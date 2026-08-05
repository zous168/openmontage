"""agent.hermes_help_guidance — system prompt gating + mxai profile bootstrap."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from agent.prompt_builder import (
    HERMES_AGENT_HELP_GUIDANCE,
    MEMORY_GUIDANCE,
    STEER_CHANNEL_NOTE,
    TASK_COMPLETION_GUIDANCE,
)
from agent.system_prompt import build_system_prompt_parts
from plugins.mxai.cfg.agent_bindings import BUSINESS_AGENT_IDS
from plugins.mxai.cfg.bootstrap.assistant_profile import (
    ensure_assistant_hermes_help_guidance,
    ensure_business_hermes_help_guidance,
)
from plugins.mxai.cfg.migrations.m0008_hermes_help_guidance import MIGRATION


def _minimal_agent(*, hermes_help_guidance: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        load_soul_identity=False,
        skip_context_files=True,
        valid_tool_names={"memory", "skill_manage", "skills_list", "skill_view"},
        model="gpt-4o",
        provider="openai",
        platform="api_server",
        _task_completion_guidance=True,
        _tool_use_enforcement="auto",
        _hermes_help_guidance=hermes_help_guidance,
        _kanban_worker_guidance=None,
        _memory_store=None,
        _memory_enabled=False,
        _user_profile_enabled=False,
        _memory_manager=None,
        pass_session_id=False,
        session_id=None,
        _environment_probe=False,
    )


def test_system_prompt_omits_hermes_help_when_disabled() -> None:
    agent = _minimal_agent(hermes_help_guidance=False)
    agent.load_soul_identity = True
    with patch("run_agent.load_soul_md", return_value="channel-soul-marker"):
        with patch(
            "run_agent.build_skills_system_prompt",
            return_value="## Skills\n<available_skills>\n  mxai:\n    - sales-talk: sales\n</available_skills>",
        ) as mock_skills:
            parts = build_system_prompt_parts(agent)
    stable = parts["stable"]
    assert HERMES_AGENT_HELP_GUIDANCE not in stable
    assert TASK_COMPLETION_GUIDANCE not in stable
    assert MEMORY_GUIDANCE not in stable
    assert STEER_CHANNEL_NOTE not in stable
    assert "Skills (mandatory)" not in stable
    assert "<available_skills>" in stable
    assert "sales-talk" in stable
    assert "Active Hermes profile" not in stable
    assert "channel-soul-marker" in stable
    mock_skills.assert_called_once()
    assert mock_skills.call_args.kwargs.get("lean") is True


def test_system_prompt_full_framework_uses_non_lean_skills_index() -> None:
    with patch("run_agent.load_soul_md", return_value=None):
        with patch("run_agent.build_skills_system_prompt", return_value="") as mock_skills:
            build_system_prompt_parts(_minimal_agent(hermes_help_guidance=True))
    mock_skills.assert_called_once()
    assert mock_skills.call_args.kwargs.get("lean") is False


def test_system_prompt_includes_framework_blocks_when_enabled() -> None:
    with patch("run_agent.load_soul_md", return_value=None):
        with patch("run_agent.build_skills_system_prompt", return_value=""):
            parts = build_system_prompt_parts(_minimal_agent(hermes_help_guidance=True))
    stable = parts["stable"]
    assert HERMES_AGENT_HELP_GUIDANCE in stable
    assert TASK_COMPLETION_GUIDANCE in stable
    assert MEMORY_GUIDANCE in stable
    assert STEER_CHANNEL_NOTE in stable


def test_business_profile_sets_hermes_help_false(tmp_path: Path) -> None:
    profile_dir = tmp_path / "wechat_chat"
    profile_dir.mkdir()
    cfg_path = profile_dir / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"agent": {"task_completion_guidance": True}}, sort_keys=False),
        encoding="utf-8",
    )
    assert ensure_business_hermes_help_guidance(profile_dir) == "hermes_help_off"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert data["agent"]["hermes_help_guidance"] is False
    assert ensure_business_hermes_help_guidance(profile_dir) == "skipped"


def test_assistant_profile_sets_hermes_help_true(tmp_path: Path) -> None:
    profile_dir = tmp_path / "assistant"
    profile_dir.mkdir()
    cfg_path = profile_dir / "config.yaml"
    cfg_path.write_text(
        yaml.safe_dump({"agent": {"hermes_help_guidance": False}}, sort_keys=False),
        encoding="utf-8",
    )
    assert ensure_assistant_hermes_help_guidance(profile_dir) == "hermes_help_on"
    data = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    assert data["agent"]["hermes_help_guidance"] is True


def test_m0008_patches_business_profiles_false_assistant_true(
    tmp_path: Path, monkeypatch
) -> None:
    profiles_root = tmp_path / "profiles"
    profiles_root.mkdir()
    assistant_dir = profiles_root / "assistant"
    assistant_dir.mkdir()
    (assistant_dir / "config.yaml").write_text(
        yaml.safe_dump({"agent": {}}, sort_keys=False),
        encoding="utf-8",
    )
    biz_dir = profiles_root / "qiyeweixin_chat"
    biz_dir.mkdir()
    (biz_dir / "config.yaml").write_text(
        yaml.safe_dump({"agent": {}}, sort_keys=False),
        encoding="utf-8",
    )

    def _fake_get_profile_dir(name: str) -> Path:
        if name == "default":
            return tmp_path
        return profiles_root / name

    monkeypatch.setattr(
        "plugins.mxai.cfg.migrations.m0008_hermes_help_guidance.get_profile_dir",
        _fake_get_profile_dir,
    )
    changed = MIGRATION.apply(tmp_path)
    assert changed >= 2
    assert yaml.safe_load((assistant_dir / "config.yaml").read_text())["agent"][
        "hermes_help_guidance"
    ] is True
    assert yaml.safe_load((biz_dir / "config.yaml").read_text())["agent"][
        "hermes_help_guidance"
    ] is False


def test_all_business_agent_ids_covered_in_migration() -> None:
    """迁移与 bootstrap 共用 BUSINESS_AGENT_IDS，避免漏 profile."""
    assert len(BUSINESS_AGENT_IDS) >= 10
