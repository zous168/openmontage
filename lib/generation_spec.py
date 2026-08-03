"""Assemble AI video generation prompts from ``video_analysis_brief`` scenes + generation defaults."""

from __future__ import annotations

import re
from typing import Any

from lib.video_gen_units import video_gen_unit_ranges

REVERSE_SEGMENT_SECONDS = 13.0
EXECUTABLE_MAX_WORDS = 120
EXECUTABLE_TARGET_WORDS = 85

_CUT_LINE = re.compile(r"\[cut[^\]]*\]", re.IGNORECASE)
_TIMED_RANGE = re.compile(r"\[\s*\d{1,2}\s*:\s*\d{2}[^\]]*\]", re.IGNORECASE)
_PAREN_METRICS = re.compile(
    r"\(~?\d+(?:\.\d+)?%?\s*frame width[^)]*\)|"
    r"\(\d+(?:\.\d+)?cm[^)]*\)|"
    r"duration\s+\d+(?:\.\d+)?s|"
    r"constant velocity|real-time physics|no time compression",
    re.IGNORECASE,
)
_BRAND_ZHUGE = re.compile(r"诸葛卧龙\s*")

PROFILE_LABELS: dict[str, dict[str, str]] = {
    "ugc_native": {
        "environment": "Scene clutter / lighting / noise floor",
        "capture_mode": "Form strategy",
        "timeline": "Second-level timed actions",
        "consistency": "Physics / speed control",
        "capture_character": "Native imperfections",
    },
    "reference_fidelity": {
        "environment": "Scene & lighting",
        "capture_mode": "Capture mode",
        "timeline": "Second-level visual, action & VFX timeline",
        "consistency": "Global DNA lock & control tokens",
        "capture_character": "Capture texture & micro-dynamics",
    },
    "cinematic": {
        "environment": "Environment & lighting",
        "capture_mode": "Camera approach",
        "timeline": "Shot timeline",
        "consistency": "Continuity & physics",
        "capture_character": "Image character",
    },
    "default": {
        "environment": "Environment",
        "capture_mode": "Capture mode",
        "timeline": "Timeline",
        "consistency": "Consistency",
        "capture_character": "Capture character",
    },
}


def canonical_generation_prompt_from_scene(
    scene: dict[str, Any], *, types: tuple[str, ...] = ("video", "image")
) -> str | None:
    """Return provider-ready prompt recorded on the scene for any visual type.

    ``required_assets[].description`` is the exact prompt text for
    ``source == "generate"`` assets. For ``video``, only provider-ready
    descriptions qualify (ugc_native_executable profile, "Aspect ratio:"
    header, or DNA-inheritance continuation); for ``image`` the description
    IS the prompt sent to the model and is returned verbatim.
    """
    for asset in scene.get("required_assets") or []:
        if not isinstance(asset, dict):
            continue
        if asset.get("type") not in types or asset.get("source") != "generate":
            continue
        desc = str(asset.get("description") or "").strip()
        if not desc:
            continue
        if asset.get("type") == "video":
            profile = str(asset.get("prompt_profile") or "").strip()
            if profile == "ugc_native_executable" or "Aspect ratio:" in desc:
                return desc
            if desc.startswith("[INHERIT DNA LOCK]"):
                return desc
            continue  # video description 非 provider-ready，跳过
        return desc  # image：description 即发送原文，原样返回
    return None


def canonical_video_prompt_from_scene(scene: dict[str, Any]) -> str | None:
    """Video-only wrapper — keeps reference_scene_plan sync behavior unchanged."""
    return canonical_generation_prompt_from_scene(scene, types=("video",))


