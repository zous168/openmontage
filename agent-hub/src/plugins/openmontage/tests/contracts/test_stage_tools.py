"""无头 stage_tools（openmontage_stage）契约。"""

from __future__ import annotations

import json

import pytest

from plugins.openmontage.lib.checkpoint import init_project, read_checkpoint
from plugins.openmontage.stage_tools import (
    TOOLSET,
    handle_artifact_read,
    handle_artifact_write,
    handle_checkpoint,
    handle_registry,
)


@pytest.fixture
def headless_env(monkeypatch, tmp_path):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setattr("plugins.openmontage.lib.paths.PROJECTS_DIR", root)
    init_project(
        "stage-tools-01",
        title="Stage Tools",
        pipeline_type="framework-smoke",
        pipeline_dir=root,
    )
    monkeypatch.setenv("OPENMONTAGE_HEADLESS_STAGE", "1")
    monkeypatch.setenv("OPENMONTAGE_HEADLESS_PROJECT", "stage-tools-01")
    monkeypatch.setenv("OPENMONTAGE_HEADLESS_STAGE_NAME", "research")
    return root


def _payload(raw: str) -> dict:
    return json.loads(raw)


def test_toolset_name_is_stage_not_orchestrator():
    from plugins.openmontage.bridge import TOOLSET as OM

    assert TOOLSET == "openmontage_stage"
    assert TOOLSET != OM


def test_checkpoint_and_artifact_roundtrip(headless_env):
    root = headless_env

    cp = _payload(handle_checkpoint({
        "status": "in_progress",
        "artifacts": {},
        "label": "写进行中",
    }))
    assert cp["ok"] is True
    assert cp["status"] == "in_progress"
    stored = read_checkpoint(root, "stage-tools-01", "research")
    assert stored and stored.get("status") == "in_progress"

    written = _payload(handle_artifact_write({
        "path": "scratch/note.txt",
        "content": "hello",
        "label": "写草稿",
    }))
    assert written["ok"] is True
    assert (root / "stage-tools-01" / "scratch" / "note.txt").read_text(
        encoding="utf-8"
    ) == "hello"

    read_back = _payload(handle_artifact_read({
        "path": "scratch/note.txt",
        "label": "读草稿",
    }))
    assert read_back["ok"] is True
    assert read_back["content"] == "hello"

    denied = _payload(handle_artifact_write({
        "path": "artifacts/decision_log.json",
        "content": "{}",
        "label": "偷写决策",
    }))
    assert denied["ok"] is False

    escape = _payload(handle_artifact_read({
        "path": "../secrets.txt",
        "label": "逃逸",
    }))
    assert escape["ok"] is False


def test_artifact_read_blocks_checkpoint(headless_env):
    blocked = _payload(handle_artifact_read({
        "path": "checkpoint_research.json",
        "label": "读检查点",
    }))
    assert blocked["ok"] is False


def test_project_id_mismatch(headless_env):
    bad = _payload(handle_checkpoint({
        "project_id": "other-project",
        "status": "failed",
        "error": "x",
        "label": "错项目",
    }))
    assert bad["ok"] is False
    assert "不一致" in bad.get("error", "")


def test_registry_allowlist_blocks_unlisted_tool(headless_env, monkeypatch):
    monkeypatch.setattr(
        "plugins.openmontage.stage_tools._stage_tools_available",
        lambda _pid, _stage: ["tts_selector"],
    )
    blocked = _payload(handle_registry({
        "action": "execute",
        "tool": "video_compose",
        "params": {},
        "label": "越权合成",
    }))
    assert blocked["ok"] is False
    assert "tools_available" in json.dumps(blocked, ensure_ascii=False)


def test_headless_governance_blocks_terminal(monkeypatch):
    from plugins.openmontage.governance import pre_tool_call

    monkeypatch.setenv("OPENMONTAGE_HEADLESS_STAGE", "1")
    verdict = pre_tool_call("terminal", {"command": "ls", "label": "列目录"})
    assert verdict and verdict.get("action") == "block"
    assert "om_registry" in verdict.get("message", "")

    verdict2 = pre_tool_call("execute_code", {"code": "print(1)", "label": "跑代码"})
    assert verdict2 and verdict2.get("action") == "block"


def test_registers_stage_tools():
    from plugins.openmontage.tests.contracts.test_hermes_plugin_contract import (
        _RecordingCtx,
    )
    import plugins.openmontage as om

    ctx = _RecordingCtx()
    om.register(ctx)
    for name in (
        "om_registry",
        "om_checkpoint",
        "om_artifact_read",
        "om_artifact_write",
        "om_decision_append",
    ):
        assert name in ctx.tools


def test_prompt_uses_stage_tools_not_python_c(projects_root=None):
    from plugins.openmontage.backlot import stage_runner
    from plugins.openmontage.lib.pipeline_loader import load_pipeline_readonly
    from plugins.openmontage.lib.checkpoint import init_project
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        project_dir = init_project(
            "p1", title="P", pipeline_type="framework-smoke", pipeline_dir=root,
        )
        # build_stage_prompt uses global PROJECTS_DIR for status; missing project ok
        manifest = load_pipeline_readonly("framework-smoke")
        prompt = stage_runner.build_stage_prompt(
            project_dir,
            "research",
            manifest=manifest,
            wall_time_minutes=5,
            budget_usd=1.0,
        )
        assert "om_registry" in prompt
        assert "om_checkpoint" in prompt
        assert "Hermes 工具面" in prompt
        assert "禁止 terminal" in prompt
        assert "registry.execute" not in prompt
        assert "{om_python}" not in prompt
