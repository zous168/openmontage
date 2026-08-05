"""Project-level publish / cover intake — stored in meta.json production_inputs.

Pipeline publish-director skills define *how* to design thumbnails; these fields
capture *what this project* wants on the cover (hook text, visual notes, source).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Optional

THUMBNAIL_SOURCE_OPTIONS: list[dict[str, str]] = [
    {"value": "auto_frame", "label_zh": "成片截帧（默认）"},
    {"value": "text_to_image", "label_zh": "文生图（AI 生成封面）"},
    {"value": "concept_only", "label_zh": "仅设计概念（不自动生成图）"},
]

DEFAULT_FRAME_CAPTURE_SECONDS = 0.8
_VALID_SOURCES = {o["value"] for o in THUMBNAIL_SOURCE_OPTIONS}

COVER_KEYS = frozenset({
    "thumbnail_text_hook",
    "thumbnail_style_notes",
    "thumbnail_source",
})


def cover_bootstrap_fields() -> list[dict[str, Any]]:
    """Optional cover fields shown after deliverable spec in project create/settings."""
    return [
        {
            "key": "thumbnail_text_hook",
            "type": "text",
            "label_zh": "封面文案",
            "required": False,
            "field_group": "cover",
            "hint_zh": "3–8 字钩子，如「又回购了」；留空则由 Agent 根据脚本生成",
        },
        {
            "key": "thumbnail_style_notes",
            "type": "text",
            "label_zh": "封面视觉说明",
            "required": False,
            "field_group": "cover",
            "hint_zh": "产品特写、品牌色、字幕样式等；publish 阶段会与 playbook 合并",
        },
        {
            "key": "thumbnail_source",
            "type": "select",
            "label_zh": "封面来源",
            "required": False,
            "field_group": "cover",
            "options": list(THUMBNAIL_SOURCE_OPTIONS),
        },
    ]


def normalize_cover_field(key: str, value: Any) -> Any:
    if value is None or str(value).strip() == "":
        raise ValueError("empty")
    if key == "thumbnail_text_hook":
        text = str(value).strip()
        if len(text) > 120:
            raise ValueError("封面文案过长（最多 120 字）。")
        return text
    if key == "thumbnail_style_notes":
        text = str(value).strip()
        if len(text) > 500:
            raise ValueError("封面视觉说明过长（最多 500 字）。")
        return text
    if key == "thumbnail_source":
        text = str(value).strip()
        if text not in _VALID_SOURCES:
            raise ValueError(f"无效封面来源：{text}")
        return text
    raise KeyError(key)


def resolve_cover_brief(production_inputs: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Merge stored cover intake into a publish-ready brief."""
    pi = production_inputs or {}
    source = str(pi.get("thumbnail_source") or "auto_frame").strip()
    if source not in _VALID_SOURCES:
        source = "auto_frame"
    return {
        "text_hook": str(pi.get("thumbnail_text_hook") or "").strip(),
        "style_notes": str(pi.get("thumbnail_style_notes") or "").strip(),
        "source": source,
    }


def default_frame_capture_seconds() -> float:
    """Fixed publish-time default when cover source is auto_frame."""
    return DEFAULT_FRAME_CAPTURE_SECONDS


def load_cover_brief_from_project(project_dir: Path) -> dict[str, Any] | None:
    meta_path = Path(project_dir) / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pi = meta.get("production_inputs")
    if not isinstance(pi, dict):
        return None
    return resolve_cover_brief(pi)


def thumbnail_dimensions(
    deliverable: Optional[dict[str, Any]] = None,
) -> tuple[int, int, str]:
    """Return (width, height, aspect_ratio) for thumbnail generation."""
    if deliverable and deliverable.get("width") and deliverable.get("height"):
        return (
            int(deliverable["width"]),
            int(deliverable["height"]),
            str(deliverable.get("aspect_ratio") or "16:9"),
        )
    return 1080, 1920, "9:16"


