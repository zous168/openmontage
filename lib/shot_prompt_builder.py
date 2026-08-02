"""Shot prompt builder — converts structured shot language into provider-optimized prompts.

Uses a 5-layer framework based on professional cinematography prompting research:
  Layer 1: Camera (lens, depth of field)
  Layer 2: Movement (shot size, camera movement)
  Layer 3: Subject (description + texture keywords)
  Layer 4: Lighting (lighting key, color temperature)
  Layer 5: Style (adapted from playbook, not verbatim)

This replaces the old approach of prepending a fixed playbook image_prompt_prefix
to every scene description, which made all scenes look the same.
"""

from __future__ import annotations

import re
from typing import Any


# Mapping from shot_language enums to natural language for prompting
_SHOT_SIZE_PHRASES = {
    "extreme_wide": "extreme wide shot showing vast environment",
    "wide": "wide shot capturing full scene",
    "medium_wide": "medium-wide shot framing subject with surroundings",
    "medium": "medium shot from waist up",
    "medium_close": "medium close-up from chest up",
    "close_up": "close-up focusing on face or detail",
    "extreme_close_up": "extreme close-up on fine detail",
    "over_shoulder": "over-the-shoulder perspective",
    "insert": "insert shot of specific detail",
    "establishing": "establishing shot setting the location",
}

_MOVEMENT_PHRASES = {
    "static": "locked-off static camera",
    "pan_left": "smooth pan to the left",
    "pan_right": "smooth pan to the right",
    "tilt_up": "gentle tilt upward",
    "tilt_down": "gentle tilt downward",
    "dolly_in": "slow dolly in toward subject",
    "dolly_out": "slow dolly out from subject",
    "tracking_left": "tracking shot moving left alongside subject",
    "tracking_right": "tracking shot moving right alongside subject",
    "crane_up": "crane shot rising upward",
    "crane_down": "crane shot descending",
    "handheld": "handheld camera with natural movement",
    "steadicam": "smooth steadicam following movement",
    "whip_pan": "fast whip pan",
    "orbital": "orbital camera circling subject",
    "zoom_in": "slow zoom in",
    "zoom_out": "slow zoom out",
    "rack_focus": "rack focus shift between foreground and background",
}

_LIGHTING_PHRASES = {
    "high_key": "bright high-key lighting, minimal shadows",
    "low_key": "dramatic low-key lighting with deep shadows",
    "natural": "natural ambient lighting",
    "golden_hour": "warm golden hour sunlight",
    "blue_hour": "cool blue hour twilight",
    "tungsten_warm": "warm tungsten interior lighting",
    "neon": "neon-lit with vibrant color spill",
    "silhouette": "backlit silhouette",
    "rim_lit": "rim lighting highlighting edges",
    "volumetric": "volumetric light with visible rays",
    "overcast_soft": "soft overcast diffused light",
}

_DOF_PHRASES = {
    "shallow": "shallow depth of field with bokeh",
    "medium": "medium depth of field",
    "deep": "deep focus with everything sharp",
}

_COLOR_TEMP_PHRASES = {
    "cool": "cool blue-toned color palette",
    "neutral": "neutral balanced colors",
    "warm": "warm amber-toned color palette",
    "mixed": "mixed color temperatures for contrast",
}


