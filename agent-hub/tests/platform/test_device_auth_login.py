"""Unit tests for device login service + route behavior (LT-028.01.03)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.platform.control_server import DeviceLoginResult, InvalidCredentialsError
from core.platform.device.device_auth_service import perform_device_login
from core.platform.device.local_device_auth import LocalDeviceAuthStore
from hermes_cli.dashboard_auth.routes import router


@pytest.fixture
def hub_data(tmp_path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: data_dir)
    return data_dir


def test_tp_z1_07_development_seed_login_200(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z1-07: HUB_ENV=development + seed credentials → persisted session."""
    monkeypatch.setenv("HUB_ENV", "development")
    monkeypatch.setenv("HUB_DEV_SEED_AI_WORKER_LOGIN", "aw_1d8c23200075fe43bf0881c5")
    monkeypatch.setenv("HUB_DEV_SEED_PASSWORD", "Seed@Pass123")

    auth = perform_device_login(login_name="aw_1d8c23200075fe43bf0881c5", password="Seed@Pass123")
    assert auth.login_name == "aw_1d8c23200075fe43bf0881c5"
    assert auth.tenant_id
    loaded = LocalDeviceAuthStore().load()
    assert loaded is not None
    assert loaded.access_token == auth.access_token


def test_tp_z1_08_production_mock_cs_login_persists(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z1-08: HUB_ENV≠development + mock CS → 200 persisted."""
    monkeypatch.setenv("HUB_ENV", "test")
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")

    payload = {
        "code": 200,
        "message": "登录成功",
        "data": {
            "access_token": "access-1",
            "refresh_token": "refresh-1",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user": {"id": "user-9", "login_name": "aw_prod", "role": "ai_worker"},
            "tenant": {"id": "tenant-9", "name": "Demo Tenant", "status": "active"},
        },
    }
    mock_http = MagicMock()
    mock_http.post = MagicMock(return_value=httpx.Response(200, json=payload))

    monkeypatch.setattr(
        "core.platform.device.device_auth_service.ControlServerClient",
        lambda **kwargs: __import__(
            "core.platform.control_server",
            fromlist=["ControlServerClient"],
        ).ControlServerClient(http_client=mock_http, base_url="https://cs.example.com"),
    )

    auth = perform_device_login(login_name="aw_prod", password="Secret@123")
    assert auth.tenant_id == "tenant-9"
    assert auth.refresh_token == "refresh-1"
    assert LocalDeviceAuthStore().load() is not None


def test_tp_z1_09_wrong_password_401(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z1-09: wrong password → InvalidCredentialsError."""
    monkeypatch.setenv("HUB_ENV", "development")
    with pytest.raises(InvalidCredentialsError):
        perform_device_login(login_name="aw_1d8c23200075fe43bf0881c5", password="wrong")


def test_device_auth_login_route_development(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_ENV", "development")
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    res = client.post(
        "/api/auth/login",
        json={"login_name": "aw_1d8c23200075fe43bf0881c5", "password": "Seed@Pass123"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["login_name"] == "aw_1d8c23200075fe43bf0881c5"
    assert body["tenant_id"]


def test_device_auth_login_route_production_mock(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HUB_ENV", "test")

    def fake_perform(*, login_name: str, password: str):
        from core.platform.device.local_device_auth import DeviceAuth

        return DeviceAuth(
            user_id="u1",
            login_name=login_name,
            tenant_id="t1",
            tenant_name="Tenant",
            device_id="d1",
            access_token="a1",
            expires_at=9999999999.0,
            refresh_token="r1",
        )

    monkeypatch.setattr(
        "core.platform.device.device_auth_service.perform_device_login",
        fake_perform,
    )
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)
    res = client.post(
        "/api/auth/login",
        json={"login_name": "aw_prod", "password": "Secret@123"},
    )
    assert res.status_code == 200
    assert res.json()["tenant_id"] == "t1"


def test_dev_seed_login_defaults_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """FR-AUTH-02: login page pre-fill from HUB_DEV_SEED_* when set."""
    from hermes_cli.dashboard_auth.login_page import dev_seed_login_defaults

    monkeypatch.setenv("HUB_DEV_SEED_AI_WORKER_LOGIN", "custom_user")
    monkeypatch.setenv("HUB_DEV_SEED_PASSWORD", "Custom@Pass")
    login, password = dev_seed_login_defaults()
    assert login == "custom_user"
    assert password == "Custom@Pass"


def test_dev_seed_login_defaults_empty_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from hermes_cli.dashboard_auth.login_page import dev_seed_login_defaults

    monkeypatch.delenv("HUB_DEV_SEED_AI_WORKER_LOGIN", raising=False)
    monkeypatch.delenv("HUB_DEV_SEED_PASSWORD", raising=False)
    login, password = dev_seed_login_defaults()
    assert login == ""
    assert password == ""


def test_integrated_login_page_prefills_login_prefs(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """GET /login（未设备登录）预填本机凭证区 login_prefs。"""
    from core.platform.device.login_prefs import save_login_prefs

    save_login_prefs(
        login_name="aw_09cc0c9e511803f6c128ab09",
        password="admin123",
        remember_password=True,
        auto_login=False,
    )

    app = FastAPI()
    app.state.hub_ipc_token_validator = lambda token: True
    app.include_router(router)
    client = TestClient(app)
    res = client.get("/login")
    assert res.status_code == 200
    html = res.text
    assert 'value="aw_09cc0c9e511803f6c128ab09"' in html
    assert 'value="admin123"' in html


def test_login_page_skips_form_when_device_already_logged_in(
    hub_data, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MxAI 已设备登录时访问 /login → 302 + IPC cookie，无需再登。"""
    from core.platform.device.local_device_auth import DeviceAuth

    LocalDeviceAuthStore().save(
        DeviceAuth(
            user_id="u1",
            login_name="aw_shared",
            tenant_id="00000000-0000-0000-0000-000000000001",
            tenant_name="Demo",
            device_id="d1",
            access_token="tok",
            expires_at=9_999_999_999,
            refresh_token="rt",
        )
    )
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.ensure_device_access_fresh",
        lambda: None,
    )

    app = FastAPI()
    app.state.hub_ipc_token_validator = lambda token: True
    app.include_router(router)
    client = TestClient(app, follow_redirects=False)
    res = client.get("/login?next=/channels")
    assert res.status_code == 302
    assert res.headers["location"] == "/channels"
    assert "local_ipc_token=" in (res.headers.get("set-cookie") or "")
