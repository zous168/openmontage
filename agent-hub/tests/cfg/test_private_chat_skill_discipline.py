"""微信/企微：纪律要求自行 skill_view + 默认启用 sales/support."""

from __future__ import annotations

from pathlib import Path

from plugins.mxai.cfg.agent_skills import ensure_profile_default_skills, list_agent_skills
from plugins.mxai.cfg.prompt_config import patch_private_chat_instructions_skill_rule
from plugins.mxai.cfg.store import atomic_write_yaml


def test_patch_private_chat_instructions_skill_rule(tmp_path: Path) -> None:
    instr = tmp_path / "INSTRUCTIONS.md"
    instr.write_text(
        "## 铁律\n\n1. 不得编造。\n\n## 回复规范\n\n- 短句\n",
        encoding="utf-8",
    )
    assert patch_private_chat_instructions_skill_rule(tmp_path, "wechat_chat") == "patched"
    text = instr.read_text(encoding="utf-8")
    assert "**强制阅读技能**" in text
    assert "skill_view" in text
    assert "sales-talk" in text
    assert "support-talk" in text
    assert "## 回复规范" in text
    assert patch_private_chat_instructions_skill_rule(tmp_path, "wechat_chat") == "skipped"


def test_patch_skips_non_chat_profiles(tmp_path: Path) -> None:
    (tmp_path / "INSTRUCTIONS.md").write_text("## 铁律\n", encoding="utf-8")
    assert patch_private_chat_instructions_skill_rule(tmp_path, "douyin_dm") == "skipped"


def test_ensure_profile_default_skills(tmp_path: Path, monkeypatch) -> None:
    profile_dir = tmp_path / "wechat_chat"
    profile_dir.mkdir()
    atomic_write_yaml(profile_dir / "config.yaml", {"skills": {"disabled": []}})

    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_skills.get_profile_dir",
        lambda _pid: profile_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_skills.assert_prompt_agent",
        lambda _pid: None,
    )

    assert ensure_profile_default_skills(profile_dir, "wechat_chat") == "skills_enabled"
    listed = list_agent_skills("wechat_chat")
    by_name = {s["name"]: s for s in listed["skills"]}
    assert by_name["sales-talk"]["enabled"] is True
    assert by_name["support-talk"]["enabled"] is True
    assert ensure_profile_default_skills(profile_dir, "wechat_chat") == "skipped"
    assert ensure_profile_default_skills(profile_dir, "douyin_dm") == "skipped"


def test_templates_include_skill_iron_rule() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "templates"
    for pid in ("wechat_chat", "qiyeweixin_chat"):
        text = (root / pid / "INSTRUCTIONS.md").read_text(encoding="utf-8")
        assert "**强制阅读技能**" in text
        assert "skill_view" in text
        assert "sales-talk" in text
        assert "support-talk" in text
