"""Unit tests for Backlot BoardState derivation (backlot/state.py)."""

import json
import time
from pathlib import Path

import pytest

from plugins.openmontage.backlot import state as state_mod
from plugins.openmontage.backlot.state import list_projects, load_board_state, summarize_project


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", root)
    return root


def _make_project(root: Path, pid: str) -> Path:
    p = root / pid
    (p / "artifacts").mkdir(parents=True)
    (p / "assets" / "images").mkdir(parents=True)
    (p / "renders").mkdir()
    return p


def _write(p: Path, data: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data), encoding="utf-8")


SCENE_PLAN = {
    "version": "1.0",
    "scenes": [
        {"id": "sc1", "type": "generated", "description": "opening",
         "start_seconds": 0, "end_seconds": 4, "script_section_id": "s1",
         "hero_moment": False},
        {"id": "sc2", "type": "generated", "description": "climax",
         "start_seconds": 4, "end_seconds": 10, "hero_moment": True},
    ],
}

SCRIPT = {
    "version": "1.0", "title": "Test Film", "total_duration_seconds": 10,
    "sections": [
        {"id": "s1", "text": "It begins.", "start_seconds": 0, "end_seconds": 4},
        {"id": "s2", "text": "It ends.", "start_seconds": 4, "end_seconds": 10},
    ],
}


