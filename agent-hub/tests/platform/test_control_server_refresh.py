"""Unit tests for control-server refresh + proactive session refresh (LT-028.02.01)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import httpx
import pytest

from core.platform.control_server import (
    ControlServerClient,
    DeviceRefreshResult,
    InvalidCredentialsError,
)
from core.platform.device.device_auth_service import ensure_device_access_fresh
from core.platform.device.local_device_auth import DeviceAuth, LocalDeviceAuthStore


@pytest.fixture(autouse=True)
def _reset_refresh_failure_state(monkeypatch: pytest.MonkeyPatch) -> None:
    import core.platform.device.device_auth_service as mod

    mod._last_refresh_failure_at = 0.0
    mod._last_entitlements_sync_at = 0.0


@pytest.fixture
def hub_data(tmp_path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    return data_dir


def _save_auth(*, expires_at: float) -> DeviceAuth:
    auth = DeviceAuth(
        user_id="user-1",
        login_name="aw_1d8c23200075fe43bf0881c5",
        tenant_id="tenant-1",
        tenant_name="Demo",
        device_id="dev-1",
        access_token="access-old",
        expires_at=expires_at,
        refresh_token="refresh-old",
    )
    LocalDeviceAuthStore().save(auth)
    return auth


def test_tp_z2_01_refresh_updates_access_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z2-01: refresh success updates access_token."""
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")
    payload = {
        "code": 200,
        "message": "成功",
        "data": {
            "access_token": "access-new",
            "refresh_token": "refresh-new",
            "expires_in": 7200,
            "token_type": "Bearer",
            "user": {"id": "user-1", "login_name": "aw_1d8c23200075fe43bf0881c5", "role": "ai_worker"},
        },
    }
    mock_http = MagicMock()
    mock_http.post = MagicMock(return_value=httpx.Response(200, json=payload))
    client = ControlServerClient(http_client=mock_http, base_url="https://cs.example.com")

    result = client.refresh("refresh-old")
    assert isinstance(result, DeviceRefreshResult)
    assert result.access_token == "access-new"
    assert result.refresh_token == "refresh-new"


def test_tp_z2_02_revoked_refresh_raises(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z2-02: revoked refresh → InvalidCredentialsError."""
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")
    payload = {
        "code": 401,
        "message": "会话已失效",
        "data": None,
        "sub_code": "session_revoked",
    }
    mock_http = MagicMock()
    mock_http.post = MagicMock(return_value=httpx.Response(401, json=payload))
    client = ControlServerClient(http_client=mock_http, base_url="https://cs.example.com")

    with pytest.raises(InvalidCredentialsError):
        client.refresh("bad-refresh")


def test_tp_z2_03_near_expiry_auto_refresh(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z2-03: expires_at near threshold triggers proactive refresh."""
    monkeypatch.setenv("HUB_ENV", "test")
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")
    _save_auth(expires_at=time.time() + 30)

    payload = {
        "code": 200,
        "message": "成功",
        "data": {
            "access_token": "access-refreshed",
            "refresh_token": "refresh-refreshed",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user": {"id": "user-1", "login_name": "aw_1d8c23200075fe43bf0881c5", "role": "ai_worker"},
        },
    }
    mock_http = MagicMock()
    mock_http.post = MagicMock(return_value=httpx.Response(200, json=payload))
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.ControlServerClient",
        lambda **kwargs: ControlServerClient(http_client=mock_http, base_url="https://cs.example.com"),
    )

    ensure_device_access_fresh()
    loaded = LocalDeviceAuthStore().load()
    assert loaded is not None
    assert loaded.access_token == "access-refreshed"
    assert loaded.refresh_token == "refresh-refreshed"


