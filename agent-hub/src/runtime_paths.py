"""Marketing Hub 组合根公共路径与运行时环境 bootstrap.

Hermes 已源码整合进 Marketing Hub；Agent 与 Hub **共用**数据根目录，
**不再使用** ``HERMES_HOME`` 环境变量，也无额外 ``hermes/`` 子目录。

**数据根** 解析（**不**读取 ``HUB_DATA_DIR`` 配置；bootstrap 后仅向内注入 env 供子进程）::

  1. ``{安装根}/data`` — frozen exe 或 ``MARKETING_HUB_INSTALL_ROOT``
  2. ``{仓库根}/.data`` — 源码 / dev 启动

一体部署下 ``get_hermes_home()`` 为 profile 运行时目录；``config.yaml`` / ``.env`` 在数据根（全局）。
**不读取** ``HERMES_HOME`` 环境变量。

目录示意::

    {data_root}/
      device/                 Hub IPC、本地登录态
      hub.db                  统一 Hub SQLite（CRM/知识库/业务）
      config.yaml, .env       Agent 全局配置（与 profile 无关）
      sessions/, skills/, logs/ …  profile 运行时数据（``profiles/<name>/`` 或根）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 与 main.py 一致：使 hermes_constants / hermes_cli 可被 import（pytest 亦依赖）
_SRC_ROOT = Path(__file__).resolve().parent
if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

_INSTALL_ROOT_ENV = "MARKETING_HUB_INSTALL_ROOT"
_LEGACY_HERMES_HOME_ENV = "HERMES_HOME"


def resolve_repo_root() -> Path:
    """仓库根目录（``backend/src`` 上两级）."""
    return Path(__file__).resolve().parents[2]


def resolve_install_root_for_data() -> Path | None:
    """数据目录用的安装根：frozen exe 或显式 ``MARKETING_HUB_INSTALL_ROOT``."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    explicit = os.environ.get(_INSTALL_ROOT_ENV, "").strip()
    if explicit:
        return Path(explicit)
    return None


def resolve_install_root() -> Path:
    """日志/展示用安装根：数据层安装根 → dev 仓库根."""
    data_root = resolve_install_root_for_data()
    if data_root is not None:
        return data_root
    return resolve_repo_root()


def _truthy_env(name: str) -> bool:
    return (os.environ.get(name) or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def bootstrap_dotenv_if_needed() -> None:
    """``start_*.cmd`` 未注入关键 env 时，从仓库根补读 ``.env.dev`` / ``.env``."""
    if "HUB_LOCAL_DB_PATH" in os.environ:
        return
    root = resolve_repo_root()
    from dotenv import load_dotenv

    for name in (".env.dev", ".env"):
        path = root / name
        if path.is_file():
            load_dotenv(path, override=True)
            return


def resolve_hub_data_dir_path() -> Path:
    """解析 Hub/Agent 数据根（dev → ``{repo}/.data``；打包 → ``{install}/data``）."""
    data_install = resolve_install_root_for_data()
    if data_install is not None:
        return data_install / "data"
    return resolve_repo_root() / ".data"


def resolve_hub_logs_dir_path() -> Path:
    """``{data_root}/logs`` — 与 MxAI ``data/logs/mxai-boot.log`` 同根."""
    return resolve_hub_data_dir_path() / "logs"


def resolve_hub_state_dir_path() -> Path:
    """``{data_root}/state`` — Hermes/Gateway 可重建运行时 JSON（非 MxAI ``plugins/mxai/state/``）。"""
    return resolve_hub_data_dir_path() / "state"


def resolve_hermes_data_dir() -> Path:
    """Agent 数据根目录（与 Hub 数据根相同）."""
    return resolve_hub_data_dir_path()


def ensure_hub_logs_dir() -> Path:
    """Ensure ``{data_root}/logs`` exists."""
    log_dir = resolve_hub_logs_dir_path()
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


def ensure_hub_data_dir() -> Path:
    """确保数据根存在."""
    data_dir = resolve_hub_data_dir_path()
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def _drop_legacy_hermes_home_env() -> None:
    """一体部署不保留遗留 ``HERMES_HOME`` 环境变量."""
    os.environ.pop(_LEGACY_HERMES_HOME_ENV, None)


def bootstrap_marketing_hub_runtime() -> dict[str, str]:
    """启动前：补 dotenv、统一 Hub + Agent 工作目录."""
    bootstrap_dotenv_if_needed()
    _drop_legacy_hermes_home_env()

    install_root = resolve_install_root()
    data_install_root = resolve_install_root_for_data()
    data_dir = ensure_hub_data_dir()
    ensure_hub_logs_dir()
    # 子进程（gateway spawn 等）仍读 env；路径由 bootstrap 计算，勿在 .env 配置 HUB_DATA_DIR。
    os.environ["HUB_DATA_DIR"] = str(data_dir)

    return {
        "install_root": str(install_root),
        "data_install_root": str(data_install_root or ""),
        "data_dir": str(data_dir),
    }