class TestBoardState:
    def test_full_project(self, projects_root):
        p = _make_project(projects_root, "film")
        _write(p / "project.json", {"project_id": "film", "title": "My Film",
                                    "pipeline_type": "cinematic", "created_at": "2026-01-01T00:00:00Z"})
        _write(p / "artifacts" / "scene_plan.json", SCENE_PLAN)
        _write(p / "artifacts" / "script.json", SCRIPT)
        img = p / "assets" / "images" / "sc1.png"
        img.write_bytes(b"fake")
        _write(p / "artifacts" / "asset_manifest.json", {
            "version": "1.0",
            "assets": [
                {"id": "a1", "type": "image", "path": "assets/images/sc1.png",
                 "scene_id": "sc1", "source_tool": "t", "cost_usd": 0.1},
                {"id": "a2", "type": "image", "path": "assets/images/missing.png",
                 "scene_id": "sc2", "source_tool": "t"},
            ],
            "total_cost_usd": 0.1,
        })
        _write(p / "checkpoint_script.json", {
            "version": "1.0", "project_id": "film", "pipeline_type": "cinematic",
            "stage": "script", "status": "completed", "timestamp": "2026-01-01T01:00:00Z",
            "human_approved": True, "artifacts": {},
        })

        s = load_board_state(p)
        assert s["title"] == "My Film"
        assert s["pipeline"]["pipeline_type"] == "cinematic"
        assert s["pipeline"]["label_zh"] == "电影级短片"
        assert s["pipeline"]["known"] is True
        board = s["storyboard"]
        assert len(board["scenes"]) == 2
        sc1, sc2 = board["scenes"]
        assert sc1["narration"] == "It begins."
        assert sc1["visual"]["exists"] is True
        # sc2 has no script_section_id -> joined by timing overlap
        assert sc2["narration"] == "It ends."
        assert sc2["hero_moment"] is True
        assert sc2["visual"]["exists"] is False  # missing file flagged
        script_stage = next(x for x in s["stages"] if x["name"] == "script")
        assert script_stage["status"] == "completed"
        assert script_stage["produces"] == ["script"]
        proposal_stage = next(x for x in s["stages"] if x["name"] == "proposal")
        assert proposal_stage["produces"] == ["proposal_packet", "decision_log"]

    def test_gate_skip_detection(self, projects_root):
        p = _make_project(projects_root, "sneaky")
        # completed on a gated stage with no awaiting_human history and no
        # human_approved -> gate_skipped flag
        _write(p / "checkpoint_script.json", {
            "version": "1.0", "project_id": "sneaky", "pipeline_type": "cinematic",
            "stage": "script", "status": "completed",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        s = load_board_state(p)
        script_stage = next(x for x in s["stages"] if x["name"] == "script")
        assert script_stage["gate_skipped"] is True

        # with an archived awaiting_human version, the gate was honored
        _write(p / "history" / "checkpoint_script_20260101.json", {
            "stage": "script", "status": "awaiting_human",
        })
        s2 = load_board_state(p)
        script_stage2 = next(x for x in s2["stages"] if x["name"] == "script")
        assert script_stage2["gate_skipped"] is False

    def test_generating_state_from_events(self, projects_root):
        p = _make_project(projects_root, "live")
        _write(p / "artifacts" / "scene_plan.json", SCENE_PLAN)
        events = [
            {"ts": "t1", "tool": "img", "event": "start", "scene_id": "sc1"},
            {"ts": "t2", "tool": "img", "event": "finish", "scene_id": "sc1"},
            {"ts": "t3", "tool": "img", "event": "start", "scene_id": "sc2"},
        ]
        (p / "events.jsonl").write_text(
            "\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
        s = load_board_state(p)
        cards = {c["id"]: c for c in s["storyboard"]["scenes"]}
        assert cards["sc1"]["generating"] is False
        assert cards["sc2"]["generating"] is True
        assert cards["sc2"]["generating_tool"] == "img"

    def test_degraded_project_never_crashes(self, projects_root):
        p = projects_root / "bare"
        p.mkdir()
        (p / "something.mp4").write_bytes(b"x")
        (p / "artifacts").mkdir()
        (p / "artifacts" / "script.json").write_text("NOT JSON", encoding="utf-8")
        s = load_board_state(p)
        assert s["has_pipeline_state"] is False
        assert s["storyboard"] is None
        assert s["media"]["renders"][0]["path"] == "something.mp4"
        assert s["media"]["renders"][0]["at_root"] is True

    def test_undeclared_stage_surfaces(self, projects_root):
        p = _make_project(projects_root, "legacy")
        _write(p / "checkpoint_idea.json", {
            "version": "1.0", "project_id": "legacy", "pipeline_type": "cinematic",
            "stage": "idea", "status": "completed",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        s = load_board_state(p)
        idea = next(x for x in s["stages"] if x["name"] == "idea")
        assert idea.get("undeclared") is True


class TestLibrary:
    def test_list_projects_sorts_live_first(self, projects_root):
        old = _make_project(projects_root, "old-film")
        _write(old / "checkpoint_script.json", {"stage": "script", "status": "completed"})
        # backdate everything in old-film
        import os
        past = time.time() - 60 * 60 * 24 * 30
        for f in old.rglob("*"):
            if f.is_file():
                os.utime(f, (past, past))

        fresh = _make_project(projects_root, "fresh-film")
        _write(fresh / "checkpoint_script.json", {"stage": "script", "status": "in_progress"})

        projects = list_projects(projects_root)
        assert [p["project_id"] for p in projects][0] == "fresh-film"
        assert projects[0]["live"] is True
        assert projects[1]["live"] is False

    def test_underscore_dirs_skipped(self, projects_root):
        (projects_root / "_analysis").mkdir()
        _make_project(projects_root, "real")
        ids = [p["project_id"] for p in list_projects(projects_root)]
        assert ids == ["real"]

    def test_demo_projects_hidden_from_library(self, projects_root):
        demo = _make_project(projects_root, "backlot-demo-run")
        _write(demo / "project.json", {
            "title": "The Last Lighthouse",
            "pipeline_type": "cinematic",
        })
        real = _make_project(projects_root, "real-film")
        _write(real / "project.json", {"title": "Real", "pipeline_type": "cinematic"})
        ids = [p["project_id"] for p in list_projects(projects_root)]
        assert ids == ["real-film"]
        assert summarize_project(demo)["title"] == "The Last Lighthouse"

    def test_demo_flag_hides_from_library(self, projects_root):
        demo = _make_project(projects_root, "my-demo")
        _write(demo / "project.json", {
            "title": "Demo",
            "pipeline_type": "cinematic",
            "demo": True,
        })
        _make_project(projects_root, "real")
        _write((projects_root / "real" / "project.json"), {
            "title": "Real",
            "pipeline_type": "cinematic",
        })
        ids = [p["project_id"] for p in list_projects(projects_root)]
        assert ids == ["real"]

    def test_summary_shape(self, projects_root):
        p = _make_project(projects_root, "sum")
        _write(p / "project.json", {"title": "Sum", "pipeline_type": "cinematic"})
        _write(p / "checkpoint_script.json", {
            "stage": "script", "status": "awaiting_human",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        summary = summarize_project(p)
        assert summary["awaiting_human"] is True
        assert summary["active_stage"] == "script"
        assert summary["pipeline_label_zh"] == "电影级短片"

    def test_pipeline_label_zh_talking_head(self, projects_root):
        p = _make_project(projects_root, "talk-show")
        _write(p / "project.json", {"title": "Talk", "pipeline_type": "talking-head"})
        s = load_board_state(p)
        assert s["pipeline"]["label_zh"] == "真人口播剪辑"
        assert summarize_project(p)["pipeline_label_zh"] == "真人口播剪辑"


class TestFindingsFixes:
    """Regression tests for dogfood findings F-04/F-05."""

    def test_artifact_refs_outside_project_are_not_followed(self, projects_root, tmp_path):
        # F-04: a checkpoint pointing at JSON outside the project tree
        # must not surface that file on the board.
        secret = tmp_path / "secret.json"
        secret.write_text(json.dumps({"version": "1.0", "leaked": True}), encoding="utf-8")
        p = _make_project(projects_root, "sneaky-ref")
        _write(p / "checkpoint_script.json", {
            "stage": "script", "status": "completed",
            "timestamp": "2026-01-01T01:00:00Z",
            "artifacts": {"script": str(secret)},
        })
        s = load_board_state(p)
        assert "script" not in s["artifacts"]

    def test_inside_project_absolute_refs_still_resolve(self, projects_root):
        p = _make_project(projects_root, "abs-ref")
        _write(p / "artifacts" / "inline_script.json", SCRIPT)
        _write(p / "checkpoint_script.json", {
            "stage": "script", "status": "completed",
            "timestamp": "2026-01-01T01:00:00Z",
            "artifacts": {"script": str((p / "artifacts" / "inline_script.json").resolve())},
        })
        s = load_board_state(p)
        assert s["artifacts"]["script"]["title"] == "Test Film"

    def test_remotion_public_path_resolves_to_assets(self, projects_root):
        from plugins.openmontage.backlot.state import _asset_entry

        p = _make_project(projects_root, "remotion-paths")
        img_dir = p / "assets" / "images"
        img_dir.mkdir(parents=True, exist_ok=True)
        (img_dir / "sc1.jpg").write_bytes(b"\xff\xd8\xff")
        entry = _asset_entry(
            p,
            {
                "id": "img_sc1",
                "type": "image",
                "path": "remotion-paths/images/sc1.jpg",
                "scene_id": "sc1",
            },
        )
        assert entry["exists"] is True
        assert entry["renderable"] is True
        assert entry["path"] == "assets/images/sc1.jpg"

    def test_stalled_in_progress_stage_flagged(self, projects_root):
        # F-05: an in_progress stage with no recent activity reads stalled.
        import os
        p = _make_project(projects_root, "wedged")
        _write(p / "checkpoint_research.json", {
            "stage": "research", "status": "in_progress",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        past = time.time() - 30 * 60
        for f in p.rglob("*"):
            if f.is_file():
                os.utime(f, (past, past))
        s = load_board_state(p)
        research = next(x for x in s["stages"] if x["name"] == "research")
        assert research["stalled"] is True
        assert research["stalled_minutes"] >= 29

    def test_fresh_in_progress_not_stalled(self, projects_root):
        p = _make_project(projects_root, "busy")
        _write(p / "checkpoint_research.json", {
            "stage": "research", "status": "in_progress",
            "timestamp": "2026-01-01T01:00:00Z", "artifacts": {},
        })
        s = load_board_state(p)
        research = next(x for x in s["stages"] if x["name"] == "research")
        assert "stalled" not in research

    def test_pending_stage_inferred_in_progress_from_events(self, projects_root):
        """Tool activity before the first checkpoint should not read as 待开始."""
        p = _make_project(projects_root, "live-run")
        _write(p / "project.json", {
            "project_id": "live-run",
            "title": "Live",
            "pipeline_type": "reference-driven",
        })
        (p / "events.jsonl").write_text(
            '{"ts":"2026-08-01T13:05:20Z","tool":"video_analyzer","event":"start"}\n',
            encoding="utf-8",
        )
        s = load_board_state(p)
        ref = next(x for x in s["stages"] if x["name"] == "reference_analysis")
        assert ref["status"] == "in_progress"
        assert ref.get("inferred_from_events") is True

    def test_downstream_completed_capped_when_upstream_awaiting(self, projects_root):
        """Later checkpoints must not show 已完成 while an earlier stage awaits approval."""
        p = _make_project(projects_root, "gate-skip")
        _write(p / "project.json", {
            "project_id": "gate-skip",
            "title": "Gate",
            "pipeline_type": "reference-driven",
        })
        _write(p / "checkpoint_assets.json", {
            "stage": "assets", "status": "awaiting_human",
            "timestamp": "2026-01-01T05:00:00Z", "artifacts": {},
        })
        _write(p / "checkpoint_edit.json", {
            "stage": "edit", "status": "completed",
            "timestamp": "2026-01-01T06:00:00Z", "artifacts": {},
        })
        _write(p / "checkpoint_compose.json", {
            "stage": "compose", "status": "completed",
            "timestamp": "2026-01-01T07:00:00Z", "artifacts": {},
        })
        s = load_board_state(p)
        by_name = {st["name"]: st for st in s["stages"]}
        assert by_name["assets"]["status"] == "awaiting_human"
        assert by_name["edit"]["status"] == "pending"
        assert by_name["edit"].get("blocked_by_upstream") is True
        assert by_name["edit"].get("raw_status") == "completed"
        assert by_name["compose"]["status"] == "pending"
        assert by_name["compose"].get("blocked_by_upstream") is True

    def test_headless_run_does_not_promote_blocked_downstream(self, projects_root):
        """上游待审批时，runs/*.json 不得把 blocked 下游标成进行中。"""
        p = _make_project(projects_root, "await-run")
        _write(p / "project.json", {
            "project_id": "await-run",
            "title": "Await Run",
            "pipeline_type": "reference-driven",
        })
        _write(p / "checkpoint_script.json", {
            "version": "1.0", "project_id": "await-run",
            "pipeline_type": "reference-driven",
            "stage": "script", "status": "completed",
            "timestamp": "2026-01-01T03:00:00Z",
            "human_approved": True, "artifacts": {},
        })
        _write(p / "checkpoint_scene_plan.json", {
            "version": "1.0", "project_id": "await-run",
            "pipeline_type": "reference-driven",
            "stage": "scene_plan", "status": "awaiting_human",
            "timestamp": "2026-01-01T04:00:00Z", "artifacts": {},
        })
        runs_dir = p / "runs"
        runs_dir.mkdir()
        _write(runs_dir / "orphan01.json", {
            "task_id": "orphan01",
            "project_id": "await-run",
            "stage": "assets",
            "status": "running",
            "started_at": "2026-01-01T05:00:00Z",
        })
        s = load_board_state(p)
        by_name = {st["name"]: st for st in s["stages"]}
        assert by_name["scene_plan"]["status"] == "awaiting_human"
        assert by_name["assets"]["status"] == "pending"
        assert by_name["assets"].get("blocked_by_upstream") is True
        assert not by_name["assets"].get("inferred_from_run")

    def test_failed_stage_error_from_metadata(self, projects_root):
        """Agent may write failure reason under metadata.error."""
        p = _make_project(projects_root, "fail-meta")
        _write(p / "project.json", {
            "project_id": "fail-meta",
            "title": "Fail Meta",
            "pipeline_type": "reference-driven",
        })
        _write(p / "checkpoint_assets.json", {
            "version": "1.0", "project_id": "fail-meta",
            "pipeline_type": "reference-driven",
            "stage": "assets", "status": "failed",
            "timestamp": "2026-01-01T05:00:00Z",
            "metadata": {"error": "video_generation 不可用"},
        })
        s = load_board_state(p)
        assets = next(x for x in s["stages"] if x["name"] == "assets")
        assert assets["error"] == "video_generation 不可用"

    def test_failed_stage_error_from_run(self, projects_root):
        """Failed checkpoint without error field inherits message from runs/*.json."""
        p = _make_project(projects_root, "fail-run")
        _write(p / "project.json", {
            "project_id": "fail-run",
            "title": "Fail",
            "pipeline_type": "reference-driven",
        })
        _write(p / "checkpoint_assets.json", {
            "version": "1.0", "project_id": "fail-run",
            "pipeline_type": "reference-driven",
            "stage": "assets", "status": "failed",
            "timestamp": "2026-01-01T05:00:00Z", "artifacts": {},
        })
        runs_dir = p / "runs"
        runs_dir.mkdir()
        _write(runs_dir / "dead01.json", {
            "task_id": "dead01",
            "project_id": "fail-run",
            "stage": "assets",
            "status": "failed",
            "error": "image_selector 超时",
            "started_at": "2026-01-01T05:00:00Z",
        })
        s = load_board_state(p)
        assets = next(x for x in s["stages"] if x["name"] == "assets")
        assert assets["status"] == "failed"
        assert assets["error"] == "image_selector 超时"

    def test_failed_stage_error_from_succeeded_run_log(self, projects_root):
        """Agent may exit 0 after writing failed checkpoint; log_tail has agent_run_summary."""
        p = _make_project(projects_root, "fail-log")
        _write(p / "project.json", {
            "project_id": "fail-log",
            "title": "Fail Log",
            "pipeline_type": "reference-driven",
        })
        _write(p / "checkpoint_assets.json", {
            "version": "1.0", "project_id": "fail-log",
            "pipeline_type": "reference-driven",
            "stage": "assets", "status": "failed",
            "timestamp": "2026-01-01T05:00:00Z", "artifacts": {},
        })
        runs_dir = p / "runs"
        runs_dir.mkdir()
        _write(runs_dir / "ok01.json", {
            "task_id": "ok01",
            "project_id": "fail-log",
            "stage": "assets",
            "status": "succeeded",
            "exit_code": 0,
            "error": None,
            "log_tail": "agent_run_summary: failed — video_generation 无可用 provider",
            "started_at": "2026-01-01T05:00:00Z",
            "finished_at": "2026-01-01T05:10:00Z",
        })
        s = load_board_state(p)
        assets = next(x for x in s["stages"] if x["name"] == "assets")
        assert assets["error"] == "failed — video_generation 无可用 provider"

    def test_rerun_assets_in_progress_keeps_downstream_completed(self, projects_root):
        """Re-running assets must not demote edit/compose or infer publish."""
        p = _make_project(projects_root, "rerun-live")
        _write(p / "project.json", {
            "project_id": "rerun-live",
            "title": "Rerun",
            "pipeline_type": "reference-driven",
        })
        _write(p / "checkpoint_scene_plan.json", {
            "stage": "scene_plan", "status": "completed",
            "timestamp": "2026-01-01T04:00:00Z", "artifacts": {},
        })
        _write(p / "checkpoint_assets.json", {
            "stage": "assets", "status": "in_progress",
            "timestamp": "2026-08-01T13:54:01Z", "artifacts": {},
        })
        _write(p / "checkpoint_edit.json", {
            "stage": "edit", "status": "completed",
            "timestamp": "2026-08-01T13:50:00Z", "artifacts": {},
        })
        _write(p / "checkpoint_compose.json", {
            "stage": "compose", "status": "completed",
            "timestamp": "2026-08-01T13:51:00Z", "artifacts": {},
        })
        (p / "events.jsonl").write_text(
            '{"ts":"2026-08-01T13:54:05+00:00","tool":"transcriber","event":"start"}\n'
            '{"ts":"2026-08-01T13:54:23+00:00","tool":"transcriber","event":"finish","success":true}\n',
            encoding="utf-8",
        )
        s = load_board_state(p)
        by_name = {st["name"]: st for st in s["stages"]}
        assert by_name["assets"]["status"] == "in_progress"
        assert by_name["edit"]["status"] == "completed"
        assert by_name["compose"]["status"] == "completed"
        assert by_name["publish"]["status"] == "pending"
        assert not by_name["publish"].get("inferred_from_events")

    def test_recent_activity_without_active_stage_not_live(self, projects_root):
        """Finished run: recent checkpoint writes must not keep the header live."""
        p = _make_project(projects_root, "done-run")
        _write(p / "project.json", {
            "project_id": "done-run",
            "title": "Done",
            "pipeline_type": "reference-driven",
        })
        for stage in ("scene_plan", "assets", "edit", "compose"):
            _write(p / f"checkpoint_{stage}.json", {
                "stage": stage, "status": "completed",
                "timestamp": "2026-08-01T13:57:00Z", "artifacts": {},
            })
        (p / "events.jsonl").write_text(
            '{"ts":"2026-08-01T13:57:02+00:00","tool":"video_compose","event":"finish","success":true}\n',
            encoding="utf-8",
        )
        s = load_board_state(p)
        assert s["live"] is False
        publish = next(x for x in s["stages"] if x["name"] == "publish")
        assert publish["status"] == "pending"

    def test_stale_unfinished_tool_event_not_live(self, projects_root):
        """Interrupted run: orphan tool start must not keep the board live."""
        p = _make_project(projects_root, "orphan-start")
        _write(p / "project.json", {
            "project_id": "orphan-start",
            "title": "Orphan",
            "pipeline_type": "reference-driven",
        })
        for stage in ("scene_plan", "assets", "edit", "compose"):
            _write(p / f"checkpoint_{stage}.json", {
                "stage": stage, "status": "completed",
                "timestamp": "2026-08-01T14:05:00Z", "artifacts": {},
            })
        (p / "events.jsonl").write_text(
            '{"ts":"2026-01-01T12:00:00+00:00","tool":"hyperframes_compose","event":"start"}\n',
            encoding="utf-8",
        )
        s = load_board_state(p)
        assert s["live"] is False

    def test_recent_tool_finish_infers_in_progress_before_checkpoint(self, projects_root):
        """Tool finished recently but checkpoint not written yet → show 进行中."""
        p = _make_project(projects_root, "cp-lag")
        _write(p / "project.json", {
            "project_id": "cp-lag",
            "title": "Lag",
            "pipeline_type": "reference-driven",
        })
        (p / "events.jsonl").write_text(
            '{"ts":"2026-08-01T13:05:20+00:00","tool":"video_analyzer","event":"start"}\n'
            '{"ts":"2026-08-01T13:05:43+00:00","tool":"video_analyzer","event":"finish","success":true,"duration_s":22.9}\n',
            encoding="utf-8",
        )
        s = load_board_state(p)
        ref = next(x for x in s["stages"] if x["name"] == "reference_analysis")
        assert ref["status"] == "in_progress"
        assert ref.get("inferred_from_events") is True


class TestStoryboardVisualSelection:
    """The renderable / snapshot / takes logic in _build_storyboard.

    Covers the atelier-thumbnail work: a .tsx composition asset is not a
    showable visual; a missing raster file still surfaces as an indicator;
    an existing SVG diagram IS showable; snapshots/<id>.png is the fallback.
    """

    def _project_with_scenes(self, root, scenes, assets):
        p = _make_project(root, "vis")
        _write(p / "project.json", {"pipeline_type": "cinematic"})
        _write(p / "artifacts" / "scene_plan.json", {"version": "1.0", "scenes": scenes})
        _write(p / "artifacts" / "asset_manifest.json", {"version": "1.0", "assets": assets})
        return p

    def _card(self, p, scene_id):
        s = load_board_state(p)
        return next(c for c in s["storyboard"]["scenes"] if c["id"] == scene_id)

    def test_existing_tsx_animation_is_not_a_visual(self, projects_root):
        # A bespoke composition asset exists on disk but can't be shown.
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "animation", "description": "morph",
              "start_seconds": 0, "end_seconds": 5}],
            [{"id": "a1", "type": "animation", "path": "Composition.tsx", "scene_id": "sc1",
              "source_tool": "atelier_remotion"}],
        )
        (p / "Composition.tsx").write_text("export const X = 1;", encoding="utf-8")
        card = self._card(p, "sc1")
        # No snapshot yet -> no renderable visual, falls to placeholder (None).
        assert card["visual"] is None
        assert card["takes"] == []

    def test_snapshot_is_the_fallback_for_animation_scene(self, projects_root):
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "animation", "description": "morph",
              "start_seconds": 0, "end_seconds": 5}],
            [{"id": "a1", "type": "animation", "path": "Composition.tsx", "scene_id": "sc1",
              "source_tool": "atelier_remotion"}],
        )
        (p / "Composition.tsx").write_text("x", encoding="utf-8")
        (p / "snapshots").mkdir()
        (p / "snapshots" / "sc1.png").write_bytes(b"\x89PNG")
        card = self._card(p, "sc1")
        assert card["visual"] is not None
        assert card["visual"]["snapshot"] is True
        assert card["visual"]["renderable"] is True
        assert card["visual"]["path"].endswith("sc1.png")

    def test_snapshot_matches_id_underscore_suffix(self, projects_root):
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "animation", "start_seconds": 0, "end_seconds": 5}],
            [],
        )
        (p / "snapshots").mkdir()
        (p / "snapshots" / "sc1_hero.png").write_bytes(b"\x89PNG")
        card = self._card(p, "sc1")
        assert card["visual"] is not None and card["visual"]["snapshot"] is True

    def test_existing_svg_diagram_is_renderable(self, projects_root):
        # Regression guard: an existing non-raster-but-showable image (.svg)
        # must remain a visual, not be dropped to a placeholder.
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "diagram", "start_seconds": 0, "end_seconds": 5}],
            [{"id": "a1", "type": "diagram", "path": "assets/images/d.svg", "scene_id": "sc1",
              "source_tool": "diagram_gen"}],
        )
        (p / "assets" / "images" / "d.svg").write_text("<svg/>", encoding="utf-8")
        card = self._card(p, "sc1")
        assert card["visual"] is not None
        assert card["visual"]["exists"] is True
        assert card["visual"]["renderable"] is True

    def test_missing_raster_file_still_flagged(self, projects_root):
        # The "asset in manifest, file missing" indicator must survive.
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "generated", "start_seconds": 0, "end_seconds": 5}],
            [{"id": "a1", "type": "image", "path": "assets/images/gone.png", "scene_id": "sc1",
              "source_tool": "t"}],
        )
        card = self._card(p, "sc1")
        assert card["visual"] is not None
        assert card["visual"]["exists"] is False

    def test_renderable_prefers_existing_and_takes_exclude_missing(self, projects_root):
        # Two takes: one real png, one missing. Active = the real one;
        # takes carries only renderable (showable) entries.
        p = self._project_with_scenes(
            projects_root,
            [{"id": "sc1", "type": "generated", "start_seconds": 0, "end_seconds": 5}],
            [
                {"id": "a1", "type": "image", "path": "assets/images/real.png", "scene_id": "sc1", "source_tool": "t"},
                {"id": "a2", "type": "image", "path": "assets/images/missing.png", "scene_id": "sc1", "source_tool": "t"},
            ],
        )
        (p / "assets" / "images" / "real.png").write_bytes(b"\x89PNG")
        card = self._card(p, "sc1")
        assert card["visual"]["exists"] is True
        assert card["visual"]["path"].endswith("real.png")
        assert [t["path"].split("/")[-1] for t in card["takes"]] == ["real.png"]


