"""om_* channel self-consistency: job status, complete_from_disk, display ok=false."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.openmontage.backlot import stage_runner
from plugins.openmontage.bridge import handle_project
from plugins.openmontage.exec_tools import handle_job, handle_run, handle_state
from plugins.openmontage.lib.checkpoint import read_checkpoint, write_checkpoint
from plugins.openmontage.tests.contracts.test_phase0_contracts import sample_artifact


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    import plugins.openmontage.lib.checkpoint as checkpoint_mod
    import plugins.openmontage.lib.paths as paths_mod
    import plugins.openmontage.lib.project_status as status_mod

    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(paths_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(status_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(checkpoint_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(stage_runner, "PROJECTS_DIR", root)
    return root


def _project(projects_root: Path, project_id: str = "recover-demo") -> Path:
    p = projects_root / project_id
    (p / "artifacts").mkdir(parents=True)
    (p / "runs").mkdir(parents=True)
    (p / "project.json").write_text(
        json.dumps({
            "version": "1.0",
            "project_id": project_id,
            "pipeline_type": "reference-driven",
        }),
        encoding="utf-8",
    )
    return p


def test_om_job_returns_run_status_and_recovery(projects_root: Path):
    project_dir = _project(projects_root)
    brief = sample_artifact("video_analysis_brief")
    (project_dir / "artifacts" / "video_analysis_brief.json").write_text(
        json.dumps(brief), encoding="utf-8",
    )
    write_checkpoint(
        projects_root,
        "recover-demo",
        "reference_analysis",
        "failed",
        artifacts={},
        pipeline_type="reference-driven",
        error="aborted",
    )
    task_id = "abc123dead00"
    (project_dir / "runs" / f"{task_id}.json").write_text(
        json.dumps({
            "task_id": task_id,
            "project_id": "recover-demo",
            "stage": "reference_analysis",
            "status": "failed",
            "error": "stuck",
            "started_at": "2026-01-01T00:00:00+00:00",
            "finished_at": "2026-01-01T00:01:00+00:00",
            "exit_code": 1,
            "pid": 0,
        }),
        encoding="utf-8",
    )
    (project_dir / "runs" / f"{task_id}.log").write_text("line1\n", encoding="utf-8")

    payload = json.loads(
        handle_job({
            "label": "轮询任务",
            "project_id": "recover-demo",
            "task_id": task_id,
        })
    )
    assert payload["ok"] is True
    assert payload["status"] == "failed"
    assert payload["stage"] == "reference_analysis"
    assert payload["next_offset"] == 1
    assert payload["recovery"]["suggested_action"] == "om_state complete_from_disk"
    assert "runtime" in payload
    assert "busy" in payload["runtime"]


def test_complete_from_disk_advances_next_stage(projects_root: Path):
    project_dir = _project(projects_root)
    brief = sample_artifact("video_analysis_brief")
    (project_dir / "artifacts" / "video_analysis_brief.json").write_text(
        json.dumps(brief), encoding="utf-8",
    )
    write_checkpoint(
        projects_root,
        "recover-demo",
        "reference_analysis",
        "failed",
        artifacts={},
        pipeline_type="reference-driven",
        error="aborted",
    )

    payload = json.loads(
        handle_state({
            "project_id": "recover-demo",
            "action": "complete_from_disk",
            "stage": "reference_analysis",
        })
    )
    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert payload["next_stage"] == "research"
    cp = read_checkpoint(projects_root, "recover-demo", "reference_analysis")
    assert cp["status"] == "completed"
    assert "video_analysis_brief" in cp["artifacts"]


def test_complete_from_disk_rejects_gated_stage(projects_root: Path):
    project_dir = _project(projects_root)
    # proposal is gated on reference-driven
    art = sample_artifact("proposal_packet")
    (project_dir / "artifacts" / "proposal_packet.json").write_text(
        json.dumps(art), encoding="utf-8",
    )
    payload = json.loads(
        handle_state({
            "project_id": "recover-demo",
            "action": "complete_from_disk",
            "stage": "proposal",
        })
    )
    assert payload["ok"] is False
    assert "审批" in payload["error"] or "门" in payload["error"]
    assert "diagnostics" in payload


def test_complete_from_disk_missing_file(projects_root: Path):
    _project(projects_root)
    payload = json.loads(
        handle_state({
            "project_id": "recover-demo",
            "action": "complete_from_disk",
            "stage": "reference_analysis",
        })
    )
    assert payload["ok"] is False
    assert "找不到" in payload["error"] or "产物" in payload["error"]
    assert payload["diagnostics"]["artifact"] == "video_analysis_brief"


def test_om_run_busy_returns_diagnostics(projects_root: Path, monkeypatch):
    from datetime import datetime, timezone

    project_dir = _project(projects_root)
    write_checkpoint(
        projects_root,
        "recover-demo",
        "reference_analysis",
        "completed",
        artifacts={"video_analysis_brief": sample_artifact("video_analysis_brief")},
        pipeline_type="reference-driven",
    )
    task_id = "live00000001"
    started = datetime.now(timezone.utc).isoformat()
    (project_dir / ".run.lock").write_text(
        json.dumps({
            "task_id": task_id,
            "stage": "research",
            "pid": 4242,
            "started_at": started,
        }),
        encoding="utf-8",
    )
    (project_dir / "runs" / f"{task_id}.json").write_text(
        json.dumps({
            "task_id": task_id,
            "project_id": "recover-demo",
            "stage": "research",
            "status": "running",
            "pid": 4242,
            "started_at": started,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(stage_runner, "_pid_alive", lambda pid: True)

    payload = json.loads(handle_run({"project_id": "recover-demo"}))
    assert payload["ok"] is False
    assert "diagnostics" in payload
    assert payload["diagnostics"]["busy"] is True
    assert payload["diagnostics"]["blockers"]
    assert payload["diagnostics"]["suggested_actions"]


def test_complete_from_disk_schema_diagnostics(projects_root: Path):
    project_dir = _project(projects_root)
    (project_dir / "artifacts" / "research_brief.json").write_text(
        json.dumps({"title": "bad"}), encoding="utf-8",
    )
    write_checkpoint(
        projects_root,
        "recover-demo",
        "reference_analysis",
        "completed",
        artifacts={"video_analysis_brief": sample_artifact("video_analysis_brief")},
        pipeline_type="reference-driven",
    )
    payload = json.loads(
        handle_state({
            "project_id": "recover-demo",
            "action": "complete_from_disk",
            "stage": "research",
        })
    )
    assert payload["ok"] is False
    assert "schema" in payload["error"] or "校验" in payload["error"]
    schema = payload["diagnostics"]["schema"]
    assert schema["errors"]
    assert payload["diagnostics"]["suggested_actions"]
    expected = payload["diagnostics"]["expected"]
    assert expected["artifact"] == "research_brief"
    assert "claim" in str(expected["properties"]["data_points"])
    assert "stat" not in expected["properties"]["data_points"]["items"]["required"]


def test_om_project_includes_runtime(projects_root: Path):
    _project(projects_root)
    payload = json.loads(handle_project({"project_id": "recover-demo"}))
    assert payload["ok"] is True
    assert "runtime" in payload
    assert payload["runtime"]["busy"] is False
    assert payload["suggested_action"] == "om_run start"
    assert payload["next_runnable_stage"] == "reference_analysis"
    assert payload["gate_blocked"] is False


def test_om_job_work_done_stops_polling_and_clears_busy(projects_root: Path, monkeypatch):
    """checkpoint 已 completed 但 run 仍 running + hub pid 活着 → 应 finalize，勿空转。"""
    from datetime import datetime, timezone

    project_dir = _project(projects_root)
    write_checkpoint(
        projects_root,
        "recover-demo",
        "reference_analysis",
        "completed",
        artifacts={"video_analysis_brief": sample_artifact("video_analysis_brief")},
        pipeline_type="reference-driven",
    )
    brief = sample_artifact("video_analysis_brief")
    (project_dir / "artifacts" / "video_analysis_brief.json").write_text(
        json.dumps(brief), encoding="utf-8",
    )
    task_id = "zombiehub0001"
    started = datetime.now(timezone.utc).isoformat()
    (project_dir / ".run.lock").write_text(
        json.dumps({
            "task_id": task_id,
            "stage": "reference_analysis",
            "pid": 99901,
            "started_at": started,
        }),
        encoding="utf-8",
    )
    (project_dir / "runs" / f"{task_id}.json").write_text(
        json.dumps({
            "task_id": task_id,
            "project_id": "recover-demo",
            "stage": "reference_analysis",
            "status": "running",
            "pid": 99901,
            "started_at": started,
        }),
        encoding="utf-8",
    )
    (project_dir / "runs" / f"{task_id}.log").write_text("done\n", encoding="utf-8")
    monkeypatch.setattr(stage_runner, "_pid_alive", lambda pid: True)

    payload = json.loads(
        handle_job({
            "label": "轮询 research",
            "project_id": "recover-demo",
            "task_id": task_id,
        })
    )
    assert payload["ok"] is True
    assert payload["work_done"] is True
    assert payload["checkpoint_status"] == "completed"
    assert payload["suggested_action"] == "stop_polling"
    assert payload["pid_scope"] == "hub"
    # reconcile 后 run 应已 succeeded，busy 清掉
    assert payload["status"] == "succeeded"
    assert payload["runtime"]["busy"] is False


def test_complete_from_disk_already_done_ignores_busy(projects_root: Path, monkeypatch):
    from datetime import datetime, timezone

    project_dir = _project(projects_root)
    write_checkpoint(
        projects_root,
        "recover-demo",
        "reference_analysis",
        "completed",
        artifacts={"video_analysis_brief": sample_artifact("video_analysis_brief")},
        pipeline_type="reference-driven",
    )
    task_id = "busyblock0001"
    started = datetime.now(timezone.utc).isoformat()
    (project_dir / "runs" / f"{task_id}.json").write_text(
        json.dumps({
            "task_id": task_id,
            "project_id": "recover-demo",
            "stage": "research",
            "status": "running",
            "pid": 4243,
            "started_at": started,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(stage_runner, "_pid_alive", lambda pid: True)

    payload = json.loads(
        handle_state({
            "project_id": "recover-demo",
            "action": "complete_from_disk",
            "stage": "reference_analysis",
        })
    )
    assert payload["ok"] is True
    assert payload.get("already_done") is True
    assert payload["status"] == "completed"
    assert payload["suggested_action"] == "stop_polling"


def test_om_project_rewrites_suggestion_when_busy(projects_root: Path, monkeypatch):
    from datetime import datetime, timezone

    project_dir = _project(projects_root)
    task_id = "live00000002"
    started = datetime.now(timezone.utc).isoformat()
    (project_dir / "runs" / f"{task_id}.json").write_text(
        json.dumps({
            "task_id": task_id,
            "project_id": "recover-demo",
            "stage": "reference_analysis",
            "status": "running",
            "pid": 4244,
            "started_at": started,
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(stage_runner, "_pid_alive", lambda pid: True)

    payload = json.loads(handle_project({"project_id": "recover-demo"}))
    assert payload["ok"] is True
    assert payload["runtime"]["busy"] is True
    assert payload["suggested_action"] == "om_job"
    assert "om_job" in (payload.get("suggested_message") or "")
    assert "blockers" in payload["runtime"]
