"""Normalize edit_decisions into a Remotion-aligned composition timeline.

Backlot UI and Remotion Studio should derive nodes, layer order, and timing
from the same props contract (Explainer.tsx + Root.tsx calculateMetadata).
"""

from __future__ import annotations

import copy
from typing import Any


def normalize_composition_props(edit: dict[str, Any]) -> dict[str, Any]:
    """Return the props object Remotion receives (before path normalization)."""
    props = copy.deepcopy(edit)
    overlays = props.get("overlays") or []
    meta_overlays = (props.get("metadata") or {}).get("remotion_overlays") or []
    if not overlays and meta_overlays:
        props["overlays"] = meta_overlays
    captions = props.get("captions") or []
    meta_captions = (props.get("metadata") or {}).get("remotion_captions") or []
    if not captions and meta_captions:
        props["captions"] = meta_captions
    props.setdefault("cuts", [])
    props.setdefault("captions", [])
    props.setdefault("audio", {})
    return props


def _cut_sequence_name(cut: dict[str, Any]) -> str:
    source = str(cut.get("source") or "")
    file = source.rsplit("/", 1)[-1] if source else ""
    cut_id = cut.get("id") or ""
    reason = cut.get("reason")
    if cut_id and reason:
        return f"{cut_id} · {reason}"
    if cut_id and file:
        return f"{cut_id} · {file}"
    return cut_id or file or "cut"


def _cut_media_child(cut: dict[str, Any]) -> dict[str, Any] | None:
    source = str(cut.get("source") or "")
    base = source.rsplit("/", 1)[-1] if source else ""
    if not base:
        return None
    ext = base.rsplit(".", 1)[-1].lower() if "." in base else ""
    if ext in {"jpg", "jpeg", "png", "webp", "gif"}:
        return {"track": "media", "kind": "image", "label": f"<Img> {base}", "data": cut}
    if ext in {"mp4", "webm", "mov", "m4v"}:
        return {"track": "media", "kind": "video", "label": f"<Video> {base}", "data": cut}
    return None


def _build_caption_pages(captions: list[dict[str, Any]], words_per_page: int = 6) -> list[dict[str, Any]]:
    """Match remotion-composer CaptionOverlay page splitting."""
    pages: list[dict[str, Any]] = []
    for index in range(0, len(captions), words_per_page):
        page_words = captions[index : index + words_per_page]
        if not page_words:
            continue
        start_ms = float(page_words[0].get("startMs") or 0)
        end_ms = float(page_words[-1].get("endMs") or start_ms)
        preview = "".join(str(w.get("word") or "") for w in page_words)[:12]
        pages.append(
            {
                "words": page_words,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "preview": preview,
            }
        )
    return pages


def _caption_page_timing(
    page: dict[str, Any], pages: list[dict[str, Any]], page_index: int, duration_seconds: float
) -> tuple[float, float, float]:
    start = max(0.0, page["start_ms"] / 1000.0)
    if page_index + 1 < len(pages):
        end = max(start, pages[page_index + 1]["start_ms"] / 1000.0)
    else:
        end = max(start, page["end_ms"] / 1000.0 + 0.5)
    end = min(end, duration_seconds)
    return start, end, max(0.0, end - start)


def _overlay_sequence_name(overlay: dict[str, Any], index: int) -> str:
    text = overlay.get("text")
    if text:
        return str(text)
    return str(overlay.get("type") or f"overlay-{index + 1}")


def _overlay_timing(overlay: dict[str, Any]) -> tuple[float, float, float]:
    start = float(overlay.get("in_seconds", overlay.get("start_seconds")) or 0)
    end_raw = overlay.get("out_seconds", overlay.get("end_seconds"))
    end = float(end_raw) if end_raw is not None else start
    duration = max(0.0, end - start)
    return start, end, duration


