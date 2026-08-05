"""在数据根上准备 Remotion 渲染引擎。

Remotion 是个 Node 工程：``src/`` 只有 0.2MB，但要跑起来得先 ``npm install``
拉出约 1.2GB 的 ``node_modules``。这决定了它**不能**跟 Python 代码一起打进
单文件 exe —— 冻结后的代码目录是只读的 ``_MEIPASS`` 临时解压区，
既装不进去，下次启动也会丢。

所以 ``COMPOSER_DIR`` 跟数据根走。三种情形：

独立签出（``DATA_ROOT == REPO_ROOT``）
    ``COMPOSER_DIR`` 就是仓库里那份，什么都不用做。

Hermes 能力模式（数据根在 ``{HUB_DATA_DIR}/montage``）
    首次使用时把工程骨架从仓库复制过去，再 ``npm install``。
    骨架很小（不含 node_modules），复制是秒级的。

冻结分发（没有仓库可复制）
    只能如实报告缺失并给出安装指引 —— 假装可用只会让渲染在几分钟后
    以一句晦涩的 webpack 报错失败。
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from plugins.openmontage.lib.paths import COMPOSER_DIR, REPO_ROOT

# 构成"一份可用的 Remotion 工程"的最小骨架。node_modules 与 out 刻意不在其中。
_SKELETON = ("package.json", "package-lock.json", "tsconfig.json", "remotion.config.ts", "src")

_NPM = shutil.which("npm") or ("npm.cmd" if shutil.which("npm.cmd") else "npm")


@dataclass
class RemotionStatus:
    """Remotion 就绪状态 —— 供 om_preflight 如实呈现。"""

    composer_dir: Path
    has_project: bool
    has_node_modules: bool
    node_available: bool
    notes: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return self.has_project and self.has_node_modules and self.node_available

    def as_dict(self) -> dict:
        return {
            "composer_dir": str(self.composer_dir),
            "ready": self.ready,
            "has_project": self.has_project,
            "has_node_modules": self.has_node_modules,
            "node_available": self.node_available,
            "notes": self.notes,
        }


def _source_dir() -> Path | None:
    """仓库里那份 Remotion 工程；冻结分发时可能不存在。"""
    candidate = REPO_ROOT / "remotion-composer"
    return candidate if (candidate / "package.json").is_file() else None


def status() -> RemotionStatus:
    """体检，不做任何写入。"""
    node = shutil.which("node")
    st = RemotionStatus(
        composer_dir=COMPOSER_DIR,
        has_project=(COMPOSER_DIR / "package.json").is_file(),
        has_node_modules=(COMPOSER_DIR / "node_modules").is_dir(),
        node_available=bool(node),
    )
    if not st.node_available:
        st.notes.append("未找到 node：Remotion 需要 Node.js 22+，请先安装")
    if not st.has_project:
        src = _source_dir()
        if src is None:
            st.notes.append(
                f"{COMPOSER_DIR} 没有 Remotion 工程，且仓库里也找不到可复制的源。"
                "请手工放置 remotion-composer/ 或改用 ffmpeg / HyperFrames 合成路径"
            )
        else:
            st.notes.append(f"可从 {src} 引导出工程：调用 ensure(install=True)")
    elif not st.has_node_modules:
        st.notes.append(f"缺 node_modules：在 {COMPOSER_DIR} 下执行 npm install")
    return st


def ensure(*, install: bool = False, timeout: int = 1800) -> RemotionStatus:
    """把 Remotion 工程准备到数据根上。

    *install* 为真时在缺依赖的情况下执行 ``npm install``（可能跑好几分钟）。
    默认不装 —— 让调用方决定要不要在对话里阻塞这么久。
    """
    if COMPOSER_DIR.resolve() == (REPO_ROOT / "remotion-composer").resolve():
        # 数据根就是仓库根：工程已在原地，只可能缺依赖。
        return _maybe_install(status(), install=install, timeout=timeout)

    if not (COMPOSER_DIR / "package.json").is_file():
        src = _source_dir()
        if src is None:
            return status()
        COMPOSER_DIR.mkdir(parents=True, exist_ok=True)
        for name in _SKELETON:
            origin = src / name
            if not origin.exists():
                continue
            target = COMPOSER_DIR / name
            if target.exists():
                continue
            if origin.is_dir():
                shutil.copytree(origin, target)
            else:
                shutil.copy2(origin, target)

    return _maybe_install(status(), install=install, timeout=timeout)


def _maybe_install(st: RemotionStatus, *, install: bool, timeout: int) -> RemotionStatus:
    if not install or st.has_node_modules or not st.has_project:
        return st
    if not st.node_available:
        return st
    try:
        proc = subprocess.run(
            [_NPM, "install", "--no-audit", "--no-fund"],
            cwd=str(st.composer_dir),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        st.notes.append(f"npm install 无法启动: {exc}")
        return st
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-5:]
        st.notes.append("npm install 失败: " + " / ".join(tail))
        return st
    return status()