class TestSourceMedia:
    def test_source_mkv_with_mp4_preview(self, projects_root):
        p = _make_project(projects_root, "koubo")
        _write(p / "project.json", {
            "project_id": "koubo", "title": "口播", "pipeline_type": "talking-head",
        })
        _write(p / "meta.json", {
            "production_inputs": {"source_media_path": "assets/video/source.mkv"},
        })
        (p / "assets" / "video").mkdir(parents=True, exist_ok=True)
        (p / "assets" / "video" / "source.mkv").write_bytes(b"mkv")
        (p / "assets" / "video" / "trim_30s.mp4").write_bytes(b"mp4")
        (p / "assets" / "images" / "frame_01.jpg").write_bytes(b"jpeg")
        _write(p / "artifacts" / "source_media_review.json", {
            "version": "1.0",
            "files": [{
                "path": str(p / "assets" / "video" / "source.mkv"),
                "media_type": "video",
                "technical_probe": {"duration_seconds": 121.5, "resolution": "720x1280"},
                "content_summary": "Vertical talking-head.",
            }],
            "summary": "Single vertical MKV talking-head.",
        })

        s = load_board_state(p)
        sm = s["source_media"]
        assert sm is not None
        assert sm["path"] == "assets/video/source.mkv"
        assert sm["exists"] is True
        assert sm["playable"] is False
        assert sm["poster"] == "assets/images/frame_01.jpg"
        assert sm["preview_path"] == "assets/video/trim_30s.mp4"
        assert sm["playback_path"] == "assets/video/trim_30s.mp4"
        assert sm["duration_seconds"] == 121.5

    def test_source_hevc_mp4_uses_h264_preview(self, projects_root):
        p = _make_project(projects_root, "koubo2")
        _write(p / "project.json", {
            "project_id": "koubo2", "title": "口播2", "pipeline_type": "talking-head",
        })
        _write(p / "meta.json", {
            "production_inputs": {"source_media_path": "assets/video/source.mp4"},
        })
        (p / "assets" / "video").mkdir(parents=True, exist_ok=True)
        (p / "assets" / "video" / "source.mp4").write_bytes(b"mp4")
        (p / "assets" / "video" / "trim_work.mp4").write_bytes(b"h264")
        _write(p / "artifacts" / "source_media_review.json", {
            "version": "1.0",
            "files": [{
                "path": str(p / "assets" / "video" / "source.mp4"),
                "media_type": "video",
                "technical_probe": {
                    "duration_seconds": 28.12,
                    "resolution": "1080x1920",
                    "codec": "hevc",
                },
            }],
        })

        s = load_board_state(p)
        sm = s["source_media"]
        assert sm["playable"] is False
        assert sm["preview_path"] == "assets/video/trim_work.mp4"
        assert sm["playback_path"] == "assets/video/trim_work.mp4"
        assert sm["codec"] == "hevc"


