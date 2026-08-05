"""Tests for MxAI agent skill install/toggle."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.agent_skills import (
    install_mxai_skill_to_profile,
    list_agent_skills,
    list_mxai_skill_catalog,
    set_agent_skill_enabled,
)
from plugins.mxai.cfg.store import atomic_write_yaml, read_yaml


def test_list_mxai_skill_catalog_includes_sales_and_support() -> None:
    rows = {row["name"]: row for row in list_mxai_skill_catalog()}
    assert "sales-talk" in rows
    assert "support-talk" in rows
    assert rows["setup-guide"]["label"] == "首启配置引导"
    assert "FloatingChat" not in rows["setup-guide"]["description"]


def test_set_agent_skill_enabled_installs_to_profile(tmp_path: Path, monkeypatch) -> None:
    profile_dir = tmp_path / "wechat_chat"
    profile_dir.mkdir()
    atomic_write_yaml(profile_dir / "config.yaml", {"skills": {"disabled": ["sales-talk"]}})

    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_skills.get_profile_dir",
        lambda _pid: profile_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_skills.assert_prompt_agent",
        lambda _pid: None,
    )

    res = set_agent_skill_enabled("wechat_chat", "sales-talk", enabled=True)
    assert res["ok"] is True
    assert res["install_action"] in {"copied", "installed"}
    assert (profile_dir / "skills" / "mxai" / "sales-talk" / "SKILL.md").is_file()
    assert "sales-talk" not in read_yaml(profile_dir / "config.yaml")["skills"]["disabled"]

    listed = list_agent_skills("wechat_chat")
    row = next(s for s in listed["skills"] if s["name"] == "sales-talk")
    assert row["installed"] is True
    assert row["enabled"] is True


def test_set_agent_skill_enabled_disable_keeps_files(tmp_path: Path, monkeypatch) -> None:
    profile_dir = tmp_path / "qiyeweixin_chat"
    profile_dir.mkdir()
    atomic_write_yaml(profile_dir / "config.yaml", {})

    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_skills.get_profile_dir",
        lambda _pid: profile_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_skills.assert_prompt_agent",
        lambda _pid: None,
    )

    set_agent_skill_enabled("qiyeweixin_chat", "support-talk", enabled=True)
    set_agent_skill_enabled("qiyeweixin_chat", "support-talk", enabled=False)

    assert (profile_dir / "skills" / "mxai" / "support-talk" / "SKILL.md").is_file()
    disabled = read_yaml(profile_dir / "config.yaml")["skills"]["disabled"]
    assert "support-talk" in disabled

    row = next(
        s for s in list_agent_skills("qiyeweixin_chat")["skills"] if s["name"] == "support-talk"
    )
    assert row["installed"] is True
    assert row["enabled"] is False


def test_install_mxai_skill_to_profile_idempotent(tmp_path: Path) -> None:
    profile_dir = tmp_path / "p"
    profile_dir.mkdir()
    assert install_mxai_skill_to_profile(profile_dir, "sales-talk") == "copied"
    assert install_mxai_skill_to_profile(profile_dir, "sales-talk") == "installed"