def build_shot_prompt(
    scene: dict[str, Any],
    style_context: dict[str, Any] | None = None,
) -> str:
    """Convert a scene with structured shot language into a generation prompt.

    Args:
        scene: Scene dict from scene_plan (with shot_language, description,
               texture_keywords, etc.)
        style_context: Optional playbook-derived style info with keys like
                       'generation_prefix', 'visual_language', 'mood'.

    Returns:
        A natural-language prompt optimized for image/video generation.
    """
    sl = scene.get("shot_language", {})
    layers: list[str] = []

    # Layer 1: Camera — lens and depth of field
    camera_parts = []
    if sl.get("lens_mm"):
        camera_parts.append(f"{sl['lens_mm']}mm lens")
    if sl.get("depth_of_field"):
        camera_parts.append(_DOF_PHRASES.get(sl["depth_of_field"], ""))
    if camera_parts:
        layers.append(", ".join(filter(None, camera_parts)))

    # Layer 2: Movement — shot size and camera movement
    movement_parts = []
    if sl.get("shot_size"):
        movement_parts.append(_SHOT_SIZE_PHRASES.get(sl["shot_size"], sl["shot_size"]))
    if sl.get("camera_movement") and sl["camera_movement"] != "static":
        movement_parts.append(_MOVEMENT_PHRASES.get(sl["camera_movement"], sl["camera_movement"]))
    if movement_parts:
        layers.append(", ".join(movement_parts))

    # Layer 3: Subject — the scene description + texture keywords
    description = scene.get("description", "")
    texture = scene.get("texture_keywords", [])
    subject_parts = [description]
    if texture:
        subject_parts.append(", ".join(texture))
    layers.append(". ".join(filter(None, subject_parts)))

    # Layer 4: Lighting — lighting key and color temperature
    lighting_parts = []
    if sl.get("lighting_key"):
        lighting_parts.append(_LIGHTING_PHRASES.get(sl["lighting_key"], sl["lighting_key"]))
    if sl.get("color_temperature"):
        lighting_parts.append(_COLOR_TEMP_PHRASES.get(sl["color_temperature"], ""))
    if lighting_parts:
        layers.append(", ".join(filter(None, lighting_parts)))

    # Layer 5: Style — adapted from playbook (NOT verbatim prefix)
    if style_context:
        mood = style_context.get("mood", "")
        visual_lang = style_context.get("visual_language", {})
        style_hint = visual_lang.get("aesthetic", "") or mood
        if style_hint:
            layers.append(f"Style: {style_hint}")

    return ". ".join(filter(None, layers))


def build_batch_prompts(
    scenes: list[dict[str, Any]],
    style_context: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """Build prompts for all visual scenes in a scene plan.

    Returns list of {scene_id, prompt} dicts.
    """
    results = []
    for scene in scenes:
        # Skip non-visual scene types
        scene_type = scene.get("type", "")
        if scene_type in ("transition",):
            continue
        prompt = build_shot_prompt(scene, style_context)
        results.append({
            "scene_id": scene.get("id", "unknown"),
            "prompt": prompt,
            "hero_moment": scene.get("hero_moment", False),
        })
    return results


def scene_plan_index_from_id(scene_id: str | None) -> int | None:
    """Map scene_plan ids like sc1 / scene-3 to zero-based reference indices."""
    if not scene_id:
        return None
    sid = str(scene_id).strip()
    m = re.match(r"^sc(\d+)$", sid, re.IGNORECASE)
    if m:
        return int(m.group(1)) - 1
    m = re.search(r"(\d+)\s*$", sid)
    if m:
        return int(m.group(1)) - 1
    return None


def _dedupe_prompt_parts(parts: list[str]) -> str:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in parts:
        p = str(raw or "").strip().strip(".")
        if not p:
            continue
        key = p.casefold()
        if key in seen:
            continue
        seen.add(key)
        ordered.append(p)
    return ". ".join(ordered)


def build_scene_storyboard_prompt(
    scene: dict[str, Any],
    *,
    reference_scene: dict[str, Any] | None = None,
    reference_keyframe: dict[str, Any] | None = None,
    style_context: dict[str, Any] | None = None,
) -> str:
    """Storyboard prompt from scene_plan, optionally enriched by reference analysis."""
    parts: list[str] = []

    intent = str(scene.get("shot_intent") or "").strip()
    description = str(scene.get("description") or "").strip()
    if intent:
        parts.append(f"Intent: {intent}")
    elif description and len(description) >= 8:
        parts.append(description)

    ref_visual = ""
    if reference_scene:
        ref_visual = str(reference_scene.get("description") or "").strip()
    kf_note = str((reference_keyframe or {}).get("description") or "").strip()
    if kf_note:
        if ref_visual and kf_note.casefold() not in ref_visual.casefold():
            ref_visual = f"{ref_visual}. Keyframe: {kf_note}"
        elif not ref_visual:
            ref_visual = kf_note
    if ref_visual:
        parts.append(ref_visual)

    for asset in scene.get("required_assets") or []:
        if not isinstance(asset, dict):
            continue
        asset_desc = str(asset.get("description") or "").strip()
        if asset_desc:
            parts.append(asset_desc)

    overlay = str(scene.get("overlay_notes") or "").strip()
    if overlay:
        parts.append(f'On-screen text: "{overlay}"')

    shot = build_shot_prompt(scene, style_context).strip()
    if shot:
        parts.append(shot)

    framing = str(scene.get("framing") or "").strip()
    movement = str(scene.get("movement") or "").strip()
    if framing:
        parts.append(framing)
    if movement:
        parts.append(movement)

    return _dedupe_prompt_parts(parts)
