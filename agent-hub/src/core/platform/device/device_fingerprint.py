"""本机设备指纹 — 登录上报 control-server 用。"""

from __future__ import annotations

import os
import platform


def get_device_os() -> str:
    """如 ``Windows-10.0.26200`` / ``Darwin-24.0.0``，最长 128。"""
    system = (platform.system() or "unknown").strip()
    release = (platform.release() or "").strip()
    label = f"{system}-{release}" if release else system
    return label[:128]


def get_hub_app_version() -> str:
    """``HUB_APP_VERSION`` 优先；否则 Hermes 包版本；再否则 ``dev``。"""
    env_ver = (os.environ.get("HUB_APP_VERSION") or "").strip()
    if env_ver:
        return env_ver[:32]
    try:
        from hermes_cli import __version__

        ver = str(__version__ or "").strip()
        if ver:
            return ver[:32]
    except Exception:  # noqa: BLE001
        pass
    return "dev"
