"""Official / device_jwt: per-request token provider + 401 refresh retry."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def test_build_official_device_jwt_token_provider_reads_fresh_token():
    from core.platform.device.device_auth_service import (
        build_official_device_jwt_token_provider,
    )

    with patch(
        "core.platform.device.device_auth_service.get_fresh_device_access_token",
        return_value="jwt-rotated",
    ) as fresh:
        provider = build_official_device_jwt_token_provider()
        assert provider() == "jwt-rotated"
        fresh.assert_called_once()


def test_ensure_device_access_fresh_force_skips_threshold():
    from core.platform.device.device_auth_service import (
        REFRESH_THRESHOLD_SEC,
        ensure_device_access_fresh,
    )
    from core.platform.device.local_device_auth import DeviceAuth

    auth = DeviceAuth(
        user_id="u1",
        login_name="aw_test",
        display_name="test",
        tenant_id="t1",
        tenant_name="tenant",
        device_id="dev1",
        access_token="old",
        expires_at=__import__("time").time() + REFRESH_THRESHOLD_SEC + 600,
        refresh_token="rt-1",
        enabled_modules=[],
    )
    store = MagicMock()
    store._load_unlocked.return_value = auth
    store._save_unlocked = MagicMock()

    refreshed = MagicMock(
        access_token="new",
        refresh_token="rt-2",
        expires_in=900,
    )

    with (
        patch(
            "core.platform.device.device_auth_service.LocalDeviceAuthStore",
            return_value=store,
        ),
        patch(
            "core.platform.device.device_auth_service.ControlServerClient"
        ) as client_cls,
        patch(
            "core.platform.device.device_auth_service._cross_process_refresh_lock",
        ) as lock_ctx,
    ):
        lock_ctx.return_value.__enter__ = MagicMock(return_value=None)
        lock_ctx.return_value.__exit__ = MagicMock(return_value=False)
        client_cls.return_value.refresh.return_value = refreshed

        ensure_device_access_fresh(force=False)
        client_cls.return_value.refresh.assert_not_called()

        ensure_device_access_fresh(force=True)
        client_cls.return_value.refresh.assert_called_once_with("rt-1")


def test_try_refresh_official_client_credentials_rebuilds_client():
    from run_agent import AIAgent

    agent = AIAgent.__new__(AIAgent)
    agent.api_mode = "chat_completions"
    agent.provider = "official"
    agent.api_key = "stale"
    agent._client_kwargs = {"api_key": "stale", "base_url": "http://gw/v1"}
    agent._primary_runtime = {"api_key": "stale", "client_kwargs": dict(agent._client_kwargs)}
    agent._transport_cache = {}
    agent.client = MagicMock(name="old_client")

    token_provider = MagicMock(return_value="fresh-jwt")
    token_provider.__name__ = "official_jwt_provider"

    with (
        patch(
            "core.platform.device.device_auth_service.ensure_device_access_fresh",
        ) as ensure,
        patch(
            "core.platform.device.device_auth_service.build_official_device_jwt_token_provider",
            return_value=token_provider,
        ),
        patch("agent.auxiliary_client._evict_cached_clients") as evict,
        patch.object(agent, "_replace_primary_openai_client", return_value=True) as rebuild,
    ):
        assert agent._try_refresh_official_client_credentials(force=True) is True

    ensure.assert_called_once_with(force=True)
    evict.assert_called_once_with("official")
    rebuild.assert_called_once_with(reason="official_device_jwt_refresh")
    assert agent.api_key is token_provider
    assert agent._client_kwargs["api_key"] is token_provider


def test_resolve_provider_client_device_jwt_uses_callable_provider(_official_runtime):
    from agent import auxiliary_client as ac

    fake_client = MagicMock(name="OpenAI")
    token_provider = MagicMock(return_value="jwt-device-test")

    with (
        patch(
            "hermes_cli.runtime_provider.resolve_runtime_provider",
            return_value=_official_runtime,
        ),
        patch(
            "hermes_cli.official_gateway_models.get_official_default_model",
            return_value="MiniMax-M2.7",
        ),
        patch(
            "core.platform.device.device_auth_service.build_official_device_jwt_token_provider",
            return_value=token_provider,
        ),
        patch.object(ac, "OpenAI", return_value=fake_client) as openai_ctor,
        patch.object(ac, "_apply_user_default_headers", return_value=None),
        patch.object(ac, "_normalize_resolved_model", side_effect=lambda m, p: m),
        patch.object(ac, "_maybe_wrap_anthropic", side_effect=lambda c, *a, **k: c),
    ):
        client, model = ac.resolve_provider_client("official", "MiniMax-M2.7")

    assert client is fake_client
    assert model == "MiniMax-M2.7"
    openai_ctor.assert_called_once()
    assert openai_ctor.call_args.kwargs["api_key"] is token_provider


@pytest.fixture()
def _official_runtime():
    return {
        "provider": "official",
        "api_mode": "chat_completions",
        "base_url": "http://gateway.example.com/v1",
        "api_key": "jwt-device-test",
        "source": "official-gateway",
    }