def test_refresh_failure_clears_session_when_access_expired(
    hub_data, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Revoked refresh + access expired logs out (fail-closed)."""
    monkeypatch.setenv("HUB_ENV", "test")
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")
    _save_auth(expires_at=time.time() - 1)

    payload = {
        "code": 401,
        "message": "会话已失效",
        "data": None,
        "sub_code": "session_revoked",
    }
    mock_http = MagicMock()
    mock_http.post = MagicMock(return_value=httpx.Response(401, json=payload))
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.ControlServerClient",
        lambda **kwargs: ControlServerClient(http_client=mock_http, base_url="https://cs.example.com"),
    )

    ensure_device_access_fresh()
    assert LocalDeviceAuthStore().load() is None


def test_refresh_failure_clears_session_while_access_still_valid(
    hub_data, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """密码重置 / 会话吊销：refresh 失败后立即下线，不再等 access 自然过期。"""
    monkeypatch.setenv("HUB_ENV", "test")
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")
    _save_auth(expires_at=time.time() + 120)

    payload = {
        "code": 401,
        "message": "会话已失效",
        "data": None,
        "sub_code": "session_revoked",
    }
    mock_http = MagicMock()
    mock_http.post = MagicMock(return_value=httpx.Response(401, json=payload))
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.ControlServerClient",
        lambda **kwargs: ControlServerClient(http_client=mock_http, base_url="https://cs.example.com"),
    )

    ensure_device_access_fresh()
    assert LocalDeviceAuthStore().load() is None


def test_refresh_failure_ignored_when_session_replaced(
    hub_data, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concurrent login replaces refresh token — old refresh failure must not clear."""
    monkeypatch.setenv("HUB_ENV", "test")
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")
    original = _save_auth(expires_at=time.time() + 30)

    def _refresh_then_login(_token: str) -> DeviceRefreshResult:
        LocalDeviceAuthStore().save(
            DeviceAuth(
                user_id=original.user_id,
                login_name=original.login_name,
                tenant_id=original.tenant_id,
                tenant_name=original.tenant_name,
                device_id=original.device_id,
                access_token="access-from-relogin",
                expires_at=time.time() + 3600,
                refresh_token="refresh-from-relogin",
            )
        )
        raise InvalidCredentialsError("会话已失效")

    mock_client = MagicMock()
    mock_client.refresh = MagicMock(side_effect=_refresh_then_login)
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.ControlServerClient",
        lambda **kwargs: mock_client,
    )

    ensure_device_access_fresh()
    loaded = LocalDeviceAuthStore().load()
    assert loaded is not None
    assert loaded.access_token == "access-from-relogin"
    assert loaded.refresh_token == "refresh-from-relogin"


def test_me_session_revoked_clears_device_auth(
    hub_data, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """GET /me 返回 session_revoked（密码重置 bump generation）→ 立即下线。"""
    from core.platform.control_server import DeviceMeResult
    from core.platform.device.device_auth_service import ensure_entitlements_fresh

    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")
    _save_auth(expires_at=time.time() + 600)

    mock_client = MagicMock()
    mock_client.get_me = MagicMock(side_effect=InvalidCredentialsError("会话已失效"))
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.ControlServerClient",
        lambda **kwargs: mock_client,
    )

    ensure_entitlements_fresh()
    assert LocalDeviceAuthStore().load() is None


def test_entitlement_lapsed_force_logs_out(
    hub_data, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """授权到期：强制清设备会话并 fail-closed 停工（不再保留「暂无授权」在线态）。"""
    from core.platform.control_server import DeviceMeResult
    from core.platform.device import device_auth_service as mod

    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")
    _save_auth(expires_at=time.time() + 600)
    auth = LocalDeviceAuthStore().load()
    assert auth is not None
    LocalDeviceAuthStore().save(
        DeviceAuth(
            user_id=auth.user_id,
            login_name=auth.login_name,
            tenant_id=auth.tenant_id,
            tenant_name=auth.tenant_name,
            device_id=auth.device_id,
            access_token=auth.access_token,
            expires_at=auth.expires_at,
            refresh_token=auth.refresh_token,
            enabled_modules=["douyin", "wechat"],
            product_grant_count=1,
            entitlement_expires_at="2099-01-01T00:00:00.000Z",
        )
    )

    mock_client = MagicMock()
    mock_client.get_me = MagicMock(
        return_value=DeviceMeResult(
            enabled_modules=[],
            tenant={"id": "t1"},
            entitlement_expires_at="2020-01-01T00:00:00.000Z",
            product_grant_count=0,
        )
    )
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.ControlServerClient",
        lambda **kwargs: mock_client,
    )
    disarm = MagicMock()
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.queue_manager.QueueManager.get",
        lambda: MagicMock(fail_closed_disarm=disarm),
    )

    mod.ensure_entitlements_fresh()
    assert LocalDeviceAuthStore().load() is None
    disarm.assert_called_once()
