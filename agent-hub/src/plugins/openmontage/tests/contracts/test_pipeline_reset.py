"""pipeline_reset clears checkpoints and canonical artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.openmontage.lib.pipeline_reset import reset_from_stage, reset_to_first_stage
from plugins.openmontage.tests.contracts.test_phase0_contracts import sample_artifact


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def test_reset_archives_canonical_artifact(tmp_path: Path):
    root = tmp_path / "projects"
    proj = root / "p1"
    proj.mkdir(parents=True)
    _write(
        proj / "project.json",
        {
            "project_id": "p1",
            "pipeline_type": "reference-driven",
            "title": "t",
        },
    )
    _write(
        proj / "checkpoint_reference_analysis.json",
        {
            "version": "1.0",
            "project_id": "p1",
            "pipeline_type": "reference-driven",
            "stage": "reference_analysis",
            "status": "completed",
            "timestamp": "2026-08-09T00:00:00Z",
            "artifacts": {
                "video_analysis_brief": sample_artifact("video_analysis_brief"),
            },
            "human_approved": True,
        },
    )
    _write(
        proj / "artifacts" / "video_analysis_brief.json",
        sample_artifact("video_analysis_brief"),
    )

    out = reset_to_first_stage("p1", projects_dir=root)
    assert out["ok"] is True
    assert "reference_analysis" in out["removed_stages"]
    assert "video_analysis_brief" in out["removed_artifacts"]
    assert not (proj / "checkpoint_reference_analysis.json").exists()
    assert not (proj / "artifacts" / "video_analysis_brief.json").exists()
    assert list((proj / "history").glob("checkpoint_reference_analysis_reset_*.json"))
    assert list((proj / "history").glob("artifact_video_analysis_brief_reset_*.json"))


def test_reset_from_mid_stage_keeps_upstream_artifact(tmp_path: Path):
    root = tmp_path / "projects"
    proj = root / "p2"
    proj.mkdir(parents=True)
    _write(
        proj / "project.json",
        {"project_id": "p2", "pipeline_type": "reference-driven", "title": "t"},
    )
    brief = sample_artifact("video_analysis_brief")
    research = sample_artifact("research_brief")
    _write(
        proj / "checkpoint_reference_analysis.json",
        {
            "version": "1.0",
            "project_id": "p2",
            "pipeline_type": "reference-driven",
            "stage": "reference_analysis",
            "status": "completed",
            "timestamp": "2026-08-09T00:00:00Z",
            "artifacts": {"video_analysis_brief": brief},
            "human_approved": True,
        },
    )
    _write(proj / "artifacts" / "video_analysis_brief.json", brief)
    _write(
        proj / "checkpoint_research.json",
        {
            "version": "1.0",
            "project_id": "p2",
            "pipeline_type": "reference-driven",
            "stage": "research",
            "status": "completed",
            "timestamp": "2026-08-09T00:01:00Z",
            "artifacts": {"research_brief": research},
            "human_approved": True,
        },
    )
    _write(proj / "artifacts" / "research_brief.json", research)

    out = reset_from_stage("p2", "research", projects_dir=root)
    assert "research_brief" in out["removed_artifacts"]
    assert (proj / "artifacts" / "video_analysis_brief.json").exists()
    assert not (proj / "artifacts" / "research_brief.json").exists()
