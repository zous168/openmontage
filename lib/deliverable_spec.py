"""Project deliverable specs — aspect ratio, resolution tier, fps, media profile.

Stored in ``meta.json`` → ``production_inputs`` (aspect_ratio, quality_tier, fps).
Platform defaults apply when fields are omitted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

ASPECT_RATIO_OPTIONS: list[dict[str, str]] = [
    {"value": "9:16", "label_zh": "竖屏 9:16"},
    {"value": "16:9", "label_zh": "横屏 16:9"},
    {"value": "1:1", "label_zh": "方形 1:1"},
    {"value": "21:9", "label_zh": "电影宽屏 21:9"},
]

QUALITY_TIER_OPTIONS: list[dict[str, str]] = [
    {"value": "720p", "label_zh": "720p（体积更小）"},
    {"value": "1080p", "label_zh": "1080p（推荐）"},
]

FPS_OPTIONS: list[dict[str, str]] = [
    {"value": "24", "label_zh": "24 fps"},
    {"value": "30", "label_zh": "30 fps"},
]

# Platform → default deliverable when user leaves fields blank.
PLATFORM_DEFAULTS: dict[str, dict[str, Any]] = {
    "douyin": {"aspect_ratio": "9:16", "quality_tier": "1080p", "fps": 30},
    "weixin_channels": {"aspect_ratio": "9:16", "quality_tier": "1080p", "fps": 30},
    "xiaohongshu": {"aspect_ratio": "9:16", "quality_tier": "1080p", "fps": 30},
    "tiktok": {"aspect_ratio": "9:16", "quality_tier": "1080p", "fps": 30},
    "instagram": {"aspect_ratio": "9:16", "quality_tier": "1080p", "fps": 30},
    "youtube": {"aspect_ratio": "16:9", "quality_tier": "1080p", "fps": 30},
    "bilibili": {"aspect_ratio": "16:9", "quality_tier": "1080p", "fps": 30},
    "linkedin": {"aspect_ratio": "16:9", "quality_tier": "1080p", "fps": 30},
    "generic": {"aspect_ratio": "16:9", "quality_tier": "1080p", "fps": 30},
}

# (aspect_ratio, quality_tier) → (width, height)
_RESOLUTION_TABLE: dict[tuple[str, str], tuple[int, int]] = {
    ("9:16", "720p"): (720, 1280),
    ("9:16", "1080p"): (1080, 1920),
    ("16:9", "720p"): (1280, 720),
    ("16:9", "1080p"): (1920, 1080),
    ("1:1", "720p"): (720, 720),
    ("1:1", "1080p"): (1080, 1080),
    ("21:9", "720p"): (1680, 720),
    ("21:9", "1080p"): (2560, 1080),
}

# Platform label → media_profiles.py registry name (when available).
_PLATFORM_MEDIA_PROFILE: dict[str, str] = {
    "douyin": "tiktok",
    "weixin_channels": "tiktok",
    "xiaohongshu": "tiktok",
    "tiktok": "tiktok",
    "instagram": "instagram_reels",
    "youtube": "youtube_landscape",
    "bilibili": "youtube_landscape",
    "linkedin": "linkedin",
    "generic": "generic_hd",
}

_VALID_ASPECT = {o["value"] for o in ASPECT_RATIO_OPTIONS}
_VALID_QUALITY = {o["value"] for o in QUALITY_TIER_OPTIONS}
_VALID_FPS = {int(o["value"]) for o in FPS_OPTIONS}


def deliverable_bootstrap_fields() -> list[dict[str, Any]]:
    """Optional form fields appended after target_platform in project settings."""
    return [
        {
            "key": "aspect_ratio",
            "type": "select",
            "label_zh": "画幅比例",
            "required": False,
            "hint_zh": "留空则按发布平台默认；抖音/视频号通常为竖屏 9:16",
            "options": list(ASPECT_RATIO_OPTIONS),
            "field_group": "deliverable",
        },
        {
            "key": "quality_tier",
            "type": "select",
            "label_zh": "分辨率档位",
            "required": False,
            "hint_zh": "720p 体积更小；1080p 为平台推荐清晰度",
            "options": list(QUALITY_TIER_OPTIONS),
            "field_group": "deliverable",
        },
        {
            "key": "fps",
            "type": "select",
            "label_zh": "帧率",
            "required": False,
            "hint_zh": "竖屏短视频通常 30 fps；电影感可选 24 fps",
            "options": list(FPS_OPTIONS),
            "field_group": "deliverable",
        },
    ]


def _platform_defaults(platform: Optional[str]) -> dict[str, Any]:
    key = (platform or "generic").strip().lower() or "generic"
    return dict(PLATFORM_DEFAULTS.get(key, PLATFORM_DEFAULTS["generic"]))


def _coerce_fps(raw: Any) -> int:
    if raw is None or str(raw).strip() == "":
        return 30
    try:
        fps = int(float(raw))
    except (TypeError, ValueError):
        raise ValueError("帧率必须是 24 或 30。") from None
    if fps not in _VALID_FPS:
        raise ValueError("帧率必须是 24 或 30。")
    return fps


def resolve_deliverable(production_inputs: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Merge stored inputs with platform defaults into a concrete output spec."""
    pi = production_inputs or {}
    platform = str(pi.get("target_platform") or "generic").strip().lower() or "generic"
    defaults = _platform_defaults(platform)

    aspect = str(pi.get("aspect_ratio") or defaults["aspect_ratio"]).strip()
    tier = str(pi.get("quality_tier") or defaults["quality_tier"]).strip()
    fps = _coerce_fps(pi.get("fps") if pi.get("fps") not in (None, "") else defaults["fps"])

    if aspect not in _VALID_ASPECT:
        aspect = defaults["aspect_ratio"]
    if tier not in _VALID_QUALITY:
        tier = defaults["quality_tier"]

    width, height = _RESOLUTION_TABLE.get((aspect, tier), (1920, 1080))
    profile = _PLATFORM_MEDIA_PROFILE.get(platform, "generic_hd")
    if aspect == "9:16" and tier == "1080p":
        profile = {
            "douyin": "tiktok",
            "weixin_channels": "tiktok",
            "xiaohongshu": "tiktok",
            "tiktok": "tiktok",
            "instagram": "instagram_reels",
        }.get(platform, "youtube_shorts")
    elif aspect == "16:9" and tier == "1080p":
        profile = _PLATFORM_MEDIA_PROFILE.get(platform, "youtube_landscape")
    elif aspect == "1:1":
        profile = "instagram_feed"
    elif aspect == "21:9":
        profile = "cinematic"

    return {
        "target_platform": platform,
        "aspect_ratio": aspect,
        "quality_tier": tier,
        "fps": fps,
        "width": width,
        "height": height,
        "resolution": f"{width}x{height}",
        "media_profile": profile,
        "configured": {
            "aspect_ratio": pi.get("aspect_ratio"),
            "quality_tier": pi.get("quality_tier"),
            "fps": pi.get("fps"),
        },
    }


