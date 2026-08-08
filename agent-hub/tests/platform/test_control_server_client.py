"""Unit tests for ControlServerClient (LT-028.01.01)."""

from __future__ import annotations

from unittest.mock import MagicMock

import httpx
import pytest

from core.platform.control_server import (
    ControlServerClient,
    ControlServerConfigError,
    ControlServerError,
    InvalidCredentialsError,
)

_BASE = "https://cs.example.com"


def _mock_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(status_code, json=payload)


def _client_with_mock_post(
    monkeypatch: pytest.MonkeyPatch,
    response: httpx.Response,
) -> tuple[ControlServerClient, MagicMock]:
    mock_post = MagicMock(return_value=response)
    mock_http = MagicMock()
    mock_http.post = mock_post
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", _BASE)
    client = ControlServerClient(http_client=mock_http)
    return client, mock_post


def test_tp_z1_01_missing_control_server_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z1-01: missing CONTROL_SERVER_BASE_URL → clear error."""
    monkeypatch.delenv("CONTROL_SERVER_BASE_URL", raising=False)
    with pytest.raises(ControlServerConfigError, match="CONTROL_SERVER_BASE_URL"):
        ControlServerClient()


def test_tp_z1_01_empty_control_server_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "   ")
    with pytest.raises(ControlServerConfigError, match="CONTROL_SERVER_BASE_URL"):
        ControlServerClient()


def test_tp_z1_02_success_parses_tokens_and_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z1-02: mock 200 with sample CS response → parsed tokens + tenant."""
    payload = {
        "code": 200,
        "message": "登录成功",
        "data": {
            "access_token": "access-abc",
            "refresh_token": "refresh-xyz",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user": {
                "id": "user-1",
                "login_name": "aw_1d8c23200075fe43bf0881c5",
                "role": "ai_worker",
            },
            "tenant": {
                "id": "tenant-1",
                "name": "Demo Tenant",
                "status": "active",
                "enabled_modules": [],
            },
        },
    }
    client, mock_post = _client_with_mock_post(
        monkeypatch, _mock_response(200, payload)
    )

    result = client.device_login(
        "Seed@Pass123",
        login_name="aw_1d8c23200075fe43bf0881c5",
        device_id="device-1",
        app_version="1.0.0",
        device_os="Windows-10.0.26200",
    )

    mock_post.assert_called_once_with(
        f"{_BASE}/api/hub/auth/login",
        json={
            "login_name": "aw_1d8c23200075fe43bf0881c5",
            "password": "Seed@Pass123",
            "device_id": "device-1",
            "app_version": "1.0.0",
            "device_os": "Windows-10.0.26200",
        },
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    assert result.access_token == "access-abc"
    assert result.refresh_token == "refresh-xyz"
    assert result.expires_in == 3600
    assert result.token_type == "Bearer"
    assert result.user["login_name"] == "aw_1d8c23200075fe43bf0881c5"
    assert result.tenant is not None
    assert result.tenant["id"] == "tenant-1"
    assert result.tenant["name"] == "Demo Tenant"


def test_login_parses_enabled_modules_from_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登录响应 tenant.enabled_modules → DeviceLoginResult.enabled_modules。"""
    payload = {
        "code": 200,
        "message": "ok",
        "data": {
            "access_token": "a",
            "refresh_token": "r",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user": {"id": "u", "login_name": "aw", "role": "ai_worker"},
            "tenant": {
                "id": "t1",
                "name": "T",
                "status": "active",
                "enabled_modules": ["douyin", "qiyeweixin", 123, ""],
                "entitlement_expires_at": "2027-01-01T00:00:00.000Z",
                "product_grant_count": 2,
            },
        },
    }
    client, _ = _client_with_mock_post(monkeypatch, _mock_response(200, payload))

    result = client.device_login("pw", login_name="aw")

    # 非字符串 / 空串被过滤
    assert result.enabled_modules == ["douyin", "qiyeweixin"]
    assert result.entitlement_expires_at == "2027-01-01T00:00:00.000Z"
    assert result.product_grant_count == 2


def test_login_parses_credit_balance_from_tenant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """登录响应 tenant.credit_balance → DeviceLoginResult.credit_balance。"""
    payload = {
        "code": 200,
        "message": "ok",
        "data": {
            "access_token": "a",
            "refresh_token": "r",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user": {"id": "u", "login_name": "aw", "role": "ai_worker"},
            "tenant": {
                "id": "t1",
                "name": "T",
                "status": "active",
                "enabled_modules": [],
                "credit_balance": 250,
                "compute_point_tokens": 100,
            },
        },
    }
    client, _ = _client_with_mock_post(monkeypatch, _mock_response(200, payload))

    result = client.device_login("pw", login_name="aw")

    assert result.credit_balance == 250
    assert result.compute_point_tokens == 100


def test_login_parses_float_credit_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CS NUMERIC 下发浮点时不得丢成 0（回归：isinstance int 误判）。"""
    payload = {
        "code": 200,
        "message": "ok",
        "data": {
            "access_token": "a",
            "refresh_token": "r",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user": {"id": "u", "login_name": "aw", "role": "ai_worker"},
            "tenant": {
                "id": "t1",
                "name": "T",
                "status": "active",
                "enabled_modules": [],
                "credit_balance": 999973.83,
                "compute_point_tokens": 100,
            },
        },
    }
    client, _ = _client_with_mock_post(monkeypatch, _mock_response(200, payload))

    result = client.device_login("pw", login_name="aw")

    assert result.credit_balance == pytest.approx(999973.83)


def test_login_parses_string_credit_balance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """偶发数字字符串（PG numeric 未 transformer）亦可解析。"""
    payload = {
        "code": 200,
        "message": "ok",
        "data": {
            "access_token": "a",
            "refresh_token": "r",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user": {"id": "u", "login_name": "aw", "role": "ai_worker"},
            "tenant": {
                "id": "t1",
                "name": "T",
                "status": "active",
                "enabled_modules": [],
                "credit_balance": "12.5",
                "compute_point_tokens": 100,
            },
        },
    }
    client, _ = _client_with_mock_post(monkeypatch, _mock_response(200, payload))

    result = client.device_login("pw", login_name="aw")

    assert result.credit_balance == pytest.approx(12.5)


def test_get_me_returns_enabled_modules(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_me 用 Bearer 调 /api/hub/me，解析 tenant.enabled_modules。"""
    payload = {
        "code": 200,
        "message": "ok",
        "data": {
            "id": "u",
            "role": "ai_worker",
            "tenant": {
                "id": "t1",
                "name": "T",
                "status": "active",
                "enabled_modules": ["boss", "wechat"],
                "entitlement_expires_at": None,
                "product_grant_count": 3,
            },
        },
    }
    mock_get = MagicMock(return_value=_mock_response(200, payload))
    mock_http = MagicMock()
    mock_http.get = mock_get
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", _BASE)
    client = ControlServerClient(http_client=mock_http)

    me = client.get_me("access-token-123")

    mock_get.assert_called_once_with(
        f"{_BASE}/api/hub/me",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer access-token-123",
        },
    )
    assert me.enabled_modules == ["boss", "wechat"]
    assert me.tenant is not None and me.tenant["id"] == "t1"
    # 长期（None）但有 3 条授权
    assert me.entitlement_expires_at is None
    assert me.product_grant_count == 3


def test_get_me_returns_credit_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_me 解析 tenant.credit_balance + compute_point_tokens。"""
    payload = {
        "code": 200,
        "message": "ok",
        "data": {
            "id": "u",
            "role": "ai_worker",
            "tenant": {
                "id": "t1",
                "name": "T",
                "status": "active",
                "enabled_modules": [],
                "credit_balance": 88,
                "compute_point_tokens": 100,
            },
        },
    }
    mock_get = MagicMock(return_value=_mock_response(200, payload))
    mock_http = MagicMock()
    mock_http.get = mock_get
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", _BASE)
    client = ControlServerClient(http_client=mock_http)

    me = client.get_me("access-token-123")

    assert me.credit_balance == 88
    assert me.compute_point_tokens == 100


def test_get_me_returns_float_credit_balance(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_me 保留浮点余额。"""
    payload = {
        "code": 200,
        "message": "ok",
        "data": {
            "id": "u",
            "role": "ai_worker",
            "tenant": {
                "id": "t1",
                "name": "T",
                "status": "active",
                "enabled_modules": [],
                "credit_balance": 999973.83,
                "compute_point_tokens": 100,
            },
        },
    }
    mock_get = MagicMock(return_value=_mock_response(200, payload))
    mock_http = MagicMock()
    mock_http.get = mock_get
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", _BASE)
    client = ControlServerClient(http_client=mock_http)

    me = client.get_me("access-token-123")

    assert me.credit_balance == pytest.approx(999973.83)


def test_tp_z1_02b_tenant_id_on_user_when_tenant_object_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Production CS shape: tenant_id on user, no data.tenant object."""
    payload = {
        "code": 200,
        "message": "登录成功",
        "data": {
            "access_token": "access-abc",
            "refresh_token": "refresh-xyz",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user": {
                "id": "user-1",
                "login_name": "aw_1d8c23200075fe43bf0881c5",
                "role": "ai_worker",
                "tenant_id": "00000000-0000-0000-0000-000000000001",
                "display_name": "演示AI员工",
            },
        },
    }
    client, _ = _client_with_mock_post(monkeypatch, _mock_response(200, payload))

    result = client.device_login("Seed@Pass123", login_name="aw_1d8c23200075fe43bf0881c5")

    assert result.tenant is not None
    assert result.tenant["id"] == "00000000-0000-0000-0000-000000000001"
    assert result.tenant["name"] == "演示AI员工"


def test_tp_z1_03_invalid_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """TP-Z1-03: mock 401 → invalid_credentials."""
    payload = {
        "code": 401,
        "message": "账号或密码错误",
        "data": None,
        "sub_code": "invalid_credentials",
    }
    client, _ = _client_with_mock_post(monkeypatch, _mock_response(401, payload))

    with pytest.raises(InvalidCredentialsError, match="账号或密码错误"):
        client.device_login("wrong", login_name="bad")


def test_strips_trailing_slash_from_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", f"{_BASE}/")
    mock_http = MagicMock()
    mock_http.post.return_value = _mock_response(
        200,
        {
            "code": 200,
            "message": "ok",
            "data": {
                "access_token": "a",
                "refresh_token": "r",
                "expires_in": 1,
                "token_type": "Bearer",
                "user": {"id": "u"},
                "tenant": None,
            },
        },
    )
    client = ControlServerClient(http_client=mock_http)
    assert client.base_url == _BASE
    client.device_login("p", login_name="u")
    assert mock_http.post.call_args.args[0] == f"{_BASE}/api/hub/auth/login"


def test_network_error_raises_control_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", _BASE)
    mock_http = MagicMock()
    mock_http.post.side_effect = httpx.ConnectError("connection refused")
    client = ControlServerClient(http_client=mock_http)

    with pytest.raises(ControlServerError, match="request failed"):
        client.device_login("p", login_name="u")


def test_non_json_response_raises_control_server_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", _BASE)
    mock_http = MagicMock()
    mock_http.post.return_value = httpx.Response(500, text="not json")
    client = ControlServerClient(http_client=mock_http)

    with pytest.raises(ControlServerError, match="non-JSON"):
        client.device_login("p", login_name="u")
