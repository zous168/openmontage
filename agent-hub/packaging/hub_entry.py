"""agent-hub 冻结入口（PyInstaller onefile）：以 uvicorn 启动 FastAPI 组合根。

无参运行 → 监听 HUB_API_HOST/HUB_API_PORT（默认 127.0.0.1:8642）。
作为 MxAI 的 sidecar（agent-hub.exe）被拉起；数据目录沿用 HUB_DATA_DIR。

冻结后 bundled 资源（插件/skills）经环境变量逃生口指向 _MEIPASS（onefile 解压目录）：
  HERMES_BUNDLED_PLUGINS  → 插件根
  HERMES_SKILL_DIR        → skills 根
  HERMES_NODE             → node 可执行文件（安装包默认同目录 node/node.exe；.env 可覆盖）
  HERMES_TUI_DIR          → 预编译 TUI 目录（含 entry.js）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _resource_base() -> Path:
    """冻结=_MEIPASS（onefile 解压目录）；开发=agent-hub/。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
    return Path(__file__).resolve().parent.parent  # agent-hub/


def _load_env_beside_exe() -> None:
    """冻结态：从 **exe 所在目录**（= 安装/绿色包扁平根，与 MxAI.exe 同目录）读 `.env`。

    这是打包后 hub 的运行配置来源（CONTROL_SERVER_BASE_URL / MINIO_* / 密钥 等）——
    把 `.env` 放在 exe 同目录即可，无需仓库根 `.env.dev`。`_setup_env_and_path()` 对所有
    调用（含 hub 自拉起的 gateway re-exec）都会执行，故 hub 与 gateway 都能拿到配置。
    注意：`sys.executable` 是真实 exe 路径（安装目录），**不是** onefile 解压的 `_MEIPASS`。
    override=False：尊重已显式注入的 env（如客户端 spawn 时传入），其余由 `.env` 补齐。
    """
    try:
        from dotenv import load_dotenv

        env_file = Path(sys.executable).resolve().parent / ".env"
        if env_file.exists():
            load_dotenv(env_file, override=False)
    except Exception:
        pass


def _configure_portable_node() -> None:
    """冻结安装包：使用 exe 同目录 node/node.exe（build-mxai 内置）。"""
    if not getattr(sys, "frozen", False):
        return
    exe_dir = Path(sys.executable).resolve().parent
    node_exe = exe_dir / "node" / "node.exe"
    if not node_exe.is_file():
        return
    os.environ.setdefault("HERMES_NODE", str(node_exe))
    node_dir = str(node_exe.parent)
    path = os.environ.get("PATH", "")
    parts = path.split(os.pathsep) if path else []
    if node_dir not in parts:
        os.environ["PATH"] = node_dir + (os.pathsep + path if path else "")


def _setup_env_and_path() -> None:
    base = _resource_base()
    if getattr(sys, "frozen", False):
        # bundled 资源指向 _MEIPASS（见 spec 的 datas 落点）
        os.environ.setdefault("HERMES_BUNDLED_PLUGINS", str(base / "plugins"))
        os.environ.setdefault("HERMES_SKILL_DIR", str(base / "skills"))
        bundled_tui = base / "hermes_cli" / "tui_dist" / "entry.js"
        if bundled_tui.is_file():
            os.environ.setdefault("HERMES_TUI_DIR", str(bundled_tui.parent))
        # 冻结后顶层包（hermes_cli/core/...）已在 _MEIPASS 根
        for p in (str(base),):
            if p not in sys.path:
                sys.path.insert(0, p)
        _load_env_beside_exe()  # 运行配置：exe 同目录的 .env
        _configure_portable_node()
    else:
        src = base / "src"
        for p in (str(base), str(src)):
            if p not in sys.path:
                sys.path.insert(0, p)


