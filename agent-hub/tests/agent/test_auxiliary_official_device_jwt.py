"""auxiliary_client 须识别 official / device_jwt（系统内置）。"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture()
def _official_runtime():
    return {
        "provider": "official",
        "api_mode": "chat_completions",
        "base_url": "http://gateway.example.com/v1",
        "api_key": "jwt-device-test",
        "source": "official-gateway",
    }


def test_resolve_provider_client_device_jwt(_official_runtime):
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
    kwargs = openai_ctor.call_args.kwargs
    assert kwargs["api_key"] is token_provider
    assert kwargs["base_url"] == "http://gateway.example.com/v1"


def test_official_empty_model_uses_configured_main_not_gateway_first(
    _official_runtime,
):
    """回归：主模型已是 Qwen 时，空 model 的 official 调用不得回落网关第一项 MiniMax。

    流水现象：同窗口既有 ``Token · Qwen3.6-27B`` 又有 ``Token · MiniMax-M2.7``。
    根因候选：device_jwt 分支 ``model or get_official_default_model() or _read_main_model()``
    在 caller 未传 model（辅助任务 / auto 链常见）时，优先吃了网关目录第一项。
    """
    from agent import auxiliary_client as ac

    fake_client = MagicMock(name="OpenAI")
    with (
        patch(
            "hermes_cli.runtime_provider.resolve_runtime_provider",
            return_value=_official_runtime,
        ),
        patch(
            "hermes_cli.official_gateway_models.get_official_default_model",
            return_value="MiniMax-M2.7",
        ),
        patch.object(ac, "_read_main_provider", return_value="official"),
        patch.object(ac, "_read_main_model", return_value="Qwen3.6-27B"),
        patch.object(ac, "OpenAI", return_value=fake_client),
        patch.object(ac, "_apply_user_default_headers", return_value=None),
        patch.object(ac, "_normalize_resolved_model", side_effect=lambda m, p: m),
        patch.object(ac, "_maybe_wrap_anthropic", side_effect=lambda c, *a, **k: c),
    ):
        # 显式传空 / None：模拟 auxiliary 未钉死 model 的路径
        _client, model_none = ac.resolve_provider_client("official", None)
        _client2, model_empty = ac.resolve_provider_client("official", "")

    assert model_none == "Qwen3.6-27B", (
        f"空 model 应跟随已配置主模型 Qwen，实际落到 {model_none!r}（会按 MiniMax 计费）"
    )
    assert model_empty == "Qwen3.6-27B", (
        f"空串 model 应跟随已配置主模型 Qwen，实际落到 {model_empty!r}"
    )


def test_resolve_auto_step1_passes_official_base_url():
    from agent import auxiliary_client as ac

    captured = {}

    def _fake_resolve(provider, model, **kwargs):
        captured["provider"] = provider
        captured["model"] = model
        captured["kwargs"] = kwargs
        return MagicMock(), model

    with (
        patch.object(ac, "resolve_provider_client", side_effect=_fake_resolve),
        patch.object(ac, "_is_provider_unhealthy", return_value=False),
        patch.object(ac, "_read_main_provider", return_value=""),
        patch.object(ac, "_read_main_model", return_value=""),
    ):
        client, model = ac._resolve_auto(
            main_runtime={
                "provider": "official",
                "model": "MiniMax-M2.7",
                "base_url": "http://gateway.example.com/v1",
                "api_key": "jwt-device-test",
                "api_mode": "chat_completions",
            }
        )

    assert client is not None
    assert model == "MiniMax-M2.7"
    assert captured["provider"] == "official"
    assert captured["kwargs"].get("explicit_base_url") == "http://gateway.example.com/v1"
    # 短 TTL：不得把 runtime 里的旧 JWT 钉死传给 resolve
    assert captured["kwargs"].get("explicit_api_key") is None


def test_device_jwt_cache_key_changes_when_token_rotates(monkeypatch):
    """后台续期只改磁盘票时，cache key 必须跟着变，否则 call_llm 继续用过期客户端。"""
    from agent import auxiliary_client as ac

    monkeypatch.setattr(ac, "_persisted_main_runtime_cache_key", lambda: (
        "official",
        "MiniMax-M2.7",
        "",
        "",
        "",
        "",
    ))
    monkeypatch.setattr(ac, "_device_jwt_cache_fingerprint", lambda: "fp-old")
    k1 = ac._client_cache_key("auto", async_mode=False)
    monkeypatch.setattr(ac, "_device_jwt_cache_fingerprint", lambda: "fp-new")
    k2 = ac._client_cache_key("auto", async_mode=False)
    assert k1 != k2
    assert k1[-1] == "fp-old"
    assert k2[-1] == "fp-new"


def test_get_cached_client_rebuilds_after_device_jwt_rotation(monkeypatch):
    from agent import auxiliary_client as ac

    ac._client_cache.clear()
    monkeypatch.setattr(ac, "_persisted_main_runtime_cache_key", lambda: (
        "official",
        "MiniMax-M2.7",
        "",
        "",
        "",
        "",
    ))
    fps = iter(["fp-old", "fp-old", "fp-new", "fp-new"])
    monkeypatch.setattr(ac, "_device_jwt_cache_fingerprint", lambda: next(fps))

    clients = [MagicMock(name="c1"), MagicMock(name="c2")]
    builds = {"n": 0}

    def _fake_resolve(provider, model=None, async_mode=False, **kwargs):
        builds["n"] += 1
        return clients[builds["n"] - 1], "MiniMax-M2.7"

    monkeypatch.setattr(ac, "resolve_provider_client", _fake_resolve)

    c1, _ = ac._get_cached_client("auto", "MiniMax-M2.7")
    c1b, _ = ac._get_cached_client("auto", "MiniMax-M2.7")
    assert c1 is c1b
    assert builds["n"] == 1

    c2, _ = ac._get_cached_client("auto", "MiniMax-M2.7")
    assert c2 is clients[1]
    assert builds["n"] == 2
    ac._client_cache.clear()
