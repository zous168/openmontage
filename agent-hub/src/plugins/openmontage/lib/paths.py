"""Canonical paths — single source of truth.

系统里有三个根，只在这里定义一次：

``CODE_ROOT``
    代码根 —— 由 ``__file__`` 推导。tools/、lib/、skills/、pipeline_defs/、
    schemas/、styles/ 都在它下面，随代码一起分发。
    独立仓库里它就是仓库根；作为 Hermes 能力插件时它是
    ``agent-hub/src/plugins/openmontage/``。

``REPO_ROOT``
    仓库根 —— 容纳不随插件分发的大件：vendor/、.agents/、assets/、
    remotion-composer/、.venv、.env。用标志物向上探测而非写死目录深度，
    这样代码搬家不会静默失效。

``DATA_ROOT``
    数据根 —— 运行时可写的东西：projects/、.backlot/、output/ 等。
    三档解析：显式的 ``OPENMONTAGE_DATA_ROOT`` > 宿主的
    ``{HUB_DATA_DIR}/montage`` > ``REPO_ROOT``（独立签出时的老行为）。
    数据面整体平移，而 ``montage/`` 下的目录名与布局跟仓库根完全一样。

projects 根是系统里最吃重的路径：检查点写在它下面，工具事件按它归属，
Backlot 看板盯着它。只定义一次。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

CODE_ROOT = Path(__file__).resolve().parent.parent

# ``plugins/`` 的父目录 —— 子进程要把它放进 PYTHONPATH 才能 import
# ``plugins.openmontage.*``。作为插件安装时这是 agent-hub/src，独立签出时
# 是仓库根；两种布局都由同一个相对关系导出。
IMPORT_ROOT = CODE_ROOT.parent.parent


def _env_path(*names: str) -> Path | None:
    """按顺序取第一个非空环境变量作为路径；靠前的名字优先。"""
    for name in names:
        raw = (os.environ.get(name) or "").strip()
        if raw:
            return Path(raw).expanduser()
    return None


# 仓库根的标志物：这些只出现在仓库顶层，不会出现在插件目录里。
_REPO_MARKERS = (".git", "vendor", "remotion-composer")


def _resolve_repo_root() -> Path:
    """从代码根向上找仓库标志物。

    刻意不写 ``parents[N]``：那种写法在代码搬家后会静默指向错误目录，
    而不是报错。找不到标志物时退回代码根 —— 独立签出时两者本就相同。
    """
    override = _env_path("OPENMONTAGE_REPO_ROOT")
    if override is not None:
        return override
    for candidate in (CODE_ROOT, *CODE_ROOT.parents):
        if any((candidate / marker).exists() for marker in _REPO_MARKERS):
            return candidate
    if getattr(sys, "frozen", False):
        # 冻结态下代码在只读的 _MEIPASS 临时目录里，往上找不到任何仓库标志物。
        # 退回 exe 所在目录：vendor/、remotion-composer/ 这类随分发放置的
        # 大件应该躺在安装目录旁边，而不是随机的解压路径里。
        return Path(sys.executable).resolve().parent
    return CODE_ROOT


REPO_ROOT = _resolve_repo_root()


def _hub_montage_root() -> Path | None:
    """宿主 profile 数据目录下的 ``montage/``。

    作为 Hermes 能力挂载时数据面理应落在 profile 下面，而不是跟源码混在仓库
    根里。刻意不要求宿主额外注入 ``OPENMONTAGE_DATA_ROOT`` —— 这里的常量是
    模块级的，在插件 ``register()`` 被调用前就已经算完，宿主那时再注入已经晚了。

    走宿主自己的 ``get_hermes_home()`` 而不是直接读 ``HUB_DATA_DIR``：后者只有
    hub 拉起的进程才带，CLI 起的 agent 没有，于是同一台机器上 hub 看到一份
    projects、CLI 看到另一份。同一个解析函数才能让同一 profile 下的 agent
    看到同一份数据。

    独立签出时 ``hermes_constants`` 不存在，返回 None 退回仓库根。
    """
    try:
        from hermes_constants import get_hermes_home
    except ImportError:
        return None
    try:
        return get_hermes_home() / "montage"
    except Exception:
        return None


# 数据根。显式覆盖 > 宿主数据面 > 仓库根（独立签出里直接跑的老行为）。
DATA_ROOT = _env_path("OPENMONTAGE_DATA_ROOT") or _hub_montage_root() or REPO_ROOT

# Overridable for staging/screenshots/tests. Everything — checkpoint writes,
# event attribution, the Backlot board — follows the same root.
PROJECTS_DIR = _env_path("OPENMONTAGE_PROJECTS_DIR") or (DATA_ROOT / "projects")

# Backlot 看板的运行时状态：缩略图缓存、媒体暂存、UI 设置、截图暂存。
BACKLOT_STATE_DIR = _env_path("OPENMONTAGE_BACKLOT_DIR") or (DATA_ROOT / ".backlot")

# 用户投放的免版税音乐。``MUSIC_LIBRARY_DIR`` 是历史名，保留兼容。
MUSIC_LIBRARY_DIR = _env_path("OPENMONTAGE_MUSIC_LIBRARY_DIR", "MUSIC_LIBRARY_DIR") or (
    DATA_ROOT / "music_library"
)

# 视觉回归的基线与抓图。
EVALS_DIR = _env_path("OPENMONTAGE_EVALS_DIR") or (DATA_ROOT / "internal" / "evals")

# 通用产物落点（按需创建）。
OUTPUT_DIR = _env_path("OPENMONTAGE_OUTPUT_DIR") or (DATA_ROOT / "output")

# Remotion 渲染引擎。跟数据根走而非代码根：它需要 ``npm install`` 出一个
# 1.2GB 的 node_modules，而冻结打包后的代码目录是只读的 _MEIPASS。
COMPOSER_DIR = _env_path("OPENMONTAGE_COMPOSER_DIR") or (DATA_ROOT / "remotion-composer")

# ── 随代码分发的静态资产 ────────────────────────────────────────────
SKILLS_DIR = CODE_ROOT / "skills"
STYLES_DIR = CODE_ROOT / "styles"
SCHEMAS_DIR = CODE_ROOT / "schemas"
PIPELINE_DEFS_DIR = CODE_ROOT / "pipeline_defs"
COMFYUI_WORKFLOWS_DIR = CODE_ROOT / "tools" / "_comfyui" / "workflows"

# ── 留在仓库根的大件（不随插件分发）──────────────────────────────────
# Layer 3 技能包 51MB、媒体资产 20MB —— 打进单文件 exe 不划算，按需分发。
LAYER3_SKILLS_DIR = _env_path("OPENMONTAGE_LAYER3_SKILLS_DIR") or (
    REPO_ROOT / ".agents" / "skills"
)
ASSETS_DIR = _env_path("OPENMONTAGE_ASSETS_DIR") or (REPO_ROOT / "assets")


def env_file() -> Path:
    """``.env`` 的落点：数据根优先，回退仓库根。

    默认（两根相同）与历史行为一致。作为 Hermes 能力运行时，凭据跟数据面一起
    放在 ``{HUB_DATA_DIR}/montage/.env``；仓库里的那份仍作为开发态回退。
    """
    candidate = DATA_ROOT / ".env"
    if candidate.is_file():
        return candidate
    return REPO_ROOT / ".env"
