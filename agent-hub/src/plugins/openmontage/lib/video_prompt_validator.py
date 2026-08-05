"""Validate UGC / reference-native video prompts before video_selector calls.

Used by tools/video/video_selector.py when ``prompt_profile="ugc_native"``.
Rules mirror ``skills/pipelines/explainer/asset-director.md`` (six-block table + Appendix A).
"""

from __future__ import annotations

import re
from typing import Any

UGC_NATIVE_MIN_PROMPT_CHARS = 180

_FORBIDDEN_SHORTHAND = (
    "same as above",
    "inherit previous prompt",
    "as above",
    "同上",
    "同前",
    "see previous",
    "continued from previous prompt",
)

_REQUIRED_CONTROL_PHRASES = (
    "real-time physics",
    "constant speed",
)

_ASPECT_IN_PROMPT = re.compile(
    r"\b(9:16|16:9|1:1)\b|"
    r"\b(vertical|horizontal|portrait|landscape)\b.*\b(video|frame|aspect|ratio|shot)\b|"
    r"\baspect ratio\b",
    re.IGNORECASE,
)

_TIMED_BEAT = re.compile(r"\[\s*\d{1,2}\s*:\s*\d{2}", re.IGNORECASE)

_FORM_STRATEGY = re.compile(
    r"\b(handheld|smartphone|phone footage|ugc|selfie|table pov|native (phone|capture|footage))\b",
    re.IGNORECASE,
)

_CLUTTER_LIGHT_NOISE = re.compile(
    r"\b(clutter|messy|room tone|noise floor|sensor grain|grain|ambient noise|"
    r"background noise|tungsten|daylight|window light|practical light)\b",
    re.IGNORECASE,
)

_NATIVE_IMPERFECTION = re.compile(
    r"\b(micro-?shake|handheld shake|focus breathing|uneven exposure|natural skin|"
    r"visible grain|native imperfection|sensor noise|slight blur)\b",
    re.IGNORECASE,
)

_FORBIDDEN_AESTHETIC_REQUESTS = (
    "cgi",
    "3d model",
    "virtual human",
    "anime style",
    "beauty filter",
    "skin smoothing",
    "gimbal smooth",
    "steadicam",
    "studio lighting",
    "commercial blockbuster",
    "zero noise",
    "pristine frame",
    "dreamlike bokeh",
    "plastic skin",
)


def validate_executable_video_prompt(
    prompt: str,
    *,
    aspect_ratio: str | None = None,
    max_words: int = 120,
) -> list[str]:
    """Validate compact single-action prompts for video_selector."""
    text = str(prompt or "").strip()
    errors: list[str] = []

    if len(text) < 80:
        errors.append(
            f"Executable prompt too short ({len(text)} chars). "
            "Include subject, one motion, scene, and camera blocks."
        )

    words = len(re.findall(r"\S+", text))
    if words > max_words:
        errors.append(
            f"Executable prompt too long ({words} words). Keep ≤ {max_words} words per clip."
        )

    lower = text.casefold()
    if _TIMED_BEAT.search(text):
        errors.append(
            "Executable prompts must not include [MM:SS-MM:SS] timeline beats. "
            "Use analysis_prompt for second-level timing; hard cuts belong in edit."
        )
    if "[cut" in lower or "hard cut" in lower:
        errors.append("Remove hard-cut markers from executable prompts — edit handles cuts.")

    if aspect_ratio and aspect_ratio not in text and not _ASPECT_IN_PROMPT.search(text):
        errors.append(f'Aspect ratio "{aspect_ratio}" must appear in the executable prompt.')

    if not _FORM_STRATEGY.search(text):
        errors.append("Missing capture mode (smartphone / handheld UGC).")

    if "real-time physics" not in lower and "constant speed" not in lower:
        errors.append('Include "real-time physics" or "constant speed" control phrase.')

    return errors


def validate_ugc_video_prompt(
    prompt: str,
    *,
    aspect_ratio: str | None = None,
) -> list[str]:
    """Return human-readable validation errors. Empty list means pass."""
    text = str(prompt or "").strip()
    errors: list[str] = []

    if len(text) < UGC_NATIVE_MIN_PROMPT_CHARS:
        errors.append(
            f"Prompt too short ({len(text)} chars). UGC native prompts must be "
            f"≥ {UGC_NATIVE_MIN_PROMPT_CHARS} chars with all six blocks spelled out."
        )

    lower = text.casefold()
    for phrase in _FORBIDDEN_SHORTHAND:
        if phrase.casefold() in lower:
            errors.append(f'Forbidden shorthand: "{phrase}". Restate all six blocks in full.')

    for phrase in _REQUIRED_CONTROL_PHRASES:
        if phrase.casefold() not in lower:
            errors.append(f'Missing required control phrase: "{phrase}".')

    has_aspect_in_prompt = bool(_ASPECT_IN_PROMPT.search(text))
    if aspect_ratio:
        if aspect_ratio not in text and not has_aspect_in_prompt:
            errors.append(
                f'Aspect ratio "{aspect_ratio}" must appear explicitly in the prompt (block 1).'
            )
    elif not has_aspect_in_prompt:
        errors.append(
            "Missing aspect ratio (block 1). Include e.g. 9:16 vertical or 16:9 horizontal."
        )

    if not _TIMED_BEAT.search(text):
        errors.append(
            "Missing second-level timed actions (block 4). "
            "Use [MM:SS-MM:SS] beats with durations."
        )

    if not _FORM_STRATEGY.search(text):
        errors.append(
            "Missing form strategy (block 3). State capture mode e.g. smartphone handheld UGC."
        )

    if not _CLUTTER_LIGHT_NOISE.search(text):
        errors.append(
            "Missing scene clutter / lighting / noise floor cues (block 2)."
        )

    if not _NATIVE_IMPERFECTION.search(text):
        errors.append(
            "Missing native imperfections (block 6). "
            "Include handheld micro-shake, grain, focus breathing, or natural skin texture."
        )

    for phrase in _FORBIDDEN_AESTHETIC_REQUESTS:
        if phrase.casefold() in lower:
            errors.append(
                f'Prompt requests forbidden aesthetic "{phrase}" (Appendix A). Rewrite with native alternatives.'
            )

    return errors


def validation_result(
    prompt: str,
    *,
    aspect_ratio: str | None = None,
) -> dict[str, Any]:
    """Structured result for tools and agents."""
    errors = validate_ugc_video_prompt(prompt, aspect_ratio=aspect_ratio)
    return {
        "valid": not errors,
        "errors": errors,
        "prompt_profile": "ugc_native",
    }
