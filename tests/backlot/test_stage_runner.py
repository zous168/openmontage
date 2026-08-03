"""Stage-runner tests — headless-agent stage channel for Backlot.

Covers: run preparation / lock, fake-agent lifecycle (awaiting_human /
completed / failed), page approve / reject (incl. revision cap), cancel,
prompt assembly, CLI resolution, and the HTTP endpoints.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import lib.paths as paths_mod
import lib.checkpoint as checkpoint_mod
import lib.decision_log as decision_log_mod
import backlot.stage_runner as stage_runner_mod
import backlot.state as state_mod
import backlot.server as server_mod

from lib.checkpoint import init_project, write_checkpoint, read_checkpoint, get_next_stage
from lib.decision_log import append_decisions, load_decision_log, suggest_next_decision_id
from tests.contracts.test_phase0_contracts import sample_artifact

PIPELINE = "framework-smoke"


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    # lib.paths 是唯一来源；所有模块 import 时绑定，逐个替换。
    monkeypatch.setattr(paths_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(stage_runner_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(checkpoint_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(decision_log_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(server_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(server_mod, "_summary_cache", {})
    monkeypatch.setattr(
        server_mod, "_PROJECTS_ROOT_STR",
        os.path.normcase(str(root.resolve())),
    )
    monkeypatch.setattr(server_mod, "THUMB_CACHE_DIR", tmp_path / "thumbs")
    return root


@pytest.fixture
def client(projects_root, monkeypatch):
    async def no_watch():
        return None

    monkeypatch.setattr(server_mod, "_watch_projects", no_watch)
    with TestClient(server_mod.create_app()) as c:
        yield c


@pytest.fixture
def project_dir(projects_root):
    return init_project(
        "film", title="Film", pipeline_type=PIPELINE,
        pipeline_dir=projects_root,
    )


class FakeProc:
    """鸭子类型 asyncio.subprocess.Process（pid=0 保证永不误杀真实进程）。"""

    def __init__(self, behavior=None, exit_code: int = 0):
        self.pid = 0
        self.returncode = exit_code
        self._behavior = behavior

    async def communicate(self, input: bytes | None = None):
        if self._behavior:
            await self._behavior(input)
        return (b"", b"")


def install_fake_agent(monkeypatch, behavior=None, exit_code: int = 0) -> FakeProc:
    proc = FakeProc(behavior=behavior, exit_code=exit_code)

    async def fake_spawn(cmd, *, cwd, stdout, stderr):
        return proc

    monkeypatch.setattr(stage_runner_mod, "_spawn_agent", fake_spawn)
    monkeypatch.setattr(stage_runner_mod, "_resolve_claude_cmd", lambda: ["claude"])
    return proc


def agent_writes_awaiting(project_id: str, stage: str, artifact_name: str):
    """fake agent 行为：in_progress → 带 artifact 的 awaiting_human + 待批决策。"""

    async def behavior(_input):
        write_checkpoint(
            paths_mod.PROJECTS_DIR, project_id, stage,
            "in_progress", artifacts={}, pipeline_type=PIPELINE,
        )
        write_checkpoint(
            paths_mod.PROJECTS_DIR, project_id, stage,
            "awaiting_human",
            artifacts={artifact_name: sample_artifact(artifact_name)},
            pipeline_type=PIPELINE,
        )
        append_decisions(project_id, [{
            "decision_id": suggest_next_decision_id(projects_root_for(project_id), prefix="d"),
            "stage": stage,
            "category": "provider_selection",
            "subject": "Narration TTS provider",
            "options_considered": [
                {
                    "option_id": "piper", "label": "Piper", "score": 0.9,
                    "reason": "本地免费",
                },
            ],
            "selected": "piper",
            "reason": "agent 决定",
            "user_visible": True,
            "user_approved": False,
        }])

    return behavior


def projects_root_for(project_id: str) -> Path:
    return paths_mod.PROJECTS_DIR / project_id


class TestPrepareStageRun:
    def test_prepare_creates_task_and_lock(self, projects_root, project_dir):
        task = stage_runner_mod.prepare_stage_run(project_dir)
        assert task.stage == "research"
        lock = json.loads((project_dir / ".run.lock").read_text(encoding="utf-8"))
        assert lock["task_id"] == task.task_id
        assert lock["runner"] == "web"
        assert stage_runner_mod._TASKS["film"].task_id == task.task_id

    def test_second_run_raises_busy(self, projects_root, project_dir):
        stage_runner_mod.prepare_stage_run(project_dir)
        with pytest.raises(stage_runner_mod.StageBusyError):
            stage_runner_mod.prepare_stage_run(project_dir)

    def test_non_next_stage_rejected(self, project_dir):
        with pytest.raises(stage_runner_mod.StageRunError) as exc:
            stage_runner_mod.prepare_stage_run(project_dir, stage="script")
        assert "只能运行" in str(exc.value)

    def test_stale_lock_taken_over(self, projects_root, project_dir):
        task = stage_runner_mod.prepare_stage_run(project_dir)
        stage_runner_mod._release_lock(project_dir, task.task_id)
        # 无锁时再次 prepare 直接成功。
        task2 = stage_runner_mod.prepare_stage_run(project_dir)
        assert task2.task_id != task.task_id


class TestRunTask:
    def test_run_task_success_awaiting_human(self, projects_root, project_dir, monkeypatch):
        install_fake_agent(
            monkeypatch,
            behavior=agent_writes_awaiting("film", "research", "research_brief"),
        )
        task = stage_runner_mod.prepare_stage_run(project_dir)
        asyncio.run(stage_runner_mod.run_task(task))

        assert task.status == "succeeded"
        assert not (project_dir / ".run.lock").exists()
        state = json.loads(
            (project_dir / "runs" / f"{task.task_id}.json").read_text(encoding="utf-8")
        )
        assert state["status"] == "succeeded"

        cp = read_checkpoint(projects_root, "film", "research")
        assert cp["status"] == "awaiting_human"
        assert not cp["human_approved"]
        log = load_decision_log(project_dir)
        latest = log["decisions"][-1]
        assert latest["user_approved"] is False

    def test_run_task_exit_failure(self, projects_root, project_dir, monkeypatch):
        install_fake_agent(monkeypatch, exit_code=1)
        task = stage_runner_mod.prepare_stage_run(project_dir)
        asyncio.run(stage_runner_mod.run_task(task))
        assert task.status == "failed"
        assert "退出码 1" in (task.error or "")

    def test_run_task_cancel_patches_stuck_in_progress(
        self, projects_root, project_dir, monkeypatch,
    ):
        install_fake_agent(monkeypatch)
        task = stage_runner_mod.prepare_stage_run(project_dir)
        # agent 已写 in_progress 但被用户取消。
        write_checkpoint(
            projects_root, "film", "research", "in_progress",
            artifacts={}, pipeline_type=PIPELINE,
        )
        stage_runner_mod.cancel_run(project_dir, task.task_id)
        assert task.status == "aborted"
        cp = read_checkpoint(projects_root, "film", "research")
        assert cp["status"] == "failed"
        assert not (project_dir / ".run.lock").exists()


class TestApproveReject:
    def _awaiting_proposal(self, project_dir, projects_root) -> None:
        write_checkpoint(
            projects_root, "film", "research", "completed",
            artifacts={"research_brief": sample_artifact("research_brief")},
            pipeline_type=PIPELINE, human_approved=True,
        )
        write_checkpoint(
            projects_root, "film", "script", "awaiting_human",
            artifacts={"script": sample_artifact("script")},
            pipeline_type=PIPELINE,
        )
        append_decisions("film", [{
            "decision_id": "d-001",
            "stage": "script",
            "category": "playbook_selection",
            "subject": "Style playbook",
            "options_considered": [
                {
                    "option_id": "clean-professional", "label": "干净专业", "score": 0.9,
                    "reason": "企业科普",
                },
            ],
            "selected": "clean-professional",
            "reason": "agent 决定",
            "user_visible": True,
            "user_approved": False,
        }])

    def test_approve_mirrors_decision_and_advances(
        self, projects_root, project_dir,
    ):
        self._awaiting_proposal(project_dir, projects_root)
        result = stage_runner_mod.approve_stage(project_dir, "script", notes="ok")
        assert result["status"] == "completed"
        assert result["next_stage"] is None  # framework-smoke 只有两阶段

        cp = read_checkpoint(projects_root, "film", "script")
        assert cp["status"] == "completed"
        assert cp["human_approved"] is True
        assert cp["metadata"]["approved_via"] == "backlot-web"
        assert cp["artifacts"]["script"]["title"] == "Test Script"

        log = load_decision_log(project_dir)
        latest = log["decisions"][-1]
        assert latest["category"] == "playbook_selection"
        assert latest["subject"] == "Style playbook"
        assert latest["user_approved"] is True

    def test_approve_no_pending_decision_adds_human_approval_entry(
        self, projects_root, project_dir,
    ):
        write_checkpoint(
            projects_root, "film", "research", "completed",
            artifacts={"research_brief": sample_artifact("research_brief")},
            pipeline_type=PIPELINE, human_approved=True,
        )
        write_checkpoint(
            projects_root, "film", "script", "awaiting_human",
            artifacts={"script": sample_artifact("script")},
            pipeline_type=PIPELINE,
        )
        result = stage_runner_mod.approve_stage(project_dir, "script")
        assert result["status"] == "completed"
        log = load_decision_log(project_dir)
        assert log["decisions"][-1]["category"] == "human_approval"

    def test_approve_not_awaiting_rejected(self, project_dir):
        with pytest.raises(stage_runner_mod.StageRunError) as exc:
            stage_runner_mod.approve_stage(project_dir, "research")
        assert "不在等待批准状态" in str(exc.value)

    def test_reject_keeps_artifacts_and_records_feedback(
        self, projects_root, project_dir,
    ):
        self._awaiting_proposal(project_dir, projects_root)
        result = stage_runner_mod.reject_stage(project_dir, "script", feedback="节奏太慢，压缩到 30 秒")
        assert result["status"] == "in_progress"
        assert result["revision_count"] == 1

        cp = read_checkpoint(projects_root, "film", "script")
        assert cp["status"] == "in_progress"
        assert cp["metadata"]["revision_request"] == "节奏太慢，压缩到 30 秒"
        assert cp["artifacts"]["script"]["title"] == "Test Script"  # 产物保留

        log = load_decision_log(project_dir)
        assert log["decisions"][-1]["category"] == "human_rejection"
        assert log["decisions"][-1]["reason"] == "节奏太慢，压缩到 30 秒"

    def test_reject_revision_cap(self, projects_root, project_dir):
        for i in range(3):
            write_checkpoint(
                projects_root, "film", "script", "awaiting_human",
                artifacts={"script": sample_artifact("script")},
                pipeline_type=PIPELINE,
            )
            stage_runner_mod.reject_stage(project_dir, "script", feedback=f"第 {i + 1} 次驳回")
        # 第四次驳回前重写 awaiting_human（reject 会把阶段置回 in_progress）。
        write_checkpoint(
            projects_root, "film", "script", "awaiting_human",
            artifacts={"script": sample_artifact("script")},
            pipeline_type=PIPELINE,
        )
        with pytest.raises(stage_runner_mod.RevisionLimitError) as exc:
            stage_runner_mod.reject_stage(project_dir, "script", feedback="超限")
        assert "上限" in str(exc.value)


class TestPrompt:
    def test_prompt_contains_skill_feedback_and_gate_instruction(
        self, projects_root, project_dir,
    ):
        from lib.pipeline_loader import load_pipeline_readonly

        manifest = load_pipeline_readonly(PIPELINE)
        prompt = stage_runner_mod.build_stage_prompt(
            project_dir, "research",
            manifest=manifest,
            wall_time_minutes=10, budget_usd=1.0,
            feedback="请更激进",
        )
        assert "skills/pipelines" in prompt or "技能全文开始" in prompt
        assert "请更激进" in prompt
        assert "awaiting_human" in prompt
        assert "research" in prompt
        assert "END YOUR TURN" in prompt or "停止" in prompt


class TestCliResolution:
    def test_which_rejects_extensionless_on_windows(self, monkeypatch):
        if os.name != "nt":
            pytest.skip("Windows-specific")
        import shutil

        def fake_which(name):
            return {
                "claude": r"C:\Users\test\npm\claude",  # sh 脚本——必须排除
                "claude.cmd": r"C:\Users\test\npm\claude.cmd",
            }.get(name)

        monkeypatch.setattr(shutil, "which", fake_which)
        assert stage_runner_mod._which("claude") is None
        assert stage_runner_mod._which("claude.cmd") == r"C:\Users\test\npm\claude.cmd"

    def test_child_env_drops_host_session_vars(self):
        env = stage_runner_mod._child_env({
            "CLAUDE_CODE_ENTRYPOINT": "claude-desktop",
            "CLAUDECODE": "1",
            "CLAUDE_CODE_SESSION_ID": "abc",
            "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH": "1",
            "ANTHROPIC_AUTH_TOKEN": "keep-me",
            "ANTHROPIC_BASE_URL": "https://example.invalid",
            "PATH": "/usr/bin",
        })
        # 宿主会话变量必须剥离——否则子进程走宿主托管 OAuth 凭据 → 401。
        assert "CLAUDE_CODE_ENTRYPOINT" not in env
        assert "CLAUDECODE" not in env
        assert "CLAUDE_CODE_SESSION_ID" not in env
        assert "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH" not in env
        # 机器级 provider 配置必须保留。
        assert env["ANTHROPIC_AUTH_TOKEN"] == "keep-me"
        assert env["ANTHROPIC_BASE_URL"] == "https://example.invalid"
        assert env["PATH"] == "/usr/bin"

    def test_child_env_does_not_mutate_source(self):
        src = {"CLAUDE_CODE_ENTRYPOINT": "claude-desktop", "PATH": "/usr/bin"}
        stage_runner_mod._child_env(src)
        assert src["CLAUDE_CODE_ENTRYPOINT"] == "claude-desktop"

    def test_resolve_claude_cmd_returns_list(self):
        try:
            cmd = stage_runner_mod._resolve_claude_cmd()
        except stage_runner_mod.StageRunError:
            pytest.skip("claude CLI 未安装")
        assert isinstance(cmd, list) and cmd
        assert " " not in cmd[0]  # 无参数注入


class TestHttpEndpoints:
    def test_stage_run_endpoint_202_and_state_runs(
        self, client, projects_root, project_dir, monkeypatch,
    ):
        install_fake_agent(
            monkeypatch,
            behavior=agent_writes_awaiting("film", "research", "research_brief"),
        )
        res = client.post("/api/project/film/stage/run", json={})
        assert res.status_code == 202
        body = res.json()
        assert body["task_id"]
        assert body["stage"] == "research"

        state = client.get("/api/project/film/state").json()
        assert state["runs"]
        assert state["runs"][0]["status"] in ("queued", "running", "succeeded")

    def test_stage_run_busy_409(self, client, project_dir, monkeypatch):
        async def hang(_input):
            await asyncio.sleep(60)

        install_fake_agent(monkeypatch, behavior=hang)
        first = client.post("/api/project/film/stage/run", json={})
        assert first.status_code == 202
        # fake agent 挂起 → 锁未释放 → 第二次 run 必须 409。
        res = client.post("/api/project/film/stage/run", json={})
        assert res.status_code == 409
        # 清理：取消挂起任务（cancel 只杀进程 + 标状态，挂起的 communicate 随之释放）。
        client.post(
            f"/api/project/film/stage/run/{first.json()['task_id']}/cancel", json={}
        )

    def test_stage_run_stage_order_400(self, client, project_dir, monkeypatch):
        install_fake_agent(monkeypatch)
        res = client.post("/api/project/film/stage/run", json={"stage": "script"})
        assert res.status_code == 400
        assert "只能运行" in res.json()["detail"]

    def test_stage_run_unknown_project_404(self, client, projects_root):
        res = client.post("/api/project/nope/stage/run", json={})
        assert res.status_code == 404

    def test_approve_endpoint(self, client, projects_root, project_dir, monkeypatch):
        install_fake_agent(monkeypatch)
        write_checkpoint(
            projects_root, "film", "research", "completed",
            artifacts={"research_brief": sample_artifact("research_brief")},
            pipeline_type=PIPELINE, human_approved=True,
        )
        write_checkpoint(
            projects_root, "film", "script", "awaiting_human",
            artifacts={"script": sample_artifact("script")},
            pipeline_type=PIPELINE,
        )
        res = client.post("/api/project/film/stage/approve", json={"stage": "script"})
        assert res.status_code == 200
        assert res.json()["status"] == "completed"
        cp = read_checkpoint(projects_root, "film", "script")
        assert cp["human_approved"] is True

    def test_reject_endpoint_requires_feedback(self, client, project_dir):
        write_checkpoint(
            paths_mod.PROJECTS_DIR, "film", "script", "awaiting_human",
            artifacts={"script": sample_artifact("script")},
            pipeline_type=PIPELINE,
        )
        res = client.post("/api/project/film/stage/reject", json={"stage": "script", "feedback": "x"})
        assert res.status_code == 422  # min_length=5

    def test_log_endpoint(self, client, projects_root, project_dir, monkeypatch):
        install_fake_agent(monkeypatch)
        res = client.post("/api/project/film/stage/run", json={})
        task_id = res.json()["task_id"]
        log = client.get(f"/api/project/film/stage/run/{task_id}/log")
        assert log.status_code == 200
        assert "total" in log.json()
