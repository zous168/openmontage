"""Contract tests: the Backlot web channel must stay audit-clean.

The web channel (stage_runner) is a second executor alongside the interactive
agent. Its writes must satisfy the same governance contract: approval gates
are real, decision_log mirror entries exist, runs/ and .run.lock metadata
never leaks into the artifact/audit paths.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

import lib.paths as paths_mod
import lib.checkpoint as checkpoint_mod
import lib.decision_log as decision_log_mod
import backlot.stage_runner as stage_runner_mod

from lib.checkpoint import init_project, write_checkpoint, read_checkpoint, get_next_stage
from lib.decision_log import append_decisions, suggest_next_decision_id
from lib.production_audit import audit_project
from tests.contracts.test_phase0_contracts import sample_artifact

PIPELINE = "framework-smoke"


@pytest.fixture
def projects_root(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr(paths_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(stage_runner_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(checkpoint_mod, "PROJECTS_DIR", root)
    monkeypatch.setattr(decision_log_mod, "PROJECTS_DIR", root)
    return root


@pytest.fixture
def project_dir(projects_root):
    return init_project(
        "film", title="Film", pipeline_type=PIPELINE,
        pipeline_dir=projects_root,
    )


def _complete_research(projects_root) -> None:
    """agent 通道合法完成 research（已批 + 决策一致）。"""
    write_checkpoint(
        projects_root, "film", "research", "completed",
        artifacts={"research_brief": sample_artifact("research_brief")},
        pipeline_type=PIPELINE, human_approved=True,
    )
    append_decisions("film", [{
        "decision_id": "d-001",
        "stage": "research",
        "category": "concept_selection",
        "subject": "Concept direction",
        "options_considered": [
            {
                "option_id": "c1", "label": "Concept A", "score": 0.9,
                "reason": "调研支撑最强",
            },
        ],
        "selected": "c1",
        "reason": "agent 决定",
        "user_visible": True,
        "user_approved": True,
    }])


def _agent_awaits_script(projects_root) -> None:
    """无头 agent 写完 script 留 awaiting_human + 待批决策。"""
    write_checkpoint(
        projects_root, "film", "script", "awaiting_human",
        artifacts={"script": sample_artifact("script")},
        pipeline_type=PIPELINE,
    )
    append_decisions("film", [{
        "decision_id": "d-002",
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


class TestWebChannelAuditClean:
    def test_approve_flow_audits_zero_critical(self, projects_root, project_dir):
        _complete_research(projects_root)
        _agent_awaits_script(projects_root)

        result = stage_runner_mod.approve_stage(project_dir, "script", notes="ok")
        assert result["status"] == "completed"

        findings = audit_project(project_dir)
        critical = [f for f in findings if f["severity"] == "critical"]
        assert critical == [], f"audit critical findings: {critical}"

        # 阶段顺序合法：research → script 都 completed。
        assert get_next_stage(paths_mod.PROJECTS_DIR, "film", PIPELINE) is None

    def test_reject_flow_audits_zero_critical(self, projects_root, project_dir):
        _complete_research(projects_root)
        _agent_awaits_script(projects_root)

        result = stage_runner_mod.reject_stage(
            project_dir, "script", feedback="节奏太慢，重写",
        )
        assert result["status"] == "in_progress"

        findings = audit_project(project_dir)
        critical = [f for f in findings if f["severity"] == "critical"]
        assert critical == [], f"audit critical findings: {critical}"

        # 驳回后 get_next_stage 仍指向 script（重跑同一条路）。
        assert get_next_stage(paths_mod.PROJECTS_DIR, "film", PIPELINE) == "script"

    def test_approve_without_mirror_decision_would_drift(
        self, projects_root, project_dir,
    ):
        """反向护栏：只改 checkpoint 不追加决策 = approval_gate_drift 必报。"""
        _complete_research(projects_root)
        _agent_awaits_script(projects_root)
        write_checkpoint(
            projects_root, "film", "script", "completed",
            artifacts={"script": sample_artifact("script")},
            pipeline_type=PIPELINE, human_approved=True,
        )
        findings = audit_project(project_dir)
        drift = [
            f for f in findings
            if f["code"] == "approval_gate_drift" and f["severity"] == "critical"
        ]
        assert drift, "approval_gate_drift 应该被触发（证明镜像决策是必需的）"

    def test_run_metadata_never_enters_contract_paths(
        self, projects_root, project_dir,
    ):
        """runs/ 与 .run.lock 不得被 audit / artifact 收集当成契约文件。"""
        runs = project_dir / "runs"
        runs.mkdir()
        (runs / "abc123.json").write_text(
            '{"task_id":"abc123","status":"running"}', encoding="utf-8",
        )
        (runs / "abc123.log").write_text("agent output", encoding="utf-8")
        (project_dir / ".run.lock").write_text(
            '{"task_id":"abc123","pid":0}', encoding="utf-8",
        )
        findings = audit_project(project_dir)
        # 无 checkpoint 的项目 audit 不应因 runs/ 元数据报新 finding。
        assert all(f["stage"] not in ("runs", ".run.lock") for f in findings)
