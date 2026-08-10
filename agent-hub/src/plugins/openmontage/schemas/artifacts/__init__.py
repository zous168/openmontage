"""Artifact schema loading and validation utilities."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

SCHEMA_DIR = Path(__file__).parent

ARTIFACT_NAMES = [
    "research_brief",
    "proposal_packet",
    "brief",
    "script",
    "character_design",
    "rig_plan",
    "pose_library",
    "scene_plan",
    "action_timeline",
    "asset_manifest",
    "edit_decisions",
    "render_report",
    "publish_log",
    "review",
    "cost_log",
    "decision_log",
    "source_media_review",
    "final_review",
    "character_qa_report",
    "video_analysis_brief",
]


def load_schema(name: str) -> dict:
    """Load a JSON schema by artifact name."""
    path = SCHEMA_DIR / f"{name}.schema.json"
    if not path.exists():
        raise FileNotFoundError(f"Schema not found: {path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Common LLM slips for timeline_beat.kind → canonical enum values.
# Camera verbs (push/pull/…) are not kinds; they belong under kind=camera.
_BEAT_KIND_ALIASES: dict[str, str] = {
    "push": "camera",
    "pull": "camera",
    "pan": "camera",
    "tilt": "camera",
    "zoom": "camera",
    "dolly": "camera",
    "truck": "camera",
    "track": "camera",
    "tracking": "camera",
    "crane": "camera",
    "orbit": "camera",
    "handheld": "camera",
    "ken_burns": "camera",
    "kenburns": "camera",
    "text": "overlay",
    "title": "overlay",
    "subtitle": "overlay",
    "caption": "overlay",
    "lower_third": "overlay",
    "sfx": "vfx",
    "effect": "vfx",
    "fx": "vfx",
    "voiceover": "speech",
    "vo": "speech",
    "narration": "speech",
    "talk": "dialogue",
    "idle": "hold",
    "still": "hold",
    "pause": "hold",
    "gesture": "action",
    "movement": "action",
}


def normalize_artifact(name: str, data: dict[str, Any]) -> dict[str, Any]:
    """Soft-fix common agent slips in place before schema validation.

    Returns the same dict (mutated). Safe to call repeatedly.
    """
    if name == "video_analysis_brief" and isinstance(data, dict):
        _normalize_video_analysis_brief_beats(data)
    return data


def _normalize_video_analysis_brief_beats(data: dict[str, Any]) -> None:
    structure = data.get("structure_analysis")
    if not isinstance(structure, dict):
        return
    scenes = structure.get("scenes")
    if not isinstance(scenes, list):
        return
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        beats = scene.get("beats")
        if not isinstance(beats, list):
            continue
        for beat in beats:
            if not isinstance(beat, dict):
                continue
            kind = beat.get("kind")
            if not isinstance(kind, str):
                continue
            mapped = _BEAT_KIND_ALIASES.get(kind.strip().lower())
            if mapped:
                beat["kind"] = mapped


def validate_artifact(name: str, data: dict[str, Any]) -> None:
    """Validate artifact data against its schema. Raises on failure."""
    if isinstance(data, dict):
        normalize_artifact(name, data)
    schema = load_schema(name)
    jsonschema.validate(instance=data, schema=schema)


def list_schemas() -> list[str]:
    """List all available artifact schema names."""
    return [p.stem.replace(".schema", "") for p in SCHEMA_DIR.glob("*.schema.json")]


def _summarize_schema_node(node: Any, *, depth: int = 0) -> Any:
    """Compress a JSON Schema subtree into a field-contract dict for agents."""
    if not isinstance(node, dict) or depth > 4:
        if isinstance(node, dict):
            return {"type": node.get("type")}
        return node

    out: dict[str, Any] = {}
    if "type" in node:
        out["type"] = node["type"]
    if "const" in node:
        out["const"] = node["const"]
    if "enum" in node:
        out["enum"] = node["enum"]
    if "format" in node:
        out["format"] = node["format"]
    if "minItems" in node:
        out["minItems"] = node["minItems"]
    if "additionalProperties" in node:
        out["additionalProperties"] = node["additionalProperties"]
    if "required" in node:
        out["required"] = node["required"]

    props = node.get("properties")
    if isinstance(props, dict):
        out["properties"] = {
            key: _summarize_schema_node(val, depth=depth + 1)
            for key, val in props.items()
        }

    items = node.get("items")
    if isinstance(items, dict):
        if items.get("type") == "object" or "properties" in items:
            item_props = items.get("properties") or {}
            out["items"] = {
                "type": "object",
                "required": items.get("required") or [],
                "properties": {
                    key: _summarize_schema_node(val, depth=depth + 1)
                    for key, val in item_props.items()
                },
                "additionalProperties": items.get("additionalProperties"),
            }
        else:
            out["items"] = _summarize_schema_node(items, depth=depth + 1)

    return out


def summarize_artifact_schema(name: str) -> dict[str, Any]:
    """Agent-facing field contract for one artifact — no need to open *.schema.json.

    Used in stage prompts, om_director, and complete_from_disk diagnostics so
    models stop inventing aliases (e.g. ``stat`` instead of ``claim``).
    """
    schema = load_schema(name)
    props_summary = _summarize_schema_node(
        {
            "type": "object",
            "properties": schema.get("properties") or {},
            "required": schema.get("required") or [],
            "additionalProperties": schema.get("additionalProperties"),
        },
    )
    return {
        "artifact": name,
        "required": schema.get("required") or [],
        "properties": props_summary.get("properties"),
        "rules": [
            "JSON 字段名必须与本契约完全一致，禁止自造别名或近义词键名",
            "标了 additionalProperties=false 的对象不得添加未列出字段",
            "数组注意 minItems / required；写完对照本契约自检，"
            "不要 search_files 打开 *.schema.json",
        ],
    }
