"""官方渠道（platform LLM 网关）provider 装配 + JWT 刷新同步 单测 (LT-045.01.02)。

覆盖：
  ① 官方模式装配出 official provider，且 base_url/api_key/api_mode 正确；
  ② 设备 JWT 刷新后 official.api_key 同步更新（复用 ensure_device_access_fresh，mock 上游）；
  ③ 未配 LLM_GATEWAY_BASE_URL / 未登录 时不启用官方渠道（优雅降级）；
  以及 BYOK / 显式端点不被官方渠道劫持。
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import httpx
import pytest

from core.platform.control_server import ControlServerClient
from core.platform.device.device_auth_service import ensure_device_access_fresh
from core.platform.device.local_device_auth import DeviceAuth, LocalDeviceAuthStore
from hermes_cli.auth import AuthError
from hermes_cli.runtime_provider import (
    _resolve_official_runtime,
    resolve_runtime_provider,
)

_GATEWAY_URL = "https://gateway.example.com/v1"


@pytest.fixture(autouse=True)
def _reset_refresh_failure_state() -> None:
    import core.platform.device.device_auth_service as mod

    mod._last_refresh_failure_at = 0.0


@pytest.fixture
def hub_data(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """把设备会话文件根指向 tmp，避免污染真实 .data/device。"""
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    # runtime_paths.resolve_hub_data_dir_path 不读 HUB_DATA_DIR，直接 patch 到 tmp。
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: data_dir)
    return data_dir


def _save_auth(*, access_token: str, expires_at: float | None = None) -> DeviceAuth:
    auth = DeviceAuth(
        user_id="user-1",
        login_name="aw_seed_demo001",
        tenant_id="tenant-1",
        tenant_name="Demo",
        device_id="dev-1",
        access_token=access_token,
        expires_at=expires_at if expires_at is not None else time.time() + 3600,
        refresh_token="refresh-old",
    )
    LocalDeviceAuthStore().save(auth)
    return auth


def test_official_provider_assembled(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """① 官方模式装配出 official provider，字段正确。"""
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    _save_auth(access_token="jwt-device-001")

    runtime = resolve_runtime_provider(requested="official")

    assert runtime["provider"] == "official"
    assert runtime["api_mode"] == "chat_completions"
    assert runtime["base_url"] == "https://gateway.example.com/v1"  # 去尾斜杠
    assert runtime["api_key"] == "jwt-device-001"
    assert runtime["source"] == "official-gateway"


def test_official_default_selected_on_auto(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """provider 未显式指定（auto）+ 网关已配置 + 已登录 → 默认选官方渠道。"""
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    _save_auth(access_token="jwt-device-001")

    runtime = _resolve_official_runtime(requested_provider="auto")
    assert runtime is not None
    assert runtime["provider"] == "official"
    assert runtime["api_key"] == "jwt-device-001"


def test_official_api_key_syncs_after_refresh(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """② 临近过期时 resolve official 会先 refresh，拿到新 JWT。"""
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "https://cs.example.com")
    # 保存一份即将到期的会话，触发 ensure_device_access_fresh 主动刷新。
    _save_auth(access_token="jwt-old", expires_at=time.time() + 30)

    # mock 上游 refresh 返回新 JWT（须在 resolve 前装好：官方渠道读 JWT 会先 refresh）
    payload = {
        "code": 200,
        "message": "成功",
        "data": {
            "access_token": "jwt-new",
            "refresh_token": "refresh-new",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user": {"id": "user-1", "login_name": "aw_seed_demo001", "role": "ai_worker"},
        },
    }
    mock_http = MagicMock()
    mock_http.post = MagicMock(return_value=httpx.Response(200, json=payload))
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.ControlServerClient",
        lambda **kwargs: ControlServerClient(
            http_client=mock_http, base_url="https://cs.example.com"
        ),
    )

    after = resolve_runtime_provider(requested="official")
    assert after["api_key"] == "jwt-new"
    mock_http.post.assert_called()


def test_official_disabled_without_gateway_url(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """③ 未配网关基址：auto 优雅降级（None）；显式 official 严格报错（不回退）。"""
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    monkeypatch.delenv("CONTROL_SERVER_BASE_URL", raising=False)
    _save_auth(access_token="jwt-device-001")

    assert _resolve_official_runtime(requested_provider="auto") is None
    # 显式选择官方渠道时不得静默回退到其它模型 → 抛 AuthError。
    with pytest.raises(AuthError):
        _resolve_official_runtime(requested_provider="official")


def test_official_falls_back_to_control_server_base_url(
    hub_data, monkeypatch: pytest.MonkeyPatch
) -> None:
    """未设 LLM_GATEWAY_BASE_URL 时回退 CONTROL_SERVER_BASE_URL（平台一体同口）。"""
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", _GATEWAY_URL)
    _save_auth(access_token="jwt-device-001")

    rt = _resolve_official_runtime(requested_provider="official")
    assert rt is not None
    assert rt["base_url"] == _GATEWAY_URL


def test_official_appends_v1_to_edge_root(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """边缘根（无 /v1）装配给 OpenAI SDK 时须补 /v1，否则 POST /chat/completions 404。"""
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "http://srv.example.com:8080")
    _save_auth(access_token="jwt-device-001")

    rt = _resolve_official_runtime(requested_provider="official")
    assert rt is not None
    assert rt["base_url"] == "http://srv.example.com:8080/v1"


def test_official_disabled_without_device_jwt(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """网关已配置但未登录（无 JWT）：auto 降级（None）；显式 official 严格报错（不回退）。"""
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    # 不保存任何设备会话。
    assert _resolve_official_runtime(requested_provider="auto") is None
    # 显式选择官方渠道但未登录 → 抛 AuthError，绝不回退到其它模型。
    with pytest.raises(AuthError):
        _resolve_official_runtime(requested_provider="official")


def test_byok_not_hijacked_by_official(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    """BYOK / 显式端点 / 显式他 provider 时官方渠道不接管。"""
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    _save_auth(access_token="jwt-device-001")

    # 显式 base_url（BYOK 自填端点）
    assert (
        _resolve_official_runtime(
            requested_provider="auto", explicit_base_url="https://byok.example.com"
        )
        is None
    )
    # 显式 api_key（BYOK 自填 key）
    assert (
        _resolve_official_runtime(requested_provider="auto", explicit_api_key="sk-byok")
        is None
    )
    # 显式指定其它 provider
    assert _resolve_official_runtime(requested_provider="openrouter") is None
