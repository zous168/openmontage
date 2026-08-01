"""Tests for lib.production_audit — project-level bypass detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.production_audit import (
    audit_project,
    check_approval_gate_drift,
    check_compose_tool_trace,
)


@pytest.fixture
def projects_root(tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    return root


def _project(projects_root: Path, project_id: str = "audit-bypass") -> Path:
    p = projects_root / project_id
    (p / "artifacts").mkdir(parents=True)
    (p / "project.json").write_text(
        json.dumps({
            "version": "1.0",
            "project_id": project_id,
            "pipeline_type": "reference-driven",
        }),
        encoding="utf-8",
    )
    return p


def test_approval_gate_drift_detected(projects_root: Path):
    p = _project(projects_root)
    (p / "decision_log.json").write_text(json.dumps({
        "version": "1.0",
        "project_id": p.name,
        "decisions": [{
            "decision_id": "d-001",
            "stage": "proposal",
            "category": "render_runtime_selection",
            "subject": "Composition runtime",
            "options_considered": [{
                "option_id": "remotion",
                "label": "Remotion",
                "score": 0.9,
                "reason": "test",
            }],
            "selected": "remotion",
            "reason": "test",
            "user_visible": True,
            "user_approved": False,
            "confidence": 0.8,
        }],
    }), encoding="utf-8")
    (p / "checkpoint_proposal.json").write_text(json.dumps({
        "version": "1.0",
        "project_id": p.name,
        "pipeline_type": "reference-driven",
        "stage": "proposal",
        "status": "completed",
        "timestamp": "2026-01-01T00:00:00Z",
        "human_approval_required": True,
        "human_approved": True,
        "artifacts": {},
    }), encoding="utf-8")

    findings = check_approval_gate_drift(p)
    assert any(f["code"] == "approval_gate_drift" for f in findings)


def test_compose_without_tool_trace_detected(projects_root: Path):
    p = _project(projects_root)
    for stage in ("assets", "compose"):
        (p / f"checkpoint_{stage}.json").write_text(json.dumps({
            "version": "1.0",
            "project_id": p.name,
            "pipeline_type": "reference-driven",
            "stage": stage,
            "status": "completed",
            "timestamp": "2026-01-01T00:00:00Z",
            "artifacts": {},
        }), encoding="utf-8")
    (p / "events.jsonl").write_text("", encoding="utf-8")

    findings = check_compose_tool_trace(p, "reference-driven")
    assert any(f["code"] == "compose_without_tool_trace" for f in findings)


def test_audit_project_returns_list(projects_root: Path):
    p = _project(projects_root)
    findings = audit_project(p, pipeline_type="reference-driven")
    assert isinstance(findings, list)
