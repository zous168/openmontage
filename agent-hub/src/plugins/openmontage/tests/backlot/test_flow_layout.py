"""Tests for flow layout persistence."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.openmontage.backlot.flow_layout import load_flow_layout, normalize_flow_layout, save_flow_layout


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_normalize_flow_layout_filters_invalid_entries() -> None:
    out = normalize_flow_layout(
        {
            "stages": {
                "script": {"x": 120, "y": 40},
                "bad name": {"x": 1, "y": 2},
                "proposal": {"x": "nope", "y": 0},
            },
            "viewport": {"x": 10, "y": -20, "zoom": 1.25},
        }
    )
    assert out["stages"] == {"script": {"x": 120.0, "y": 40.0}}
    assert out["viewport"] == {"x": 10.0, "y": -20.0, "zoom": 1.25}


def test_save_and_load_flow_layout(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    _write_json(project / "meta.json", {"version": "1.0"})

    saved = save_flow_layout(
        project,
        stages={"script": {"x": 300, "y": 80}, "assets": {"x": 620, "y": 80}},
        viewport={"x": -40, "y": 12, "zoom": 0.9},
    )
    assert saved["stages"]["script"] == {"x": 300.0, "y": 80.0}
    assert saved["viewport"]["zoom"] == 0.9

    loaded = load_flow_layout(project)
    assert loaded["stages"]["assets"] == {"x": 620.0, "y": 80.0}
    assert loaded["viewport"]["x"] == -40.0

    meta = json.loads((project / "meta.json").read_text(encoding="utf-8"))
    assert "flow_layout" in meta
    assert meta["flow_layout"]["stages"]["script"]["x"] == 300


def test_save_flow_layout_preserves_viewport_when_omitted(tmp_path: Path) -> None:
    project = tmp_path / "demo"
    project.mkdir()
    save_flow_layout(
        project,
        stages={"script": {"x": 1, "y": 2}},
        viewport={"x": 0, "y": 0, "zoom": 1},
    )
    saved = save_flow_layout(project, stages={"script": {"x": 50, "y": 60}})
    assert saved["viewport"] == {"x": 0.0, "y": 0.0, "zoom": 1.0}
