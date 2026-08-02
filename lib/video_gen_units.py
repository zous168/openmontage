"""Video generation unit sizing for scene_plan (storyboard = one API clip)."""
from __future__ import annotations

from math import ceil
from typing import Any

DEFAULT_VIDEO_GEN_CLIP_SECONDS = 10.0
MIN_VIDEO_GEN_CLIP_SECONDS = 5.0
MAX_VIDEO_GEN_CLIP_SECONDS = 30.0


def resolve_video_gen_clip_duration(
    production_inputs: dict[str, Any] | None,
    *,
    default: float = DEFAULT_VIDEO_GEN_CLIP_SECONDS,
) -> float:
    """Read ``video_gen_clip_duration_seconds`` from project production_inputs."""
    if not production_inputs:
        return default
    raw = production_inputs.get("video_gen_clip_duration_seconds")
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return max(MIN_VIDEO_GEN_CLIP_SECONDS, min(MAX_VIDEO_GEN_CLIP_SECONDS, value))


def video_gen_unit_ranges(
    total_duration_seconds: float,
    clip_duration_seconds: float,
) -> list[tuple[float, float]]:
    """Split *total_duration_seconds* into [start, end) ranges per generation clip."""
    total = max(0.0, float(total_duration_seconds))
    clip = max(MIN_VIDEO_GEN_CLIP_SECONDS, float(clip_duration_seconds))
    if total <= 0:
        return [(0.0, clip)]

    ranges: list[tuple[float, float]] = []
    start = 0.0
    while start < total - 1e-6:
        end = min(total, start + clip)
        ranges.append((round(start, 3), round(end, 3)))
        if end >= total - 1e-6:
            break
        start = end
    return ranges or [(0.0, round(total, 3))]


def scene_count_for_duration(total_duration_seconds: float, clip_duration_seconds: float) -> int:
    """How many storyboard scenes (= video gen calls) for a timeline."""
    total = max(0.0, float(total_duration_seconds))
    clip = max(MIN_VIDEO_GEN_CLIP_SECONDS, float(clip_duration_seconds))
    if total <= 0:
        return 1
    return max(1, int(ceil(total / clip)))
