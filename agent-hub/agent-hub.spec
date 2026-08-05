# -*- mode: python ; coding: utf-8 -*-
"""agent-hub PyInstaller spec — onefile，产出 dist/agent-hub.exe。

MxAI sidecar：FastAPI hub @ :8642（main.py 组合根 + hermes + 23 个文件式插件）。
插件/skills 为运行期文件发现 → 作 datas 打包，入口经 HERMES_BUNDLED_PLUGINS /
HERMES_SKILL_DIR 指向 _MEIPASS。疑难/动态依赖用 collect_all 整包收集。
"""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(os.path.abspath(SPECPATH))   # agent-hub/
SRC = ROOT / "src"

datas, binaries, hiddenimports = [], [], []

# 不该进冻结产物的东西。openmontage 插件的 tests/ 有 30MB 夹具，
# 占插件总体积的七成，而运行期一行都不读。
_DATA_EXCLUDE_DIRS = {"__pycache__", "tests", "node_modules", ".venv", ".pytest_cache", ".ruff_cache"}
_DATA_EXCLUDE_SUFFIXES = {".pyc", ".pyo"}


def _filtered_tree(root: Path, dest_prefix: str) -> list[tuple[str, str]]:
    """逐文件收集，跳过 _DATA_EXCLUDE_*。

    PyInstaller 的目录式 datas 是整棵递归复制、无从过滤，所以这里自己走一遍。
    """
    out = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in _DATA_EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.suffix in _DATA_EXCLUDE_SUFFIXES:
            continue
        parent = rel.parent.as_posix()
        dest = dest_prefix if parent == "." else f"{dest_prefix}/{parent}"
        out.append((str(path), dest))
    return out


# ── 运行期数据（保留冻结后访问结构）──
_data_map = {
    "plugins": "plugins",                        # 文件式插件发现根
    "templates": "templates",                    # profile 脚手架模板（src/templates/_default）
    "skills": "skills",                          # 技能库
    "hermes_cli/web_dist": "hermes_cli/web_dist",
    "hermes_cli/web_routes": "hermes_cli/web_routes",
    "hermes_cli/tui_dist": "hermes_cli/tui_dist",  # Dashboard /api/pty 内嵌 Chat（node dist/entry.js）
    "gateway/assets": "gateway/assets",
}
for src_rel, dest_rel in _data_map.items():
    p = SRC / src_rel
    if p.exists():
        datas.extend(_filtered_tree(p, dest_rel))
    elif src_rel == "hermes_cli/tui_dist":
        raise SystemExit(
            f"ERROR: missing {p} — Dashboard Chat requires tui_dist/entry.js "
            "(run scripts/build-hub.ps1 Ensure-HermesTuiDist or commit prebuilt entry.js)"
        )

_shared_mod = ROOT.parent / "shared" / "parent_pid_watch.py"
if _shared_mod.is_file():
    datas.append((str(_shared_mod), "."))

# ── 疑难/动态依赖整包收集（数据文件 + 子模块 + 二进制）──
_collect = [
    "uvicorn", "fastapi", "starlette",
    "supabase", "gotrue", "postgrest", "storage3", "realtime", "supafunc",
    "apscheduler", "openai", "jose", "passlib", "asyncpg",
    "aioboto3", "aiobotocore", "botocore", "boto3",
    "pypdf", "docx", "openpyxl", "sqlmodel", "structlog",
    "pydantic", "pydantic_settings", "jinja2", "brotlicffi", "orjson",
    "email_validator", "anyio", "httpx", "httpcore", "websockets", "aiohttp",
    # Dashboard /api/pty：WinPTY 后端需要 winpty-agent.exe + winpty.dll
    "winpty",
    # 随包 ffmpeg 二进制（音色转 wav / 抽帧 / 去音轨）
    "imageio_ffmpeg",
]
for pkg in _collect:
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# ── uvicorn 运行时 auto 实现（动态选择，需显式声明）──
hiddenimports += [
    "uvicorn.loops.auto", "uvicorn.loops.asyncio",
    "uvicorn.protocols.http.auto", "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets.auto", "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan.on", "uvicorn.lifespan.off",
    "psycopg2", "anyio._backends._asyncio",
]

a = Analysis(
    [str(ROOT / "packaging" / "hub_entry.py")],
    pathex=[str(ROOT), str(SRC)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PyQt5", "PyQt6", "PySide6", "torch",
              "nacl"],  # PyNaCl 在本 venv 缺 __init__（装坏）、hub 核心不用 → 排除避免 hook 崩

    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="agent-hub",
    debug=False,
    # Sidecar：bootloader 不转发控制台 CTRL_* 给应用进程。
    bootloader_ignore_signals=True,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "packaging" / "agent-hub.ico"),  # Hub 后端调度中枢图标（网络拓扑）
)
