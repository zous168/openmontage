"""Fail-closed auth teardown tests (LT-028.02.02)."""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core.platform.device.device_auth_service import clear_device_auth_fail_closed
from core.platform.device.local_device_auth import DeviceAuth, LocalDeviceAuthStore
from plugins.mxai.orchestrator.queue_manager import QueueManager


@pytest.fixture
def hub_data(tmp_path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    QueueManager.reset()
    yield data_dir
    QueueManager.reset()


def _seed_auth(hub_data) -> None:
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


def test_tp_z2_04_clears_device_auth(hub_data) -> None:
    """TP-Z2-04: simulated 401 clears device_auth.json."""
    _seed_auth(hub_data)
    clear_device_auth_fail_closed(reason="test_401")
    assert LocalDeviceAuthStore().load() is None


def test_tp_z2_05_disarms_queue(hub_data) -> None:
    """TP-Z2-05: work_armed=false and global pause after fail-closed."""
    q = QueueManager.get()
    with q._mutex:
        q._work_armed = True
        q._global_paused = False
    assert q.is_work_armed() is True

    clear_device_auth_fail_closed(reason="test_disarm")
    assert q.is_work_armed() is False
    assert q.summary()["paused"] is True


def test_tp_z2_06_mxai_api_401_without_ipc(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """受保护 mxai API 无 IPC token 时返回 401 local_token_missing。"""
    from hermes_cli.dashboard_auth.local_guard import local_guard_middleware
    from plugins.mxai.api.router import router as mxai_router

    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    app.state.hub_ipc_token_validator = lambda token: token == "valid-ipc"
    app.middleware("http")(local_guard_middleware)

    client = TestClient(app)
    res = client.get("/api/plugins/mxai/stats/summary")
    assert res.status_code == 401
    assert res.json()["detail"]["code"] == "local_token_missing"


def test_tp_z2_06_mxai_api_401_without_ticket(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z2-06: protected mxai API returns 401 when device auth cleared."""
    from hermes_cli.dashboard_auth.local_guard import local_guard_middleware
    from plugins.mxai.api.router import router as mxai_router

    monkeypatch.setenv("HUB_ENV", "development")
    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    app.state.hub_ipc_token_validator = lambda token: token == "valid-ipc"
    app.middleware("http")(local_guard_middleware)

    client = TestClient(app)
    res = client.get(
        "/api/plugins/mxai/stats/summary",
        headers={"X-Hub-Local-Token": "valid-ipc"},
    )
    assert res.status_code == 401
    body = res.json()
    detail = body["detail"]
    assert detail["code"] == "device_not_logged_in"
    assert body["error"] == "unauthenticated"
    assert body["login_url"] == "/login"


def test_tp_z2_07_spa_redirects_to_login_without_device(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """未设备登录时访问 SPA 路由应 302 → /login?next=…"""
    from hermes_cli.dashboard_auth.local_guard import local_guard_middleware

    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )

    app = FastAPI()

    @app.get("/memory")
    async def memory_page():
        return {"ok": True}

    app.state.hub_ipc_token_validator = lambda token: token == "valid-ipc"
    app.middleware("http")(local_guard_middleware)

    client = TestClient(app, follow_redirects=False)
    res = client.get(
        "/memory",
        headers={
            "Accept": "text/html",
            "X-Hub-Local-Token": "valid-ipc",
        },
    )
    assert res.status_code == 302
    assert res.headers["location"] in {"/login?next=/memory", "/login?next=%2Fmemory"}
