"""Env writes should only clear LLM derived state for provider credentials."""

from __future__ import annotations

import pytest

from hermes_cli.config import invalidate_llm_derived_state, save_env_value


def test_save_env_provider_key_clears_llm_state(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "hub"
    root.mkdir()
    (root / ".env").write_text("", encoding="utf-8")

    import runtime_paths as rp_mod

    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: root)
    monkeypatch.setenv("HUB_DATA_DIR", str(root))

    calls: list[int] = []
    monkeypatch.setattr(
        "hermes_cli.config.invalidate_llm_derived_state",
        lambda: calls.append(1),
    )

    save_env_value("MOARK_API_KEY", "sk-test")
    assert calls == [1]

    calls.clear()
    save_env_value("FIRECRAWL_API_KEY", "fc-test")
    assert calls == []