def _cut_timeline_start(cut: dict[str, Any], *, absolute: bool, cursor: float) -> tuple[float, float]:
    raw = max(0.0, float(cut.get("out_seconds") or 0) - float(cut.get("in_seconds") or 0))
    speed = float(cut.get("speed") or 1) or 1.0
    duration = raw if absolute else raw / speed
    start = float(cut.get("in_seconds") or 0) if absolute else cursor
    return start, duration


def composition_duration_seconds(edit: dict[str, Any]) -> float:
    """Match remotion-composer/src/Root.tsx calculateMetadata for Explainer."""
    runtime = edit.get("render_runtime") or "ffmpeg"
    cuts = edit.get("cuts") or []
    if runtime in ("remotion", "hyperframes"):
        if not cuts:
            return 0.0
        last_end = max(float(c.get("out_seconds") or 0) for c in cuts)
        return last_end + 1.0
    total = 0.0
    for cut in cuts:
        _, duration = _cut_timeline_start(cut, absolute=False, cursor=total)
        total += duration
    return total


def build_composition_timeline(edit: dict[str, Any]) -> dict[str, Any]:
    props = normalize_composition_props(edit)
    runtime = props.get("render_runtime") or "ffmpeg"
    absolute = runtime in ("remotion", "hyperframes")
    cuts = props.get("cuts") or []

    cursor = 0.0
    cut_nodes: list[dict[str, Any]] = []
    for index, cut in enumerate(cuts):
        start, duration = _cut_timeline_start(cut, absolute=absolute, cursor=cursor)
        if not absolute:
            cursor += duration
        media_child = _cut_media_child(cut)
        children: list[dict[str, Any]] = []
        if media_child:
            children.append(
                {
                    **media_child,
                    "index": 0,
                    "start": start,
                    "end": start + duration,
                    "duration": duration,
                }
            )
        cut_nodes.append(
            {
                "track": "cut",
                "index": index,
                "id": cut.get("id") or f"cut-{index}",
                "start": start,
                "end": start + duration,
                "duration": duration,
                "label": _cut_sequence_name(cut),
                "reason": cut.get("reason"),
                "data": cut,
                "children": children,
            }
        )

    duration_seconds = composition_duration_seconds(edit)

    layers: list[dict[str, Any]] = [
        {
            "id": "cuts",
            "layer": 1,
            "kind": "sequence",
            "label": "cuts",
            "nodes": cut_nodes,
        }
    ]

    overlay_nodes: list[dict[str, Any]] = []
    for index, overlay in enumerate(props.get("overlays") or []):
        start, end, node_duration = _overlay_timing(overlay)
        if node_duration <= 0:
            continue
        overlay_nodes.append(
            {
                "track": "overlay",
                "index": index,
                "id": overlay.get("id") or f"overlay-{index}",
                "start": start,
                "end": end,
                "duration": node_duration,
                "label": _overlay_sequence_name(overlay, index),
                "data": overlay,
            }
        )
    if overlay_nodes:
        layers.append(
            {
                "id": "overlays",
                "layer": 2,
                "kind": "overlay",
                "label": "overlays",
                "nodes": overlay_nodes,
            }
        )

    captions = props.get("captions") or []
    if captions and absolute and captions[0].get("startMs") is not None:
        caption_pages = _build_caption_pages(captions)
        caption_nodes: list[dict[str, Any]] = []
        for page_index, page in enumerate(caption_pages):
            start, end, node_duration = _caption_page_timing(
                page, caption_pages, page_index, duration_seconds
            )
            if node_duration <= 0:
                continue
            preview = page.get("preview") or ""
            caption_nodes.append(
                {
                    "track": "caption",
                    "index": page_index,
                    "id": f"caption-{page_index}",
                    "start": start,
                    "end": end,
                    "duration": node_duration,
                    "label": "caption",
                    "preview": preview,
                    "data": page,
                }
            )
        if caption_nodes:
            layers.append(
                {
                    "id": "captions",
                    "layer": 3,
                    "kind": "caption",
                    "label": "captions",
                    "nodes": caption_nodes,
                }
            )
    elif captions:
        starts = [float(c.get("start") or 0) for c in captions]
        ends = [float(c.get("end") or 0) for c in captions]
        cap_start = min(starts) if starts else 0.0
        cap_end = max(ends) if ends else duration_seconds
        layers.append(
            {
                "id": "captions",
                "layer": 3,
                "kind": "caption",
                "label": "captions",
                "nodes": [
                    {
                        "track": "caption",
                        "index": 0,
                        "id": "captions",
                        "start": cap_start,
                        "end": cap_end,
                        "duration": max(0.0, cap_end - cap_start),
                        "label": "captions",
                        "data": {"captions": captions},
                    }
                ],
            }
        )

    narration = (props.get("audio") or {}).get("narration") or {}
    narr_segments = narration.get("segments") or []
    narr_src = narration.get("src")
    if narr_segments or narr_src:
        if narr_segments:
            narr_nodes = []
            for index, seg in enumerate(narr_segments):
                start = float(seg.get("start_seconds") or 0)
                end_raw = seg.get("end_seconds")
                end = float(end_raw) if end_raw is not None else duration_seconds
                narr_nodes.append(
                    {
                        "track": "narr",
                        "index": index,
                        "id": seg.get("asset_id") or f"narr-{index}",
                        "start": start,
                        "end": end,
                        "duration": max(0.1, end - start),
                        "label": seg.get("asset_id") or "narration",
                        "data": seg,
                    }
                )
        else:
            label = str(narr_src).split("/")[-1] if narr_src else "narration"
            narr_nodes = [
                {
                    "track": "narr",
                    "index": 0,
                    "id": "narration",
                    "start": 0.0,
                    "end": duration_seconds,
                    "duration": duration_seconds,
                    "label": label,
                    "data": {"src": narr_src, "volume": narration.get("volume")},
                }
            ]
        layers.append(
            {
                "id": "audio-narration",
                "layer": 4,
                "kind": "audio",
                "label": "audio.narration",
                "nodes": narr_nodes,
            }
        )

    music = (props.get("audio") or {}).get("music") or {}
    if music.get("src") or music.get("asset_id"):
        label = music.get("asset_id") or (
            str(music.get("src")).split("/")[-1] if music.get("src") else "music"
        )
        layers.append(
            {
                "id": "audio-music",
                "layer": 4,
                "kind": "audio",
                "label": "audio.music",
                "nodes": [
                    {
                        "track": "music",
                        "index": 0,
                        "id": label,
                        "start": 0.0,
                        "end": duration_seconds,
                        "duration": duration_seconds,
                        "label": label,
                        "data": music,
                    }
                ],
            }
        )

    if not absolute:
        sfx_list = (props.get("audio") or {}).get("sfx") or []
        if sfx_list:
            sfx_nodes = []
            for index, sfx in enumerate(sfx_list):
                start = float(sfx.get("start_seconds") or 0)
                dur = float(sfx.get("duration_seconds") or 2)
                sfx_nodes.append(
                    {
                        "track": "sfx",
                        "index": index,
                        "id": sfx.get("asset_id") or f"sfx-{index}",
                        "start": start,
                        "end": start + dur,
                        "duration": dur,
                        "label": sfx.get("asset_id") or "sfx",
                        "data": sfx,
                    }
                )
            layers.append(
                {
                    "id": "audio-sfx",
                    "layer": 5,
                    "kind": "audio",
                    "label": "audio.sfx",
                    "nodes": sfx_nodes,
                }
            )

    return {
        "render_runtime": runtime,
        "duration_seconds": duration_seconds,
        "layers": layers,
        "props": {
            "cuts": props.get("cuts") or [],
            "overlays": props.get("overlays") or [],
            "captions": props.get("captions") or [],
            "audio": props.get("audio") or {},
        },
    }
