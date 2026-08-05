"""Tests for lib.decision_log and latest-decision audit semantics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.openmontage.lib.decision_log import append_decisions, latest_decisions_for_stage, suggest_next_decision_id
from plugins.openmontage.lib.production_audit import check_approval_gate_drift


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    import plugins.openmontage.lib.paths as paths_mod

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(paths_mod, "PROJECTS_DIR", root)
    return root


def _project(projects_root: Path, project_id: str = "dec-log") -> Path:
    p = projects_root / project_id
    p.mkdir()
    (p / "project.json").write_text(
        json.dumps({"version": "1.0", "project_id": project_id, "pipeline_type": "reference-driven"}),
        encoding="utf-8",
    )
    return p


def test_append_decisions_validates_and_persists(projects_root: Path):
    p = _project(projects_root)
    append_decisions(
        p.name,
        [{
            "decision_id": "d-001",
            "stage": "proposal",
            "category": "concept_selection",
            "subject": "Concept",
            "options_considered": [{
                "option_id": "c1",
                "label": "A",
                "score": 0.9,
                "reason": "test",
            }],
            "selected": "c1",
            "reason": "test",
            "user_visible": True,
            "user_approved": True,
            "confidence": 0.9,
        }],
        projects_dir=projects_root,
    )
    log = json.loads((p / "decision_log.json").read_text(encoding="utf-8"))
    assert len(log["decisions"]) == 1


def test_latest_decisions_for_stage_prefers_newer_subject_match():
    decisions = [
        {
            "decision_id": "d-001",
            "stage": "proposal",
            "category": "render_runtime_selection",
            "subject": "Runtime",
            "user_visible": True,
            "user_approved": False,
        },
        {
            "decision_id": "d-002",
            "stage": "proposal",
            "category": "render_runtime_selection",
            "subject": "Runtime",
            "user_visible": True,
            "user_approved": True,
        },
    ]
    latest = latest_decisions_for_stage(decisions, "proposal")
    assert len(latest) == 1
    assert latest[0]["decision_id"] == "d-002"


def test_approval_gate_drift_ignores_superseded_unapproved(projects_root: Path):
    p = _project(projects_root)
    (p / "decision_log.json").write_text(json.dumps({
        "version": "1.0",
        "project_id": p.name,
        "decisions": [
            {
                "decision_id": "d-001",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Runtime",
                "options_considered": [{"option_id": "hyperframes", "label": "HF", "score": 0.8, "reason": "x"}],
                "selected": "hyperframes",
                "reason": "old",
                "user_visible": True,
                "user_approved": False,
            },
            {
                "decision_id": "d-002",
                "stage": "proposal",
                "category": "render_runtime_selection",
                "subject": "Runtime",
                "options_considered": [{"option_id": "remotion", "label": "Remotion", "score": 1.0, "reason": "x"}],
                "selected": "remotion",
                "reason": "approved rerun",
                "user_visible": True,
                "user_approved": True,
            },
        ],
    }), encoding="utf-8")
    (p / "checkpoint_proposal.json").write_text(json.dumps({
        "version": "1.0",
        "project_id": p.name,
        "pipeline_type": "reference-driven",
        "stage": "proposal",
        "status": "completed",
        "human_approved": True,
        "artifacts": {},
    }), encoding="utf-8")

    assert check_approval_gate_drift(p) == []


def test_suggest_next_decision_id(projects_root: Path):
    p = _project(projects_root)
    (p / "decision_log.json").write_text(json.dumps({
        "version": "1.0",
        "project_id": p.name,
        "decisions": [{"decision_id": "d-007"}],
    }), encoding="utf-8")
    assert suggest_next_decision_id(p) == "d-008"
