"""Tests for assets composition strategy resolution."""

from __future__ import annotations

from lib.assets_composition import resolve_assets_composition_strategy


def test_explicit_production_inputs_static():
    assert (
        resolve_assets_composition_strategy(
            production_inputs={"assets_video_strategy": "ffmpeg_still_loop"},
        )
        == "static_composition"
    )


def test_proposal_assets_tools_without_video_selector():
    proposal = {
        "production_plan": {
            "stages": [
                {"stage": "assets", "tools": ["tts_selector", "image_selector", "zhipu_image"]},
            ],
        },
    }
    assert (
        resolve_assets_composition_strategy(proposal=proposal)
        == "static_composition"
    )


def test_force_ugc_native_overrides_fallback(monkeypatch):
    monkeypatch.setattr(
        "tools.video._shared.static_composition_fallback_active",
        lambda: True,
    )
    assert (
        resolve_assets_composition_strategy(force="ugc_native")
        == "ugc_native"
    )


def test_auto_static_when_no_remote(monkeypatch):
    monkeypatch.setattr(
        "tools.video._shared.static_composition_fallback_active",
        lambda: True,
    )
    assert resolve_assets_composition_strategy() == "static_composition"
