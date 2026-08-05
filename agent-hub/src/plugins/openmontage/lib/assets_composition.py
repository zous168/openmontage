"""Resolve assets-stage composition strategy (UGC video vs static image + compose)."""

from __future__ import annotations

from typing import Any, Literal

AssetsCompositionStrategy = Literal["ugc_native", "static_composition"]

_STATIC_ALIASES = frozenset({"static_composition", "ffmpeg_still_loop", "image_ken_burns", "zero_key"})


def _normalize_strategy(raw: object) -> AssetsCompositionStrategy | None:
    if not isinstance(raw, str):
        return None
    key = raw.strip().lower()
    if key in _STATIC_ALIASES:
        return "static_composition"
    if key == "ugc_native":
        return "ugc_native"
    return None


def _proposal_assets_tools(proposal: dict[str, Any] | None) -> list[str]:
    if not proposal:
        return []
    plan = proposal.get("production_plan")
    if not isinstance(plan, dict):
        return []
    for stage in plan.get("stages") or []:
        if not isinstance(stage, dict):
            continue
        if stage.get("stage") == "assets":
            tools = stage.get("tools") or []
            return [str(t) for t in tools if t]
    return []


def resolve_assets_composition_strategy(
    *,
    production_inputs: dict[str, Any] | None = None,
    proposal: dict[str, Any] | None = None,
    force: AssetsCompositionStrategy | None = None,
) -> AssetsCompositionStrategy:
    """Single source of truth for reference-driven assets routing.

    Priority (highest first):
    1. Explicit ``force`` (tests / CLI)
    2. ``production_inputs.assets_video_strategy`` or ``forbid_video_selector``
    3. ``proposal.production_plan.assets_video_strategy``
    4. Proposal assets stage tool list excludes ``video_selector``
    5. ``static_composition_fallback_active()`` when no remote video provider
    """
    if force in {"ugc_native", "static_composition"}:
        return force

    inputs = production_inputs if isinstance(production_inputs, dict) else {}

    from_inputs = _normalize_strategy(inputs.get("assets_video_strategy"))
    if from_inputs:
        return from_inputs
    if inputs.get("forbid_video_selector") is True:
        return "static_composition"

    if proposal:
        plan = proposal.get("production_plan")
        if isinstance(plan, dict):
            from_proposal = _normalize_strategy(plan.get("assets_video_strategy"))
            if from_proposal:
                return from_proposal
        tools = _proposal_assets_tools(proposal)
        if tools and "video_selector" not in tools:
            return "static_composition"

    from plugins.openmontage.tools.video._shared import static_composition_fallback_active

    if static_composition_fallback_active():
        return "static_composition"
    return "ugc_native"


def strategy_metadata(strategy: AssetsCompositionStrategy) -> dict[str, Any]:
    if strategy == "static_composition":
        return {
            "assets_composition_strategy": "static_composition",
            "video_compose_strategy": "ffmpeg_still_loop",
            "pacing_style": "static_gen_unit",
            "forbid_video_selector": True,
        }
    return {
        "assets_composition_strategy": "ugc_native",
        "video_compose_strategy": None,
        "pacing_style": "executable_gen_unit",
        "forbid_video_selector": False,
    }
