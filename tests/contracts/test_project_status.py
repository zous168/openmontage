"""Contract tests for lib.project_status — agent introspection entry point."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent


def test_agent_guide_has_introspection_hard_rule():
    guide = (ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "Agent Introspection" in guide
    assert "HARD RULE" in guide
    assert "lib.project_status" in guide
    assert "Get-ChildItem" in guide


def test_reviewer_mentions_introspection():
    body = (ROOT / "skills" / "meta" / "reviewer.md").read_text(encoding="utf-8")
    assert "Improvised orchestration" in body
    assert "lib.project_status" in body


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    import lib.paths as paths_mod

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(paths_mod, "PROJECTS_DIR", root)
    return root


def _minimal_project(projects_root: Path, project_id: str = "status-demo") -> Path:
    p = projects_root / project_id
    (p / "artifacts").mkdir(parents=True)
    (p / "project.json").write_text(
        json.dumps({
            "version": "1.0",
            "project_id": project_id,
            "title": "Demo",
            "pipeline_type": "reference-driven",
        }),
        encoding="utf-8",
    )
    return p


def test_build_project_status_next_stage(projects_root: Path):
    from lib.project_status import build_project_status

    _minimal_project(projects_root)
    status = build_project_status("status-demo", projects_dir=projects_root)
    assert status["next_stage"] == "reference_analysis"
    assert status["director_skill"] == "skills/pipelines/reference-driven/reference-director.md"
    assert status["completed_stages"] == []


def test_cli_json_output(projects_root: Path, monkeypatch):
    import lib.paths as paths_mod

    monkeypatch.setattr(paths_mod, "PROJECTS_DIR", projects_root)
    _minimal_project(projects_root)

    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT)
    env["OPENMONTAGE_PROJECTS_DIR"] = str(projects_root)
    proc = subprocess.run(
        [sys.executable, "-m", "lib.project_status", "status-demo", "--json"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["project_id"] == "status-demo"
    assert payload["next_stage"] == "reference_analysis"