def build_thumbnail_prompt(
    cover: dict[str, Any],
    *,
    title: str = "",
    style_playbook: str = "",
    deliverable: Optional[dict[str, Any]] = None,
) -> str:
    """Assemble a FLUX-friendly thumbnail prompt from project cover intake."""
    aspect = str((deliverable or {}).get("aspect_ratio") or "9:16")
    parts: list[str] = []
    if aspect == "9:16":
        parts.append(
            "Vertical social video thumbnail in 9:16 portrait format, "
            "center-weighted composition readable on mobile feeds"
        )
    elif aspect == "16:9":
        parts.append(
            "Horizontal video thumbnail in 16:9 landscape format, "
            "strong focal subject with clean negative space"
        )
    elif aspect == "1:1":
        parts.append("Square social thumbnail in 1:1 format, bold centered layout")
    else:
        parts.append(f"Video thumbnail in {aspect} aspect ratio")

    if cover.get("style_notes"):
        parts.append(cover["style_notes"])
    if cover.get("text_hook"):
        parts.append(
            f'Include bold high-contrast headline text reading "{cover["text_hook"]}" '
            "with crisp legible typography"
        )
    elif title:
        parts.append(f"Visual concept for video titled「{title}」")
    if style_playbook:
        parts.append(f"Visual style aligned with {style_playbook} brand aesthetics")
    parts.append(
        "Feed-stopping contrast, professional lighting, unmarked surfaces, "
        "no watermark, no UI chrome, no blurry text"
    )
    return ". ".join(parts)


def build_thumbnail_concept(
    cover: dict[str, Any],
    *,
    title: str = "",
    style_playbook: str = "",
    deliverable: Optional[dict[str, Any]] = None,
    generation: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Build export_bundle thumbnail_concept from project cover intake."""
    prompt = build_thumbnail_prompt(
        cover,
        title=title,
        style_playbook=style_playbook,
        deliverable=deliverable,
    )
    concept_parts: list[str] = []
    if cover.get("style_notes"):
        concept_parts.append(cover["style_notes"])
    if style_playbook:
        concept_parts.append(f"playbook: {style_playbook}")
    if not concept_parts and title:
        concept_parts.append(f"封面突出「{title}」")
    concept: dict[str, Any] = {
        "concept": "；".join(concept_parts) if concept_parts else "平台竖屏封面，高对比可读",
        "text_overlay": cover.get("text_hook") or "",
        "style_notes": cover.get("style_notes") or "",
        "source": cover.get("source") or "auto_frame",
        "prompt": prompt,
    }
    if generation:
        concept["generation"] = generation
    return concept


def generate_cover_thumbnail(
    prompt: str,
    output_path: Path,
    *,
    width: int,
    height: int,
    aspect_ratio: str,
    preferred_provider: str = "auto",
) -> tuple[Optional[Path], Optional[dict[str, Any]], Optional[str]]:
    """Generate a cover image via image_selector. Returns (path, meta, error)."""
    from plugins.openmontage.tools.base_tool import ToolStatus
    from plugins.openmontage.tools.graphics.image_selector import ImageSelector

    selector = ImageSelector()
    if selector.get_status() != ToolStatus.AVAILABLE:
        return None, None, "No image generation provider available (image_selector)."

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = selector.execute({
        "prompt": prompt,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "output_path": str(output_path),
        "preferred_provider": preferred_provider,
    })
    if not result.success:
        return None, None, result.error or "image_selector failed"

    artifact = None
    if result.artifacts:
        artifact = Path(result.artifacts[0])
    elif result.data and result.data.get("output"):
        artifact = Path(result.data["output"])
    if artifact is None or not artifact.is_file():
        return None, None, "Image generation succeeded but no output file was written."

    meta = {
        "provider": result.data.get("selected_provider") or result.data.get("provider"),
        "tool": result.data.get("selected_tool"),
        "prompt": prompt,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
    }
    if result.cost_usd is not None:
        meta["cost_usd"] = result.cost_usd
    return artifact, meta, None


def extract_frame_thumbnail(
    video_path: Path,
    output_dir: Path,
    capture_seconds: float,
    *,
    output_name: str = "thumbnail.jpg",
) -> Optional[Path]:
    """Extract one JPEG frame from video at capture_seconds. Returns path or None."""
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            check=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None

    output_dir.mkdir(parents=True, exist_ok=True)
    dest = output_dir / output_name
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(max(0.0, capture_seconds)),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "2",
        str(dest),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    return dest if dest.is_file() else None
