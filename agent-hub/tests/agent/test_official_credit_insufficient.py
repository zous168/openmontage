"""LT-045.04：官方网关 402 → 会话内「算力点不足」文案（不重试透支）。"""
from __future__ import annotations

from agent.conversation_loop import (
    _billing_or_entitlement_message,
    _is_official_gateway_route,
)
from agent.i18n import t


def test_is_official_gateway_route_by_provider():
    assert _is_official_gateway_route("official", "") is True
    assert _is_official_gateway_route("openrouter", "") is False


def test_is_official_gateway_route_by_base_url(monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://127.0.0.1:4000")
    assert _is_official_gateway_route("openai", "http://127.0.0.1:4000") is True
    assert _is_official_gateway_route("openai", "https://openrouter.ai/api/v1") is False


def test_billing_message_official_uses_i18n():
    msg = _billing_or_entitlement_message(
        capability="model access",
        provider="official",
        base_url="http://gw",
        model="gpt-4o",
    )
    assert msg == t("gateway.credits.insufficient")
    assert "网关侧运行余额不足" in t("gateway.credits.insufficient", lang="zh")
    assert "Insufficient compute credits" in t(
        "gateway.credits.insufficient", lang="en"
    )


def test_billing_message_non_official_unchanged():
    msg = _billing_or_entitlement_message(
        capability="model access",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="gpt-4o",
    )
    assert "openrouter" in msg.lower() or "OpenRouter" in msg
    assert "gateway.credits.insufficient" not in msg


def test_assistant_credit_message_forces_zh_even_when_display_en(monkeypatch):
    from agent.credit_messages import official_credits_insufficient_for_assistant
    from agent.i18n import reset_language_cache

    monkeypatch.setenv("HERMES_LANGUAGE", "en")
    reset_language_cache()
    msg = official_credits_insufficient_for_assistant(
        "Insufficient compute credits (balance=-247, min=0)"
    )
    assert "网关侧运行余额不足" in msg
    assert "Insufficient compute credits. Please top up" not in msg
    assert "balance=-247" in msg
