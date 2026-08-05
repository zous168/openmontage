"""Persist React Flow canvas layout (node positions + viewport) in meta.json."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_STAGE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _valid_stage_name(name: str) -> bool:
    return bool(_STAGE_NAME_RE.match(name))


def _valid_coord(val: Any) -> float | None:
    try:
        number = float(val)
    except (TypeError, ValueError):
        return None
    if not -50_000 <= number <= 50_000:
        return None
    return number


def normalize_flow_layout(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Return a sanitized flow_layout payload."""
    raw = raw or {}
    stages_in = raw.get("stages") if isinstance(raw.get("stages"), dict) else {}
    stages: dict[str, dict[str, float]] = {}
    for name, pos in stages_in.items():
        if not isinstance(name, str) or not _valid_stage_name(name):
            continue
        if not isinstance(pos, dict):
            continue
        x = _valid_coord(pos.get("x"))
        y = _valid_coord(pos.get("y"))
        if x is None or y is None:
            continue
        stages[name] = {"x": x, "y": y}

    out: dict[str, Any] = {"stages": stages}

    vp_raw = raw.get("viewport")
    if isinstance(vp_raw, dict):
        x = _valid_coord(vp_raw.get("x"))
        y = _valid_coord(vp_raw.get("y"))
        zoom = _valid_coord(vp_raw.get("zoom"))
        if x is not None and y is not None and zoom is not None and 0.05 <= zoom <= 4:
            out["viewport"] = {"x": x, "y": y, "zoom": zoom}

    updated = raw.get("updated_at")
    if isinstance(updated, str) and updated.strip():
        out["updated_at"] = updated.strip()

    return out


def load_flow_layout(project_dir: Path) -> dict[str, Any]:
    meta_path = project_dir / "meta.json"
    if not meta_path.is_file():
        return {"stages": {}}
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return normalize_flow_layout(meta.get("flow_layout"))


def save_flow_layout(
    project_dir: Path,
    *,
    stages: dict[str, Any] | None = None,
    viewport: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Merge and persist layout. Omitted fields keep their previous values."""
    current = load_flow_layout(project_dir)

    next_stages = current["stages"]
    if stages is not None:
        normalized = normalize_flow_layout({"stages": stages})
        next_stages = normalized["stages"]

    next_layout: dict[str, Any] = {
        "stages": next_stages,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if viewport is not None:
        merged = normalize_flow_layout({**current, "viewport": viewport})
        if "viewport" in merged:
            next_layout["viewport"] = merged["viewport"]
    elif "viewport" in current:
        next_layout["viewport"] = current["viewport"]

    meta_path = project_dir / "meta.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("version", "1.0")
    meta["flow_layout"] = next_layout
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return normalize_flow_layout(next_layout)