def _strip_python_interpreter_flags(argv: list[str]) -> list[str]:
    """去掉 ``python -u -m …`` 中 hub/dashboard spawn 常带的解释器 flag."""
    rest = list(argv)
    while rest:
        token = rest[0]
        if token == "-u":
            rest = rest[1:]
            continue
        if token == "-W" and len(rest) >= 2:
            rest = rest[2:]
            continue
        if token == "-X" and len(rest) >= 2:
            rest = rest[2:]
            continue
        if token.startswith("-X") and len(token) > 2:
            rest = rest[1:]
            continue
        break
    return rest


def _run_module_as_main(module: str, module_argv: list[str]) -> bool:
    """runpy 跑模块；``hermes_cli.main gateway run`` 归一化为 ``gateway.run``."""
    import runpy

    args = list(module_argv)
    if module == "hermes_cli.main":
        while args and args[0] in ("-p", "--profile"):
            if len(args) < 2:
                args = []
                break
            args = args[2:]
        if len(args) >= 2 and args[0] == "gateway" and args[1] == "run":
            gateway_argv = args[2:]
            sys.argv = ["gateway.run", *gateway_argv]
            runpy.run_module("gateway.run", run_name="__main__")
            return True
    if not module:
        return False
    sys.argv = [module, *args]
    runpy.run_module(module, run_name="__main__")
    return True


def _emulate_python_flags(argv: list[str]) -> bool:
    """冻结态模拟 ``python -c <code>`` / ``python -m <module>``。

    hub 运行时会用 ``sys.executable``（冻结后即本 exe）以解释器方式 re-exec 自身来拉起
    **gateway**（看门狗 ``-c "<脚本>"`` 包裹 ``-m hermes_cli.main gateway run``）。冻结 exe
    不认 ``-c`` / ``-m``，会把它们当普通 argv 丢给本入口 → 若不处理就又起一个 hub。
    这里识别并模拟：``-c`` → exec 代码；``-m`` → runpy 跑模块（run_name='__main__'）。
    返回 True 表示已作为解释器分发处理（不再起 hub）。
    """
    if not getattr(sys, "frozen", False):
        return False

    rest = _strip_python_interpreter_flags(argv)
    if not rest:
        return False
    if rest[0] == "-c":
        code = rest[1] if len(rest) > 1 else ""
        sys.argv = ["-c"] + list(rest[2:])
        exec(compile(code, "<hub-exe-c>", "exec"), {"__name__": "__main__"})
        return True
    if rest[0] == "-m":
        module = rest[1] if len(rest) > 1 else ""
        return _run_module_as_main(module, rest[2:])
    return False


def main() -> None:
    _setup_env_and_path()

    # 冻结态：hub 以本 exe 当解释器 re-exec（gateway 自拉起的看门狗 -c / -m）→ 先模拟分发。
    if _emulate_python_flags(sys.argv[1:]):
        return

    host = os.environ.get("HUB_API_HOST", "127.0.0.1").strip() or "127.0.0.1"
    port = int(os.environ.get("HUB_API_PORT", "8642"))

    from hermes_cli.parent_pid_watch import start_parent_pid_watch

    # sidecar：MxAI spawn 时注入 PARENT_PID；缺省则冻结态用 getppid() 兜底（强杀 MxAI 时自退）
    if not start_parent_pid_watch(label="agent-hub"):
        sys.exit("agent-hub: PARENT_PID missing (MxAI spawn must set it)")

    import uvicorn

    # main.py 为组合根：装配 hermes web_server + 插件发现 + 路由 + 网关生命周期（含 gateway 自拉起）。
    from main import app

    # 本机 sidecar：客户端 WebView 长连接复用到 :8642。uvicorn 默认 timeout_keep_alive=5s，
    # 空闲连接会被服务端掐断，前端复用陈旧连接时偶发 "Failed to fetch"。调大到 > 前端最长轮询/停顿窗口，
    # 从源头消除该竞速（单用户本机，多留空闲连接开销可忽略）。可用 HUB_API_KEEPALIVE 覆盖。
    keepalive = int(os.environ.get("HUB_API_KEEPALIVE", "65"))
    uvicorn.run(app, host=host, port=port, log_level="info", timeout_keep_alive=keepalive)


if __name__ == "__main__":
    main()