class TestProjectSummary:
    def test_project_summary_aggregates_artifacts_and_media(self, projects_root):
        p = _make_project(projects_root, "proj-sum")
        _write(p / "project.json", {
            "project_id": "proj-sum",
            "title": "Proj Sum",
            "pipeline_type": "cinematic",
        })
        _write(p / "artifacts" / "scene_plan.json", SCENE_PLAN)
        _write(p / "artifacts" / "script.json", SCRIPT)
        img = p / "assets" / "images" / "sc1.png"
        img.write_bytes(b"fake")
        _write(p / "artifacts" / "asset_manifest.json", {
            "version": "1.0",
            "assets": [
                {"id": "a1", "type": "image", "path": "assets/images/sc1.png", "scene_id": "sc1"},
            ],
        })
        render = p / "renders" / "final.mp4"
        render.write_bytes(b"mp4")
        _write(p / "artifacts" / "render_report.json", {
            "version": "1.0",
            "outputs": [{
                "path": "renders/final.mp4",
                "format": "mp4",
                "resolution": "1920x1080",
                "duration_seconds": 10,
            }],
        })

        s = load_board_state(p)
        summary = s["project_summary"]
        names = {a["name"] for a in summary["artifacts"]}
        assert "script" in names
        assert "asset_manifest" in names
        assert "render_report" in names
        media_paths = {m["path"] for m in summary["media"]}
        assert "assets/images/sc1.png" in media_paths
        assert "renders/final.mp4" in media_paths
        assert summary["counts"]["artifacts_present"] >= 3
        assert summary["counts"]["media"] >= 2
        script_entry = next(a for a in summary["artifacts"] if a["name"] == "script")
        assert script_entry["path"] == "artifacts/script.json"

    def test_stage_outputs_from_checkpoint_artifacts(self, projects_root):
        p = _make_project(projects_root, "proj-out")
        _write(p / "project.json", {
            "project_id": "proj-out",
            "title": "Outputs",
            "pipeline_type": "cinematic",
        })
        _write(p / "artifacts" / "script.json", SCRIPT)
        _write(p / "checkpoint_script.json", {
            "version": "1.0",
            "project_id": "proj-out",
            "pipeline_type": "cinematic",
            "stage": "script",
            "status": "completed",
            "timestamp": "2026-01-01T01:00:00Z",
            "artifacts": {"script": SCRIPT},
        })

        s = load_board_state(p)
        script_stage = next(st for st in s["stages"] if st["name"] == "script")
        assert script_stage["outputs"] == ["script"]

        summary = s["project_summary"]
        script_group = next(g for g in summary["by_stage"] if g["stage"] == "script")
        names = {a["name"] for a in script_group["artifacts"]}
        assert names == {"script"}
        script_entry = next(a for a in summary["artifacts"] if a["name"] == "script")
        assert script_entry["stages"] == ["script"]

    def test_project_summary_includes_publish_export_cover(self, projects_root):
        p = _make_project(projects_root, "proj-pub")
        _write(p / "project.json", {
            "project_id": "proj-pub",
            "title": "Publish Cover",
            "pipeline_type": "cinematic",
        })
        thumb = p / "exports" / "thumbnails" / "thumbnail.jpg"
        thumb.parent.mkdir(parents=True, exist_ok=True)
        thumb.write_bytes(b"fake-jpg")
        export_video = p / "exports" / "video" / "output.mp4"
        export_video.parent.mkdir(parents=True, exist_ok=True)
        export_video.write_bytes(b"mp4")
        _write(p / "artifacts" / "publish_log.json", {
            "version": "1.0",
            "entries": [{
                "platform": "douyin",
                "status": "exported",
                "export_path": str(p / "exports"),
                "timestamp": "2026-01-01T12:00:00Z",
            }],
        })

        s = load_board_state(p)
        media_paths = {m["path"] for m in s["project_summary"]["media"]}
        assert "exports/thumbnails/thumbnail.jpg" in media_paths
        assert "exports/video/output.mp4" in media_paths
        cover = next(
            m for m in s["project_summary"]["media"]
            if m["path"] == "exports/thumbnails/thumbnail.jpg"
        )
        assert cover["label"] == "封面"
        assert cover["source_artifact"] == "publish_log"

    def test_board_state_includes_deliverable_from_meta(self, projects_root):
        p = _make_project(projects_root, "proj-deliverable")
        _write(p / "project.json", {
            "project_id": "proj-deliverable",
            "title": "Deliverable",
            "pipeline_type": "reference-driven",
        })
        _write(p / "meta.json", {
            "version": "1.0",
            "production_inputs": {
                "target_platform": "douyin",
                "aspect_ratio": "9:16",
                "quality_tier": "720p",
                "fps": 30,
            },
        })

        s = load_board_state(p)
        assert s["deliverable"]["resolution"] == "720x1280"
        assert s["deliverable"]["aspect_ratio"] == "9:16"
        assert s["deliverable"]["quality_tier"] == "720p"

    def test_board_state_style_playbook_label_zh(self, projects_root):
        p = _make_project(projects_root, "styled")
        _write(p / "project.json", {
            "project_id": "styled",
            "title": "风格测试",
            "pipeline_type": "reference-driven",
            "style_playbook": "clean-professional",
        })

        s = load_board_state(p)
        assert s["style_playbook"] == "clean-professional"
        assert s["style_playbook_label_zh"] == "干净专业"


