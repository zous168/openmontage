"""系统内置模型（official）目录 / 默认主模型 单测。"""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from core.platform.device.local_device_auth import DeviceAuth, LocalDeviceAuthStore
from hermes_cli.official_gateway_models import (
    OFFICIAL_PROVIDER_SLUG,
    clear_official_gateway_models_cache,
    ensure_official_as_default_main_model,
    fetch_official_gateway_models,
    is_official_channel_ready,
)


_GATEWAY_URL = "http://127.0.0.1:4000"


@pytest.fixture
def hub_data(tmp_path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: data_dir)
    return data_dir


def _save_auth(*, access_token: str = "jwt-test") -> DeviceAuth:
    auth = DeviceAuth(
        user_id="user-1",
        login_name="aw_seed_demo001",
        tenant_id="tenant-1",
        tenant_name="Demo",
        device_id="dev-1",
        access_token=access_token,
        expires_at=time.time() + 3600,
        refresh_token="refresh-old",
    )
    LocalDeviceAuthStore().save(auth)
    return auth


def test_official_channel_ready_requires_gateway_and_jwt(hub_data, monkeypatch):
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    assert is_official_channel_ready() is False
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    assert is_official_channel_ready() is False
    _save_auth()
    assert is_official_channel_ready() is True


def test_list_authenticated_providers_includes_official(hub_data, monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    _save_auth()

    from hermes_cli.model_switch import list_authenticated_providers

    with patch(
        "hermes_cli.official_gateway_models.fetch_official_gateway_models",
        return_value=["MiniMax-M2.7", "other-model"],
    ):
        rows = list_authenticated_providers(max_models=50)

    official = next((r for r in rows if r["slug"] == OFFICIAL_PROVIDER_SLUG), None)
    assert official is not None
    assert official["name"] == "系统内置模型"
    assert official["authenticated"] is True
    assert official["auth_type"] == "device_jwt"
    assert official["models"][0] == "MiniMax-M2.7"
    assert rows[0]["slug"] == OFFICIAL_PROVIDER_SLUG


def test_canonical_providers_official_first():
    from hermes_cli.models import CANONICAL_PROVIDERS

    assert CANONICAL_PROVIDERS[0].slug == "official"
    assert CANONICAL_PROVIDERS[0].label == "系统内置模型"


def test_ensure_official_default_force(hub_data, monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    _save_auth()

    # 先写入 moark，验证 force=True 会覆盖为 official
    from hermes_cli.config import load_config, save_config

    cfg = load_config() or {}
    cfg["model"] = {"provider": "moark", "default": "MiniMax-M2.7"}
    save_config(cfg)

    with patch(
        "hermes_cli.official_gateway_models.fetch_official_gateway_models",
        return_value=["MiniMax-M2.7"],
    ):
        assert ensure_official_as_default_main_model(force=True) is True

    cfg2 = load_config() or {}
    model = cfg2.get("model") or {}
    assert model.get("provider") == "official"
    assert model.get("default") == "MiniMax-M2.7"


def test_ensure_official_skips_fetch_when_already_configured(hub_data, monkeypatch):
    """已选系统内置主模型时不应再打网关。"""
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    _save_auth()
    from hermes_cli.config import load_config, save_config

    cfg = load_config() or {}
    cfg["model"] = {"provider": "official", "default": "MiniMax-M2.7"}
    save_config(cfg)

    with patch(
        "hermes_cli.official_gateway_models.fetch_official_gateway_models",
        side_effect=AssertionError("should not fetch"),
    ) as mocked:
        assert ensure_official_as_default_main_model(force=False) is False
        mocked.assert_not_called()


def test_fetch_official_models_uses_memory_cache(hub_data, monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    _save_auth()
    clear_official_gateway_models_cache()

    with patch(
        "hermes_cli.models.fetch_api_models",
        return_value=["MiniMax-M2.7", "other"],
    ) as live:
        first = fetch_official_gateway_models()
        second = fetch_official_gateway_models()

    assert first == ["MiniMax-M2.7", "other"]
    assert second == first
    assert live.call_count == 1


def test_fetch_official_models_force_refresh_bypasses_cache(hub_data, monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", _GATEWAY_URL)
    _save_auth()
    clear_official_gateway_models_cache()

    with patch(
        "hermes_cli.models.fetch_api_models",
        side_effect=[["a"], ["b"]],
    ) as live:
        assert fetch_official_gateway_models() == ["a"]
        assert fetch_official_gateway_models(force_refresh=True) == ["b"]

    assert live.call_count == 2
