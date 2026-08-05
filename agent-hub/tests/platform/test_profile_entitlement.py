"""设备账号 enabled_modules 与渠道 profile 门禁."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

import runtime_paths as rp_mod
from core.platform.device.device_auth_service import (
    is_profile_entitled,
    require_profile_entitled,
)
from core.platform.device.local_device_auth import DeviceAuth, LocalDeviceAuthStore


@pytest.fixture
def auth_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.delenv("MARKETING_HUB_INSTALL_ROOT", raising=False)
    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    return tmp_path


def test_unknown_session_allows_gated_profiles(auth_dir: Path) -> None:
    assert LocalDeviceAuthStore().load() is None
    assert is_profile_entitled("boss") is True
    assert is_profile_entitled("assistant") is True


def test_logged_in_filters_by_enabled_modules(auth_dir: Path) -> None:
    LocalDeviceAuthStore().save(
        DeviceAuth(
            user_id="u1",
            login_name="aw_test",
            tenant_id="t1",
            tenant_name="T",
            device_id="d1",
            access_token="tok",
            expires_at=time.time() + 3600,
            enabled_modules=["douyin", "qiyeweixin"],
        )
    )
    assert is_profile_entitled("douyin") is True
    assert is_profile_entitled("qiyeweixin") is True
    assert is_profile_entitled("boss") is False
    assert is_profile_entitled("assistant") is True
    with pytest.raises(ValueError, match="模块未授权"):
        require_profile_entitled("boss")
