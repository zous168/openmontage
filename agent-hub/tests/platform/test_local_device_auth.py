"""Unit tests for LocalDeviceAuthStore (LT-028.01.02)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from core.platform.control_server import DeviceLoginResult
from core.platform.device.local_device_auth import (
    DeviceAuth,
    LocalDeviceAuthStore,
    save_from_control_server,
)


@pytest.fixture
def auth_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    # resolve_hub_data_dir_path 不读 HUB_DATA_DIR，须显式指向 tmp（与 tests/conftest mxai_env 一致）
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: tmp_path,
    )
    return tmp_path


def _auth_json_path(data_dir: Path) -> Path:
    return data_dir / "device" / "device_auth.json"


def test_tp_z1_04_save_load_includes_refresh_token(auth_dir: Path) -> None:
    """TP-Z1-04: after save, load() includes refresh_token."""
    store = LocalDeviceAuthStore()
    auth = DeviceAuth(
        user_id="user-1",
        login_name="aw_1d8c23200075fe43bf0881c5",
        tenant_id="tenant-1",
        tenant_name="Demo Tenant",
        device_id="device-1",
        access_token="access-abc",
        expires_at=time.time() + 3600,
        refresh_token="refresh-xyz",
    )
    store.save(auth)

    raw = json.loads(_auth_json_path(auth_dir).read_text(encoding="utf-8"))
    assert raw["refresh_token"] == "refresh-xyz"

    loaded = store.load()
    assert loaded is not None
    assert loaded.refresh_token == "refresh-xyz"


def test_tp_z1_05_old_json_without_refresh_still_loads(auth_dir: Path) -> None:
    """TP-Z1-05: legacy json without refresh_token still loads."""
    path = _auth_json_path(auth_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "user_id": "user-legacy",
                "login_name": "legacy",
                "tenant_id": "tenant-legacy",
                "tenant_name": "Legacy Tenant",
                "device_id": "device-legacy",
                "access_token": "legacy-access",
                "expires_at": 1234567890.0,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = LocalDeviceAuthStore().load()
    assert loaded is not None
    assert loaded.refresh_token == ""
    assert loaded.user_id == "user-legacy"
    assert loaded.access_token == "legacy-access"


def test_tp_z1_06_tenant_id_from_control_server_response(
    auth_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TP-Z1-06: tenant_id matches CS response tenant.id (not HUB_DEV_TENANT_ID)."""
    monkeypatch.setenv("HUB_DEV_TENANT_ID", "dev-tenant-placeholder")

    fixed_now = 1_700_000_000.0
    monkeypatch.setattr(
        "core.platform.device.local_device_auth.time.time",
        lambda: fixed_now,
    )

    result = DeviceLoginResult(
        access_token="access-cs",
        refresh_token="refresh-cs",
        expires_in=7200,
        token_type="Bearer",
        user={"id": "cs-user-42", "login_name": "aw_1d8c23200075fe43bf0881c5", "role": "ai_worker"},
        tenant={
            "id": "cs-tenant-real",
            "name": "CS Tenant",
            "status": "active",
            "enabled_modules": [],
        },
    )

    auth = save_from_control_server(
        "aw_1d8c23200075fe43bf0881c5",
        result,
        device_id="device-cs",
    )

    assert auth.tenant_id == "cs-tenant-real"
    assert auth.tenant_name == "CS Tenant"
    assert auth.user_id == "cs-user-42"
    assert auth.display_name == "aw_1d8c23200075fe43bf0881c5"  # 无 display_name 时回落 login_name
    assert auth.refresh_token == "refresh-cs"
    assert auth.expires_at == fixed_now + 7200

    loaded = LocalDeviceAuthStore().load()
    assert loaded is not None
    assert loaded.tenant_id == "cs-tenant-real"
    assert loaded.tenant_id != "dev-tenant-placeholder"


def test_tp_z1_06b_tenant_id_from_user_when_tenant_object_missing(auth_dir: Path) -> None:
    """When CS omits tenant object, fall back to user.tenant_id."""
    result = DeviceLoginResult(
        access_token="access-cs",
        refresh_token="refresh-cs",
        expires_in=7200,
        token_type="Bearer",
        user={
            "id": "cs-user-42",
            "login_name": "aw_1d8c23200075fe43bf0881c5",
            "role": "ai_worker",
            "tenant_id": "00000000-0000-0000-0000-000000000001",
            "display_name": "演示AI员工",
        },
        tenant=None,
    )

    auth = save_from_control_server("aw_1d8c23200075fe43bf0881c5", result, device_id="device-cs")

    assert auth.tenant_id == "00000000-0000-0000-0000-000000000001"
    assert auth.tenant_name == "演示AI员工"
    assert auth.display_name == "演示AI员工"
    assert LocalDeviceAuthStore().load() is not None
    assert LocalDeviceAuthStore().load().display_name == "演示AI员工"


def test_credit_balance_float_roundtrip(auth_dir: Path) -> None:
    """落盘/加载保留浮点算力点（与 CS NUMERIC 对齐）。"""
    result = DeviceLoginResult(
        access_token="access-cs",
        refresh_token="refresh-cs",
        expires_in=7200,
        token_type="Bearer",
        user={"id": "u1", "login_name": "aw1", "role": "ai_worker"},
        tenant={"id": "t1", "name": "T", "status": "active"},
        credit_balance=999973.83,
        compute_point_tokens=100,
    )
    auth = save_from_control_server("aw1", result, device_id="d1")
    assert auth.credit_balance == pytest.approx(999973.83)

    loaded = LocalDeviceAuthStore().load()
    assert loaded is not None
    assert loaded.credit_balance == pytest.approx(999973.83)

    # 直接写 JSON 浮点 / 字符串也能 load
    path = _auth_json_path(auth_dir)
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["credit_balance"] = "42.25"
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    reloaded = LocalDeviceAuthStore().load()
    assert reloaded is not None
    assert reloaded.credit_balance == pytest.approx(42.25)