def normalize_deliverable_field(key: str, value: Any) -> Any:
    """Validate one deliverable field; raises ValueError on bad input."""
    if value is None or str(value).strip() == "":
        raise ValueError("empty")
    text = str(value).strip()
    if key == "aspect_ratio":
        if text not in _VALID_ASPECT:
            raise ValueError(f"无效画幅比例：{text}")
        return text
    if key == "quality_tier":
        if text not in _VALID_QUALITY:
            raise ValueError(f"无效分辨率档位：{text}")
        return text
    if key == "fps":
        return _coerce_fps(text)
    raise KeyError(key)


DELIVERABLE_KEYS = frozenset({"aspect_ratio", "quality_tier", "fps"})


def load_deliverable_from_project(project_dir: Path) -> dict[str, Any] | None:
    """Load resolved deliverable spec from a project directory."""
    meta_path = Path(project_dir) / "meta.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    production_inputs = meta.get("production_inputs")
    if not isinstance(production_inputs, dict):
        return None
    return resolve_deliverable(production_inputs)


def compose_target_from_deliverable(spec: dict[str, Any]) -> dict[str, Any]:
    """Map deliverable spec to edit_decisions.metadata.compose_target."""
    aspect = str(spec.get("aspect_ratio") or "16:9")
    fit = "cover" if aspect in ("9:16", "1:1") else "pad"
    return {
        "width": int(spec["width"]),
        "height": int(spec["height"]),
        "fit": fit,
        "fps": int(spec["fps"]),
    }


def _infer_project_dir_from_inputs(inputs: dict[str, Any]) -> Path | None:
    explicit = inputs.get("project_dir") or inputs.get("project_path")
    if explicit:
        candidate = Path(str(explicit)).resolve()
        if (candidate / "meta.json").is_file() or (candidate / "project.json").is_file():
            return candidate
    try:
        from lib.events import infer_project_dir

        inferred = infer_project_dir(inputs)
        if inferred is not None:
            return inferred.resolve()
    except Exception:
        pass
    return None


def enrich_render_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Apply project deliverable defaults to compose/render tool inputs.

    When ``meta.json`` → ``production_inputs`` defines aspect ratio, quality
    tier, or fps, this fills in ``profile``, ``fps``, and
    ``edit_decisions.metadata.compose_target`` unless the caller already set them.
    """
    project_dir = _infer_project_dir_from_inputs(inputs)
    if project_dir is None:
        return inputs

    spec = load_deliverable_from_project(project_dir)
    if not spec:
        return inputs

    out = dict(inputs)
    out.setdefault("deliverable", spec)

    if not out.get("profile") and not out.get("output_profile"):
        out["profile"] = spec.get("media_profile")

    if out.get("fps") in (None, ""):
        out["fps"] = spec["fps"]

    if not out.get("platform"):
        out["platform"] = spec.get("target_platform")

    ed = out.get("edit_decisions")
    if isinstance(ed, dict):
        ed = dict(ed)
        meta = dict(ed.get("metadata") or {})
        compose_target = meta.get("compose_target")
        if not isinstance(compose_target, dict) or not compose_target.get("width"):
            meta["compose_target"] = compose_target_from_deliverable(spec)
        meta.setdefault(
            "deliverable",
            {
                "resolution": spec["resolution"],
                "aspect_ratio": spec["aspect_ratio"],
                "quality_tier": spec["quality_tier"],
                "fps": spec["fps"],
                "media_profile": spec.get("media_profile"),
            },
        )
        ed["metadata"] = meta
        out["edit_decisions"] = ed

    return out


def enrich_generation_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Apply deliverable defaults for AI video/image generation tools."""
    project_dir = _infer_project_dir_from_inputs(inputs)
    if project_dir is None:
        return inputs

    spec = load_deliverable_from_project(project_dir)
    if not spec:
        return inputs

    out = dict(inputs)
    out.setdefault("deliverable", spec)

    if not out.get("aspect_ratio"):
        out["aspect_ratio"] = spec["aspect_ratio"]
    if out.get("width") in (None, "", 0):
        out["width"] = spec["width"]
    if out.get("height") in (None, "", 0):
        out["height"] = spec["height"]

    return out


def enrich_project_deliverable(inputs: dict[str, Any]) -> dict[str, Any]:
    """Apply all project deliverable defaults to tool inputs."""
    return enrich_generation_inputs(enrich_render_inputs(inputs))
