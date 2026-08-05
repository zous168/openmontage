"""build_skills_system_prompt lean mode + disabled filter."""

from __future__ import annotations

from pathlib import Path

from agent.prompt_builder import build_skills_system_prompt, clear_skills_system_prompt_cache
from hermes_constants import reset_hermes_home_override, set_hermes_home_override
from plugins.mxai.cfg.store import atomic_write_yaml


def test_lean_skills_index_omits_disabled(tmp_path: Path, monkeypatch) -> None:
    skills_dir = tmp_path / "skills"
    skill_dir = skills_dir / "mxai" / "sales-talk"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: sales-talk\ndescription: sales playbook\n---\n# Sales\n",
        encoding="utf-8",
    )
    disabled_dir = skills_dir / "mxai" / "support-talk"
    disabled_dir.mkdir(parents=True)
    (disabled_dir / "SKILL.md").write_text(
        "---\nname: support-talk\ndescription: support playbook\n---\n# Support\n",
        encoding="utf-8",
    )

    atomic_write_yaml(
        tmp_path / "config.yaml",
        {
            "skills": {
                "disabled": ["support-talk"],
                "lean_index_categories": ["mxai"],
            }
        },
    )
    other = skills_dir / "github" / "github-pr-workflow"
    other.mkdir(parents=True)
    (other / "SKILL.md").write_text(
        "---\nname: github-pr-workflow\ndescription: unrelated github skill\n---\n",
        encoding="utf-8",
    )

    token = set_hermes_home_override(str(tmp_path))
    try:
        import agent.prompt_builder as pb

        clear_skills_system_prompt_cache(clear_snapshot=True)

        out = build_skills_system_prompt(
            available_tools={"skill_view", "mxai_kb_search"},
            available_toolsets={"skills_view", "mxai_kb_search"},
            lean=True,
        )
    finally:
        reset_hermes_home_override(token)

    assert "sales-talk" in out
    assert "- support-talk" not in out  # 禁用技能不进索引
    assert "github-pr-workflow" not in out
    assert "Skills (mandatory)" not in out
    assert "Skills（必读）" in out
    assert "skill_view" in out
    assert "skill_manage" not in out
    assert "必须" in out