def analysis_prompt_from_scene(scene: dict[str, Any]) -> str | None:
    """Return full reverse-engineered analysis prompt when stored on the scene."""
    stored = str(scene.get("analysis_prompt") or "").strip()
    if stored:
        return stored
    for asset in scene.get("required_assets") or []:
        if not isinstance(asset, dict):
            continue
        ap = str(asset.get("analysis_prompt") or "").strip()
        if ap:
            return ap
    return None


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def _sanitize_executable_clause(text: str) -> str:
    """Strip analysis-only tokens unsuitable for a single video-gen call."""
    cleaned = str(text or "").strip()
    cleaned = _CUT_LINE.sub("", cleaned)
    cleaned = _TIMED_RANGE.sub("", cleaned)
    cleaned = _BRAND_ZHUGE.sub("", cleaned)
    cleaned = _PAREN_METRICS.sub("", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    cleaned = re.sub(r"\s+([,.;])", r"\1", cleaned)
    cleaned = re.sub(r"\bwith\s*[,.;]?\s*$", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip(" ,.;")


def _simplified_subject(dna_lock: dict[str, Any] | None) -> str:
    raw = str((dna_lock or {}).get("subject") or "").strip()
    raw = _BRAND_ZHUGE.sub("", raw)
    if raw:
        return _sanitize_executable_clause(raw)
    return (
        "Red-manicured hands, yellow and green pepper-flatbread snack bags (matte plastic), "
        "golden crispy chips with visible pepper seasoning"
    )


def _simplified_scene(gen: dict[str, Any], dna_lock: dict[str, Any] | None) -> str:
    env = _as_dict(gen.get("environment"))
    setting = _sanitize_executable_clause(str(env.get("setting") or "Warm indoor snack desk"))
    lighting = _sanitize_executable_clause(
        str(env.get("lighting") or "Warm tungsten key from upper-left")
    )
    clutter = _sanitize_executable_clause(str(env.get("clutter_and_props") or ""))
    # Keep only anchor props — full prop lists overload video models.
    if clutter:
        anchors = []
        for token in ("woven mat", "bamboo basket", "calendar", "festive"):
            if token.casefold() in clutter.casefold():
                anchors.append(token)
        clutter = ", ".join(anchors) if anchors else "woven mat, festive desk props"
    else:
        scene_dna = _sanitize_executable_clause(str((dna_lock or {}).get("scene") or ""))
        clutter = scene_dna[:120] if scene_dna else "woven mat, bamboo basket, warm desk props"
    ambient = _sanitize_executable_clause(str(env.get("ambient_floor") or "subtle sensor grain"))
    return f"{setting}; {clutter}; {lighting}; {ambient}"


def _shot_hint_for_window(
    brief: dict[str, Any],
    start_seconds: float,
    end_seconds: float,
) -> tuple[str, str]:
    """Return (shot_size_phrase, camera_phrase) for a time window."""
    ref_scenes = ((brief.get("structure_analysis") or {}).get("scenes") or [])
    mid = (start_seconds + end_seconds) / 2
    match = None
    for scene in ref_scenes:
        if not isinstance(scene, dict):
            continue
        s0 = float(scene.get("start_time", scene.get("start_seconds", 0)))
        s1 = float(scene.get("end_time", scene.get("end_seconds", s0)))
        if s0 <= mid < s1:
            match = scene
            break
    sl = _as_dict((match or {}).get("shot_language"))
    shot = str(sl.get("shot_size") or "close_up").replace("_", " ")
    if "extreme" in shot:
        shot = "extreme close-up"
    elif shot == "close up":
        shot = "close-up"
    movement = str(sl.get("camera_movement") or "handheld_static").replace("_", " ")
    if movement in {"handheld static", "handheld"}:
        camera = "Handheld smartphone POV with slight micro-shake"
    elif "dolly" in movement:
        camera = "Slow handheld push-in, top-down product framing"
    else:
        camera = f"Handheld {movement} smartphone POV"
    return shot, camera


def _rank_action_beats(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    priority = {"object_interaction": 0, "action": 1, "camera": 2, "micro_motion": 3, "hold": 4}
    action_beats = [
        b for b in beats
        if str(b.get("kind") or "").strip().lower() not in {"cut", "transition", "overlay", "vfx"}
    ]
    return sorted(
        action_beats,
        key=lambda b: (
            priority.get(str(b.get("kind") or "action"), 9),
            float(b.get("start_seconds", 0)),
        ),
    )


def _motion_from_beats(beats: list[dict[str, Any]]) -> str:
    ranked = _rank_action_beats(beats)
    if not ranked:
        return "Single continuous product action with natural hand movement."
    desc = _sanitize_executable_clause(str(ranked[0].get("description") or ""))
    desc = re.sub(r"\s+with\s*;\s*", "; ", desc)
    desc = re.sub(r"\s+with\s*$", "", desc, flags=re.IGNORECASE)
    if not desc:
        return "Single continuous product action with natural hand movement."
    return desc.rstrip(".") + "."


def _motion_montage_from_beats(
    beats: list[dict[str, Any]],
    *,
    max_clauses: int = 4,
) -> str:
    """Summarize multiple beats as one montage line (no timestamps) for ~10s gen units."""
    ranked = _rank_action_beats(beats)
    clauses: list[str] = []
    for beat in ranked[:max_clauses]:
        desc = _sanitize_executable_clause(str(beat.get("description") or ""))
        desc = re.sub(r"\s+with\s*;\s*", "; ", desc)
        desc = re.sub(r"\s+with\s*$", "", desc, flags=re.IGNORECASE)
        if desc:
            clauses.append(desc.rstrip("."))
    if not clauses:
        return "Single continuous product action with natural hand movement."
    if len(clauses) == 1:
        return clauses[0] + "."
    return "Fast-paced UGC montage: " + "; ".join(clauses) + "."


def compile_executable_prompt(
    brief: dict[str, Any],
    start_seconds: float,
    end_seconds: float,
    *,
    establish_dna: bool = False,
    inherit_dna: bool = False,
    beats: list[dict[str, Any]] | None = None,
) -> str:
    """Compile a single-action, provider-ready prompt (~80–120 words).

    Full reverse-engineered timelines belong in ``prompt_for_time_range`` /
    ``analysis_prompt`` — not in video_selector payloads.
    """
    gen = _as_dict(brief.get("generation"))
    lock = get_dna_lock(brief)
    delivery = _as_dict(gen.get("delivery"))
    aspect = str(delivery.get("aspect_ratio") or "9:16").strip()
    orient = str(delivery.get("orientation") or "vertical").strip()
    capture_mode = str(delivery.get("capture_mode") or "").strip()
    if not capture_mode:
        capture_mode = "One-hand smartphone POV, native snack UGC demo"

    window_beats = beats if beats is not None else _beats_in_range(
        _collect_scene_beats(brief), start_seconds, end_seconds
    )
    action_beats = _rank_action_beats(window_beats)
    window_seconds = max(0.0, float(end_seconds) - float(start_seconds))
    shot, camera = _shot_hint_for_window(brief, start_seconds, end_seconds)
    if window_seconds > 4.0 and len(action_beats) > 1:
        motion = _motion_montage_from_beats(action_beats)
    else:
        motion = _motion_from_beats(action_beats)
    subject = _simplified_subject(lock)
    scene = _simplified_scene(gen, lock)

    lines = [
        f"Aspect ratio: {aspect} {orient}.",
        f"Capture: {_sanitize_executable_clause(capture_mode)}.",
        f"Subject: {subject}.",
        f"Motion: {motion}",
        f"Scene: {scene}.",
        f"Camera: {camera}; {shot}; shallow depth of field.",
    ]
    if inherit_dna and not establish_dna:
        lines.append(
            "Continuity: match prior clip — same hands, packaging colors, desk props, and warm grade."
        )
    lines.append(
        "Real-time physics, constant speed, no burned-in subtitles or logos, natural sensor grain."
    )
    prompt = "\n\n".join(lines)
    words = _word_count(prompt)
    if words > EXECUTABLE_MAX_WORDS:
        # Drop continuity line first, then trim scene clutter.
        compact = "\n\n".join(lines[:5] + lines[-1:])
        if _word_count(compact) > EXECUTABLE_MAX_WORDS:
            compact = "\n\n".join(lines[:4] + [lines[-1]])
        prompt = compact
    return prompt


def _format_timestamp(seconds: float) -> str:
    total = max(0.0, float(seconds))
    minutes = int(total // 60)
    secs = total - minutes * 60
    if abs(secs - round(secs)) < 1e-6:
        return f"{minutes:02d}:{int(round(secs)):02d}"
    return f"{minutes:02d}:{secs:04.1f}"


def format_timed_action_range(start_seconds: float, end_seconds: float) -> str:
    """Return ``[MM:SS-MM:SS]`` range label."""
    return f"[{_format_timestamp(start_seconds)}-{_format_timestamp(end_seconds)}]"


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _collect_scene_beats(brief: dict[str, Any]) -> list[dict[str, Any]]:
    scenes = ((brief.get("structure_analysis") or {}).get("scenes") or [])
    beats: list[dict[str, Any]] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        for beat in scene.get("beats") or []:
            if isinstance(beat, dict):
                beats.append(beat)
    beats.sort(key=lambda b: float(b.get("start_seconds", 0)))
    return beats


def _build_spec_from_brief(brief: dict[str, Any]) -> dict[str, Any] | None:
    """Synthesize a virtual generation spec from ``generation`` + scene beats."""
    gen = brief.get("generation")
    if not isinstance(gen, dict):
        return None
    duration = float((brief.get("source") or {}).get("duration_seconds") or 0)
    beats = _collect_scene_beats(brief)
    if not beats and not gen:
        return None
    lock = get_dna_lock(brief) or {}
    control = str(gen.get("control_tokens") or lock.get("control_tokens") or "").strip()
    segment: dict[str, Any] = {
        "segment_index": 0,
        "start_seconds": 0,
        "end_seconds": duration or max((float(b.get("end_seconds", 0)) for b in beats), default=0),
        "dna_inheritance": "establish",
        "delivery": gen.get("delivery"),
        "environment": gen.get("environment"),
        "timeline": beats,
        "capture_character": gen.get("capture_character"),
        "control_tokens": control or None,
    }
    if control or lock:
        segment["consistency"] = {
            "physics_tokens": control,
            "subject_dna": str(lock.get("subject") or "").strip() or None,
            "scene_dna": str(lock.get("scene") or "").strip() or None,
        }
    return {
        "prompt_profile": gen.get("prompt_profile") or "default",
        "segments": [segment],
    }


def get_generation_spec(brief: dict[str, Any]) -> dict[str, Any] | None:
    """Return generation spec from brief — legacy ``generation_spec`` or synthesized from scenes."""
    legacy = brief.get("generation_spec")
    if isinstance(legacy, dict):
        return legacy
    return _build_spec_from_brief(brief)


def get_dna_lock(brief: dict[str, Any]) -> dict[str, Any] | None:
    custom = ((brief.get("replication_guidance") or {}).get("playbook_customizations") or {})
    lock = custom.get("dna_lock")
    return lock if isinstance(lock, dict) else None


def _environment_text(environment: dict[str, Any]) -> str:
    parts = [
        str(environment.get("setting") or "").strip(),
        str(environment.get("clutter_and_props") or "").strip(),
        str(environment.get("lighting") or "").strip(),
        str(environment.get("ambient_floor") or "").strip(),
        str(environment.get("grade_lut") or "").strip(),
    ]
    return "; ".join(p for p in parts if p)


def _format_beat_line(beat: dict[str, Any]) -> str:
    start = beat.get("start_seconds", 0)
    end = beat.get("end_seconds", start)
    desc = str(beat.get("description") or "").strip()
    kind = str(beat.get("kind") or "action").strip()
    prefix = format_timed_action_range(start, end)
    if kind in {"cut", "transition", "overlay", "vfx"}:
        return f"{prefix} [{kind}] {desc}".strip()
    overlay = beat.get("overlay_spec")
    if isinstance(overlay, dict) and overlay:
        coords = ", ".join(
            f"{k}={overlay[k]}"
            for k in ("x_pct", "y_pct", "width_pct", "height_pct")
            if overlay.get(k) is not None
        )
        extra = f" @ [{coords}]" if coords else ""
        return f"{prefix}{extra} {desc}".strip()
    return f"{prefix} {desc}".strip()


def _consistency_text(
    consistency: dict[str, Any],
    *,
    dna_lock: dict[str, Any] | None,
) -> str:
    parts: list[str] = []
    physics = str(consistency.get("physics_tokens") or "").strip()
    if physics:
        parts.append(physics)
    subject = str(consistency.get("subject_dna") or "").strip()
    scene = str(consistency.get("scene_dna") or "").strip()
    if not subject and dna_lock:
        subject = str(dna_lock.get("subject") or "").strip()
    if not scene and dna_lock:
        scene = str(dna_lock.get("scene") or "").strip()
    if subject:
        parts.append(f"Subject DNA: {subject}")
    if scene:
        parts.append(f"Scene DNA: {scene}")
    continuity = str(consistency.get("continuity_from_previous") or "").strip()
    if continuity:
        parts.append(continuity)
    anchors = consistency.get("object_anchors") or []
    if isinstance(anchors, list):
        for anchor in anchors:
            if not isinstance(anchor, dict):
                continue
            name = str(anchor.get("name") or "object").strip()
            bits = [
                str(anchor.get(k) or "").strip()
                for k in ("absolute_size", "screen_share", "material", "contact", "shadow", "notes")
                if str(anchor.get(k) or "").strip()
            ]
            if bits:
                parts.append(f"{name}: {', '.join(bits)}")
    return ". ".join(parts)


def _vfx_overlay_lines(overlays: list[dict[str, Any]]) -> list[str]:
    lines: list[str] = []
    for layer in overlays:
        kind = str(layer.get("kind") or "graphic").replace("_", " ")
        notes = str(layer.get("notes") or "").strip()
        placement = _as_dict(layer.get("placement"))
        place_bits = [
            f"{k}={placement[k]}"
            for k in ("x_pct", "y_pct", "width_pct", "height_pct", "anchor")
            if placement.get(k) is not None
        ]
        place = f" @ {', '.join(place_bits)}" if place_bits else ""
        anim = str(layer.get("animation") or "").strip()
        start = layer.get("start_seconds")
        end = layer.get("end_seconds")
        timing = ""
        if start is not None and end is not None:
            timing = f"{format_timed_action_range(start, end)} "
        chunk = f"{timing}{kind}{place}"
        if anim:
            chunk += f" ({anim})"
        if notes:
            chunk += f" — {notes}"
        lines.append(chunk.strip())
    return lines


def assemble_segment_prompt(
    segment: dict[str, Any],
    *,
    dna_lock: dict[str, Any] | None = None,
    prompt_profile: str = "default",
) -> str:
    """Render one generation segment into a provider-ready prompt string."""
    labels = PROFILE_LABELS.get(prompt_profile, PROFILE_LABELS["default"])
    lines: list[str] = []

    inheritance = str(segment.get("dna_inheritance") or "establish").strip().lower()
    if inheritance == "inherit":
        lines.append("[INHERIT DNA LOCK]")

    delivery = _as_dict(segment.get("delivery"))
    aspect = str(delivery.get("aspect_ratio") or "").strip()
    capture_mode = str(delivery.get("capture_mode") or "").strip()
    if aspect:
        orient = str(delivery.get("orientation") or "").strip()
        suffix = f" {orient}" if orient else ""
        lines.append(f"Aspect ratio: {aspect}{suffix}.")
    if capture_mode:
        lines.append(f"{labels['capture_mode']}: {capture_mode}")

    env_text = _environment_text(_as_dict(segment.get("environment")))
    if env_text:
        lines.append(f"{labels['environment']}: {env_text}")

    beats = [b for b in (segment.get("timeline") or []) if isinstance(b, dict)]
    if beats:
        lines.append(f"{labels['timeline']}:")
        lines.extend(f"- {_format_beat_line(b)}" for b in beats)

    consistency_text = _consistency_text(_as_dict(segment.get("consistency")), dna_lock=dna_lock)
    if consistency_text:
        lines.append(f"{labels['consistency']}: {consistency_text}")

    capture_notes = str(_as_dict(segment.get("capture_character")).get("notes") or "").strip()
    if capture_notes:
        lines.append(f"{labels['capture_character']}: {capture_notes}")

    edit_camera = segment.get("edit_camera")
    if isinstance(edit_camera, dict):
        edit_notes = str(edit_camera.get("notes") or "").strip()
        if edit_notes:
            lines.append(f"Edit / camera: {edit_notes}")
    elif isinstance(edit_camera, str) and edit_camera.strip():
        lines.append(f"Edit / camera: {edit_camera.strip()}")

    overlays = segment.get("overlays")
    overlay_list = [o for o in overlays if isinstance(o, dict)] if isinstance(overlays, list) else []
    overlay_lines = _vfx_overlay_lines(overlay_list)
    if overlay_lines:
        lines.append("VFX overlays:")
        lines.extend(f"- {line}" for line in overlay_lines)

    audio = _as_dict(segment.get("audio"))
    audio_bits = [
        str(audio.get("micro_acoustics") or "").strip(),
        str(audio.get("room_acoustics") or "").strip(),
        str(audio.get("lip_sync_declaration") or "").strip(),
        str(audio.get("continuity_note") or "").strip(),
        str(audio.get("notes") or "").strip(),
    ]
    audio_text = " ".join(b for b in audio_bits if b)
    if audio_text:
        lines.append(f"Audio: {audio_text}")

    tokens = str(segment.get("control_tokens") or "").strip()
    if tokens:
        lines.append(f"Control tokens: {tokens}")

    return "\n\n".join(lines)


def _beats_in_range(
    beats: list[dict[str, Any]],
    start_seconds: float,
    end_seconds: float,
) -> list[dict[str, Any]]:
    """Return beats overlapping ``[start_seconds, end_seconds)``, clipped to the window."""
    start = float(start_seconds)
    end = float(end_seconds)
    clipped: list[dict[str, Any]] = []
    for beat in beats:
        bs = float(beat.get("start_seconds", 0))
        be = float(beat.get("end_seconds", bs))
        if be <= start or bs >= end:
            continue
        item = dict(beat)
        item["start_seconds"] = round(max(bs, start), 3)
        item["end_seconds"] = round(min(be, end), 3)
        clipped.append(item)
    return clipped


def prompt_for_time_range(
    brief: dict[str, Any],
    start_seconds: float,
    end_seconds: float,
    *,
    establish_dna: bool | None = None,
) -> str | None:
    """Assemble a reverse-engineered video-gen prompt for a storyboard time window."""
    gen = brief.get("generation")
    if not isinstance(gen, dict):
        return None
    spec = get_generation_spec(brief)
    profile = str((spec or {}).get("prompt_profile") or gen.get("prompt_profile") or "default")
    lock = get_dna_lock(brief)
    control = str(gen.get("control_tokens") or (lock or {}).get("control_tokens") or "").strip()

    start = float(start_seconds)
    end = float(end_seconds)
    beats = _beats_in_range(_collect_scene_beats(brief), start, end)

    ref_duration = float((brief.get("source") or {}).get("duration_seconds") or 0)
    if end > ref_duration:
        hold_from = max(start, beats[-1]["end_seconds"] if beats else start)
        if hold_from < end:
            beats.append({
                "start_seconds": round(hold_from, 3),
                "end_seconds": round(end, 3),
                "kind": "hold",
                "description": (
                    "Continue prior hero composition with subtle handheld micro-shake; "
                    "maintain exact product, desk props, and lighting; real-time physics, no dead frames."
                ),
            })

    if not beats:
        beats = [{
            "start_seconds": round(start, 3),
            "end_seconds": round(end, 3),
            "kind": "action",
            "description": "Maintain reference scene DNA for this window.",
        }]

    inherit = (establish_dna is False) or (establish_dna is None and start > 0)
    consistency: dict[str, Any] = {}
    if control or lock:
        consistency = {
            "physics_tokens": control,
            "subject_dna": str((lock or {}).get("subject") or "").strip() or None,
            "scene_dna": str((lock or {}).get("scene") or "").strip() or None,
        }
    if inherit:
        consistency["continuity_from_previous"] = (
            "Inherit global DNA lock; continue seamlessly from previous clip's last frame and room tone."
        )

    segment: dict[str, Any] = {
        "segment_index": 0,
        "start_seconds": start,
        "end_seconds": end,
        "dna_inheritance": "establish" if not inherit else "inherit",
        "delivery": gen.get("delivery"),
        "environment": gen.get("environment"),
        "timeline": beats,
        "capture_character": gen.get("capture_character"),
        "control_tokens": control or None,
    }
    if consistency:
        segment["consistency"] = consistency

    if not inherit:
        segment["audio"] = {
            "lip_sync_declaration": "lip-sync N/A (product-only, no face)",
            "continuity_note": "room tone continues seamlessly",
            "notes": "No burned-in subtitles in generated picture; narration added at edit.",
        }

    return assemble_segment_prompt(segment, dna_lock=lock, prompt_profile=profile)


def segment_prompt_from_brief(
    brief: dict[str, Any],
    segment_index: int,
) -> str | None:
    """Return assembled prompt for ``segment_index`` from brief scenes + generation defaults."""
    spec = get_generation_spec(brief)
    if not spec:
        return None
    profile = str(spec.get("prompt_profile") or "default").strip()
    lock = get_dna_lock(brief)

    for segment in spec.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        if int(segment.get("segment_index", -1)) != segment_index:
            continue
        cached = str(segment.get("assembled_prompt") or "").strip()
        if cached:
            return cached
        return assemble_segment_prompt(segment, dna_lock=lock, prompt_profile=profile)
    return None


def find_segment_for_time(spec: dict[str, Any], time_seconds: float) -> dict[str, Any] | None:
    """Pick the generation segment covering ``time_seconds`` (half-open interval)."""
    t = float(time_seconds)
    for segment in spec.get("segments") or []:
        if not isinstance(segment, dict):
            continue
        start = float(segment.get("start_seconds", 0))
        end = float(segment.get("end_seconds", start))
        if start <= t < end:
            return segment
    segments = [s for s in (spec.get("segments") or []) if isinstance(s, dict)]
    return segments[-1] if segments else None


def build_persisted_generation_spec(
    brief: dict[str, Any],
    *,
    chunk_seconds: float = REVERSE_SEGMENT_SECONDS,
) -> dict[str, Any] | None:
    """Build ``generation_spec`` with per-segment ``assembled_prompt`` for the reference video."""
    gen = brief.get("generation")
    if not isinstance(gen, dict):
        return None
    duration = float((brief.get("source") or {}).get("duration_seconds") or 0)
    if duration <= 0:
        return None
    profile = str(gen.get("prompt_profile") or "ugc_native").strip()
    lock = get_dna_lock(brief) or {}
    control = str(gen.get("control_tokens") or lock.get("control_tokens") or "").strip()
    all_beats = _collect_scene_beats(brief)
    ranges = video_gen_unit_ranges(duration, chunk_seconds)

    segments: list[dict[str, Any]] = []
    for index, (start, end) in enumerate(ranges):
        inherit = index > 0
        beats = _beats_in_range(all_beats, start, end)
        if end > duration:
            hold_from = max(start, beats[-1]["end_seconds"] if beats else start)
            if hold_from < end:
                beats.append({
                    "start_seconds": round(hold_from, 3),
                    "end_seconds": round(end, 3),
                    "kind": "hold",
                    "description": (
                        "Continue prior composition; subtle handheld micro-shake; "
                        "real-time physics, no dead frames."
                    ),
                })
        consistency: dict[str, Any] = {}
        if control or lock:
            consistency = {
                "physics_tokens": control,
                "subject_dna": str(lock.get("subject") or "").strip() or None,
                "scene_dna": str(lock.get("scene") or "").strip() or None,
            }
        if inherit:
            consistency["continuity_from_previous"] = (
                "Inherit global DNA lock; continue seamlessly from previous segment's "
                "last frame and room tone."
            )
        segment: dict[str, Any] = {
            "segment_index": index,
            "start_seconds": start,
            "end_seconds": end,
            "dna_inheritance": "inherit" if inherit else "establish",
            "delivery": gen.get("delivery"),
            "environment": gen.get("environment"),
            "timeline": beats,
            "capture_character": gen.get("capture_character"),
            "control_tokens": control or None,
        }
        if consistency:
            segment["consistency"] = consistency
        if not inherit:
            segment["audio"] = {
                "lip_sync_declaration": "lip-sync N/A (product-only, no face)",
                "continuity_note": "room tone continues seamlessly",
                "notes": "Pure picture reverse-engineering; exclude burn-in subtitles/watermarks.",
            }
        segment["assembled_prompt"] = assemble_segment_prompt(
            segment,
            dna_lock=lock,
            prompt_profile=profile,
        )
        segments.append(segment)

    return {
        "prompt_profile": profile,
        "segmentation": {
            "chunk_seconds": chunk_seconds,
            "rule": "reverse_engineering_fixed_chunk",
            "source": "反推视频提示词.md",
        },
        "segments": segments,
    }


def attach_generation_spec_to_brief(
    brief: dict[str, Any],
    *,
    chunk_seconds: float = REVERSE_SEGMENT_SECONDS,
) -> dict[str, Any]:
    """Attach or refresh ``generation_spec`` on a video_analysis_brief dict."""
    spec = build_persisted_generation_spec(brief, chunk_seconds=chunk_seconds)
    if spec:
        brief["generation_spec"] = spec
        meta = brief.setdefault("_analysis_meta", {})
        steps = meta.setdefault("steps_completed", [])
        if "generation_spec_assembled" not in steps:
            steps.append("generation_spec_assembled")
    return brief
