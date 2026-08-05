from __future__ import annotations

import pytest

from core.platform.gateway_base_url import resolve_llm_gateway_base_url


def test_resolve_prefers_llm_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://gw:4000")
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "http://cs:8080")
    assert resolve_llm_gateway_base_url() == "http://gw:4000"


def test_resolve_falls_back_to_control_server(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    monkeypatch.setenv("CONTROL_SERVER_BASE_URL", "http://cs:8080")
    assert resolve_llm_gateway_base_url() == "http://cs:8080"


def test_resolve_empty_when_both_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_GATEWAY_BASE_URL", raising=False)
    monkeypatch.delenv("CONTROL_SERVER_BASE_URL", raising=False)
    assert resolve_llm_gateway_base_url() == ""
