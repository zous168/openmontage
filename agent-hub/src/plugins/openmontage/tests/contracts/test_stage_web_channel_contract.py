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

import plugins.openmontage.lib.paths as paths_mod
import plugins.openmontage.lib.checkpoint as checkpoint_mod
import plugins.openmontage.lib.decision_log as decision_log_mod
import plugins.openmontage.backlot.stage_runner as stage_runner_mod

from plugins.openmontage.lib.checkpoint import init_project, write_checkpoint, read_checkpoint, get_next_stage
from plugins.openmontage.lib.decision_log import append_decisions, suggest_next_decision_id
from plugins.openmontage.lib.production_audit import audit_project
from plugins.openmontage.tests.contracts.test_phase0_contracts import sample_artifact

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


class TestRejectedCheckpointLeavesNoDecisions:
    """被拒的 write_checkpoint 不得留下已落盘的决策。

    曾经 ``_merge_decision_log`` 排在 ``validate_checkpoint`` 之前：一次因
    schema 不合法而失败的写入，checkpoint 文件没写，decision_log.json 却已
    经收下了那些条目。日志是 append-only 且按 decision_id 去重，于是非法
    category（agent 确实会自造）永久滞留，且因 category 非法而永远无法在
    批准时被镜像 —— gated 阶段就此埋下永久 approval_gate_drift。
    """

    def test_invalid_embedded_decision_is_not_persisted(
        self, projects_root, project_dir,
    ):
        from plugins.openmontage.lib.checkpoint import CheckpointValidationError
        from plugins.openmontage.lib.decision_log import load_decision_log

        bad = {
            "version": "1.0",
            "project_id": "film",
            "decisions": [{
                "decision_id": "d-bogus",
                "stage": "research",
                "category": "agent_invented_category",  # 不在 schema 枚举里
                "subject": "自造类别",
                "options_considered": [
                    {"option_id": "a", "label": "A", "score": 1, "reason": "x"},
                ],
                "selected": "a",
                "reason": "agent 自造",
                "user_visible": True,
                "user_approved": False,
            }],
        }
        with pytest.raises(CheckpointValidationError):
            write_checkpoint(
                projects_root, "film", "research", "awaiting_human",
                artifacts={
                    "research_brief": sample_artifact("research_brief"),
                    "decision_log": bad,
                },
                pipeline_type=PIPELINE,
            )

        ids = {d["decision_id"] for d in load_decision_log(project_dir).get("decisions", [])}
        assert "d-bogus" not in ids, "被拒的写入把非法决策留在了 decision_log.json"
        assert not (project_dir / "checkpoint_research.json").exists()

    def test_valid_embedded_decision_still_merges(self, projects_root, project_dir):
        from plugins.openmontage.lib.decision_log import load_decision_log

        good = {
            "version": "1.0",
            "project_id": "film",
            "decisions": [{
                "decision_id": "d-ok",
                "stage": "research",
                "category": "concept_selection",
                "subject": "Concept direction",
                "options_considered": [
                    {"option_id": "c1", "label": "C1", "score": 1, "reason": "x"},
                ],
                "selected": "c1",
                "reason": "agent 决定",
                "user_visible": True,
                "user_approved": False,
            }],
        }
        write_checkpoint(
            projects_root, "film", "research", "awaiting_human",
            artifacts={
                "research_brief": sample_artifact("research_brief"),
                "decision_log": good,
            },
            pipeline_type=PIPELINE,
        )
        ids = {d["decision_id"] for d in load_decision_log(project_dir).get("decisions", [])}
        assert "d-ok" in ids


class TestStageSkillResolution:
    """无头 agent 的 prompt 承诺「导演技能全文已粘贴」——必须真的贴上。

    manifest 存的是裸标识符（``pipelines/explainer/compose-director``），
    既无 ``skills/`` 根也无 ``.md`` 后缀。曾经直接把该字段当路径用，
    ``is_file()`` 恒为假，于是每个阶段都贴了个空块，agent 只能自己
    Grep/Read 去翻技能，白烧若干轮。
    """

    def test_every_declared_stage_skill_resolves_to_a_real_file(self):
        import contextlib
        import io

        from plugins.openmontage.lib.paths import CODE_ROOT, PIPELINE_DEFS_DIR
        from plugins.openmontage.lib.pipeline_loader import load_pipeline_readonly, resolve_stage_skill_file

        missing: list[str] = []
        checked = 0
        for manifest_path in sorted(PIPELINE_DEFS_DIR.glob("*.yaml")):
            try:
                with contextlib.redirect_stderr(io.StringIO()):
                    manifest = load_pipeline_readonly(manifest_path.stem)
            except Exception:
                continue  # manifest 自身 schema 不合法——由别的契约测试负责
            for stage in manifest.get("stages") or []:
                resolved = resolve_stage_skill_file(manifest, stage["name"])
                if resolved is None:
                    continue
                checked += 1
                if not (CODE_ROOT / resolved).is_file():
                    missing.append(f"{manifest_path.stem}/{stage['name']} -> {resolved}")
        assert checked > 0, "没有任何阶段声明了 skill——解析器可能坏了"
        assert missing == [], f"技能文件解析不到: {missing}"

    @pytest.mark.parametrize("declared", [
        "pipelines/explainer/compose-director",       # manifest 里的裸写法
        "skills/pipelines/explainer/compose-director",  # 已带前缀
        "pipelines/explainer/compose-director.md",    # 已带后缀
        "skills/pipelines/explainer/compose-director.md",
        "pipelines\\explainer\\compose-director",     # Windows 反斜杠
    ])
    def test_resolve_normalizes_prefix_suffix_and_separators(self, declared):
        from plugins.openmontage.lib.pipeline_loader import resolve_stage_skill_file

        manifest = {"stages": [{"name": "compose", "skill": declared}]}
        assert resolve_stage_skill_file(manifest, "compose") == (
            "skills/pipelines/explainer/compose-director.md"
        )

    def test_resolve_returns_none_when_stage_declares_no_skill(self):
        from plugins.openmontage.lib.pipeline_loader import resolve_stage_skill_file

        manifest = {"stages": [{"name": "research"}]}
        assert resolve_stage_skill_file(manifest, "research") is None
        assert resolve_stage_skill_file(manifest, "nope") is None

    def test_prompt_actually_embeds_the_skill_body(self):
        """端到端：prompt 里必须出现技能正文，而不只是标题壳子。"""
        from plugins.openmontage.lib.paths import CODE_ROOT
        from plugins.openmontage.lib.pipeline_loader import load_pipeline_readonly, resolve_stage_skill_file

        manifest = load_pipeline_readonly("reference-driven")
        skill_rel = resolve_stage_skill_file(manifest, "compose")
        body = (CODE_ROOT / skill_rel).read_text(encoding="utf-8")
        probe = body.strip().splitlines()[0]  # 技能正文首行

        prompt = stage_runner_mod.build_stage_prompt(
            Path(paths_mod.PROJECTS_DIR) / "nonexistent-project",
            "compose",
            manifest=manifest,
            wall_time_minutes=25,
            budget_usd=10.0,
        )
        assert skill_rel in prompt
        assert probe in prompt, "prompt 声称贴了技能全文，实际没有"
        assert len(prompt) > len(body), "prompt 应当包含整份技能"


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