class TestStoryboardImagePromptProvenance(TestStoryboardVisualSelection):
    """Image scenes must surface the EXACT recorded prompt (the text sent
    to the model), not a reconstructed approximation."""

    def _image_project(self, projects_root):
        exact = ("扁平矢量科普插画：一束白色光束穿过三棱镜分解成彩虹，"
                 "深蓝夜空背景，现代教育插画风格")
        p = self._project_with_scenes(
            projects_root,
            [{
                "id": "sc1", "type": "generated", "description": "棱镜彩虹插画",
                "start_seconds": 0, "end_seconds": 6,
                "required_assets": [
                    {"type": "image", "description": exact, "source": "generate",
                     "prompt_profile": "default"},
                ],
            }],
            [{
                "id": "a1", "type": "image", "path": "assets/images/prism.png",
                "scene_id": "sc1", "source_tool": "image_selector", "prompt": exact,
            }],
        )
        (p / "assets" / "images").mkdir(parents=True, exist_ok=True)
        (p / "assets" / "images" / "prism.png").write_bytes(b"\x89PNG")
        return p, exact

    def test_image_scene_generation_prompt_is_exact_recorded_prompt(self, projects_root):
        p, exact = self._image_project(projects_root)
        s = load_board_state(p)
        card = next(c for c in s["storyboard"]["scenes"] if c["id"] == "sc1")
        assert card["generation_prompt"] == exact
        assert card["generation_prompt"] != card["description"]
