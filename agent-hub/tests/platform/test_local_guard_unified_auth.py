"""local_guard 统一 IPC + 设备登录门禁（Hub 集成模式）."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.platform.device.local_device_auth import DeviceAuth, LocalDeviceAuthStore
from hermes_cli.dashboard_auth.local_guard import local_guard_middleware
from hermes_cli.dashboard_auth.middleware import gated_auth_middleware


@pytest.fixture
def hub_data(tmp_path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    yield data_dir


def _seed_device() -> None:
    LocalDeviceAuthStore().save(
        DeviceAuth(
            user_id="user-1",
            login_name="aw_1d8c23200075fe43bf0881c5",
            tenant_id="tenant-1",
            tenant_name="Demo",
            device_id="dev-1",
            access_token="access-1",
            expires_at=time.time() + 3600,
            refresh_token="refresh-1",
        )
    )


def _integrated_app(*, with_gated: bool = False) -> FastAPI:
    app = FastAPI()
    app.state.hub_ipc_token_validator = lambda token: token == "ipc-ok"
    app.state.hub_public_prefixes = (
        "/api/auth/login",
        "/api/auth/dev/local-ipc-token",
    )
    if with_gated:
        app.state.auth_required = True
        app.middleware("http")(gated_auth_middleware)
    app.middleware("http")(local_guard_middleware)

    @app.get("/api/plugins/mxai/ping")
    async def mxai_ping():
        return {"ok": True}

    @app.get("/api/auth/me")
    async def auth_me():
        return {"authenticated": True}

    @app.post("/api/auth/login")
    async def auth_login():
        return {"ok": True}

    @app.get("/api/status")
    async def status():
        return {"status": "ok"}

    @app.get("/memory")
    async def memory():
        return {"page": True}

    return app


@pytest.mark.parametrize("with_gated", [False, True])
def test_protected_api_requires_ipc_and_device(
    hub_data, monkeypatch: pytest.MonkeyPatch, with_gated: bool
) -> None:
    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )
    _seed_device()
    app = _integrated_app(with_gated=with_gated)
    client = TestClient(app)

    assert client.get("/api/plugins/mxai/ping").status_code == 401
    assert client.get(
        "/api/plugins/mxai/ping",
        headers={"X-Hub-Local-Token": "ipc-ok"},
    ).status_code == 200


def test_public_api_status_without_ipc(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )
    app = _integrated_app()
    client = TestClient(app)
    assert client.get("/api/status").status_code == 200


def test_auth_bootstrap_without_ipc(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )
    app = _integrated_app()
    client = TestClient(app)
    assert client.post("/api/auth/login", json={}).status_code == 200


def test_auth_me_requires_ipc_not_device_tenant(
    hub_data, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/api/auth/me 须 IPC，但不要求 tenant 注入（设备可未登录）。"""
    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )
    app = _integrated_app()
    client = TestClient(app)
    assert client.get("/api/auth/me").status_code == 401
    assert client.get(
        "/api/auth/me",
        headers={"X-Hub-Local-Token": "ipc-ok"},
    ).status_code == 200


def test_gated_auth_noop_when_hub_ipc_configured(
    hub_data, monkeypatch: pytest.MonkeyPatch
) -> None:
    """集成模式 gated 不重复验 IPC——缺 token 时由 local_guard 拦截。"""
    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )
    _seed_device()
    app = _integrated_app(with_gated=True)
    client = TestClient(app)
    res = client.get("/api/plugins/mxai/ping")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "local_token_missing"
