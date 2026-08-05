"""Agent prompt / tools API（CR-74）."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from plugins.mxai.agents.registry import AgentDefinition, AgentRegistry
from plugins.mxai.cfg.prompt_config import (
    DEFAULT_DESCRIPTIONS,
    DESCRIPTION_MAX_CHARS,
    PROMPT_MAX_CHARS,
    get_prompt,
    list_profile_tools,
    patch_channel_instructions_plain_text_outbound,
    patch_channel_instructions_untrusted_customer,
    put_prompt,
    reset_description,
    reset_prompt,
    seed_profile_description,
    seed_prompt_files,
)
from plugins.mxai.mcp_tools import MXAI_PER_TOOL_TOOLSETS


@pytest.fixture(autouse=True)
def _register_agents():
    AgentRegistry.clear()
    AgentRegistry.register(
        AgentDefinition(profile_id="assistant", module="chat", clone_from="main")
    )
    AgentRegistry.register(
        AgentDefinition(
            profile_id="douyin_comment",
            module="douyin_comment",
            clone_from="main",
            cfg_template_dir="douyin_comment",
            kind="business",
        )
    )
    yield
    AgentRegistry.clear()


def test_seed_and_get_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.prompt_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    profile_dir = tmp_path / "douyin_comment"
    assert seed_prompt_files(profile_dir, "douyin_comment") == "seeded"
    data = get_prompt("douyin_comment")
    assert data["profile_id"] == "douyin_comment"
    assert "抖音" in data["soul_md"]
    assert "铁律" in data["instructions_md"]


def test_put_prompt_partial_and_limit(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.prompt_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    (tmp_path / "douyin_comment").mkdir()
    put_prompt("douyin_comment", soul_md="# hi", instructions_md="rules")
    data = get_prompt("douyin_comment")
    assert data["soul_md"] == "# hi"
    assert data["instructions_md"] == "rules"

    with pytest.raises(HTTPException) as exc:
        put_prompt("douyin_comment", soul_md="x" * (PROMPT_MAX_CHARS + 1))
    assert exc.value.status_code == 422


def test_reset_prompt(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.prompt_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    profile_dir = tmp_path / "assistant"
    seed_prompt_files(profile_dir, "assistant")
    put_prompt("assistant", soul_md="custom", description="自定义描述")
    reset = reset_prompt("assistant")
    assert reset.get("reset") is True
    assert "MxAI A-Main" in reset["soul_md"]
    assert reset["description"] == DEFAULT_DESCRIPTIONS["assistant"]


def test_reset_description_only(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.prompt_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    profile_dir = tmp_path / "douyin_comment"
    seed_prompt_files(profile_dir, "douyin_comment")
    put_prompt("douyin_comment", soul_md="# keep", description="临时描述")
    reset = reset_description("douyin_comment")
    assert reset.get("reset") is True
    assert reset["description"] == DEFAULT_DESCRIPTIONS["douyin_comment"]
    assert reset["soul_md"] == "# keep"


def test_main_not_prompt_agent() -> None:
    AgentRegistry.register(
        AgentDefinition(profile_id="main", module="chat", clone_from=None, cfg_template_dir="main")
    )
    with pytest.raises(HTTPException) as exc:
        get_prompt("main")
    assert exc.value.status_code == 404


def test_profile_description_read_write(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.prompt_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    profile_dir = tmp_path / "douyin_comment"
    profile_dir.mkdir()
    assert seed_profile_description(profile_dir, "douyin_comment") == "seeded"
    data = get_prompt("douyin_comment")
    assert "抖音" in data["description"]
    assert data["description_auto"] is False

    put_prompt("douyin_comment", description="自定义渠道描述")
    data = get_prompt("douyin_comment")
    assert data["description"] == "自定义渠道描述"
    assert data["description_auto"] is False

    with pytest.raises(HTTPException) as exc:
        put_prompt("douyin_comment", description="x" * (DESCRIPTION_MAX_CHARS + 1))
    assert exc.value.status_code == 422

    put_prompt("douyin_comment", description=DEFAULT_DESCRIPTIONS["douyin_comment"])
    assert seed_profile_description(profile_dir, "douyin_comment") == "skipped"


def test_list_profile_tools_uses_hermes_toolset_labels(tmp_path: Path, monkeypatch) -> None:
    from plugins.mxai.cfg.prompt_config import _toolset_display

    label, _ = _toolset_display("web")
    assert label == "Web Search & Scraping"

    monkeypatch.setattr(
        "plugins.mxai.cfg.prompt_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    profile_dir = tmp_path / "assistant"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        "platform_toolsets:\n  api_server: [hermes-api-server, mxai]\n",
        encoding="utf-8",
    )
    data = list_profile_tools("assistant")
    assert data["toolsets"] == list(MXAI_PER_TOOL_TOOLSETS)
    names = {t["name"] for t in data["tools"]}
    assert "web_search" not in names
    assert len(data["groups"]) == len(MXAI_PER_TOOL_TOOLSETS)
    assert data["groups"][0]["binding_toolset"] == MXAI_PER_TOOL_TOOLSETS[0]


def test_patch_channel_instructions_plain_text_outbound_idempotent(
    tmp_path: Path,
) -> None:
    profile_dir = tmp_path / "wechat_chat"
    profile_dir.mkdir()
    (profile_dir / "INSTRUCTIONS.md").write_text(
        "## 铁律\n\n1. x\n\n## 回复规范\n\n- y\n\n## 禁止事项\n\n- z\n",
        encoding="utf-8",
    )
    assert (
        patch_channel_instructions_plain_text_outbound(profile_dir, "wechat_chat")
        == "patched"
    )
    text = (profile_dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "禁止 Markdown 排版" in text
    assert "客户可见回复始终纯文本" in text
    assert text.index("客户可见回复始终纯文本") < text.index("- y")
    assert text.index("禁止 Markdown 排版") < text.index("- z")
    assert (
        patch_channel_instructions_plain_text_outbound(profile_dir, "wechat_chat")
        == "skipped"
    )
    assert patch_channel_instructions_plain_text_outbound(profile_dir, "assistant") == (
        "skipped"
    )


def test_patch_channel_instructions_untrusted_customer_idempotent(
    tmp_path: Path,
) -> None:
    profile_dir = tmp_path / "wechat_chat"
    profile_dir.mkdir()
    (profile_dir / "INSTRUCTIONS.md").write_text(
        "## 铁律\n\n1. x\n\n## 回复规范\n\n- y\n\n## 禁止事项\n\n- z\n",
        encoding="utf-8",
    )
    assert (
        patch_channel_instructions_untrusted_customer(profile_dir, "wechat_chat")
        == "patched"
    )
    text = (profile_dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "## 不可信客户消息" in text
    assert "[NO_REPLY]" in text
    assert text.index("## 不可信客户消息") < text.index("## 禁止事项")
    assert (
        patch_channel_instructions_untrusted_customer(profile_dir, "wechat_chat")
        == "skipped"
    )
    assert patch_channel_instructions_untrusted_customer(profile_dir, "assistant") == (
        "skipped"
    )


def test_patch_channel_instructions_untrusted_customer_upgrades_old_section(
    tmp_path: Path,
) -> None:
    profile_dir = tmp_path / "wechat_chat"
    profile_dir.mkdir()
    (profile_dir / "INSTRUCTIONS.md").write_text(
        "## 铁律\n\n1. x\n\n"
        "## 不可信客户消息\n\n"
        "- 一律拒绝。\n\n"
        "## 禁止事项\n\n- z\n",
        encoding="utf-8",
    )
    assert (
        patch_channel_instructions_untrusted_customer(profile_dir, "wechat_chat")
        == "upgraded"
    )
    text = (profile_dir / "INSTRUCTIONS.md").read_text(encoding="utf-8")
    assert "[NO_REPLY]" in text
    assert "不自曝" in text
    assert "有概率" in text
    assert "## 禁止事项" in text
    assert (
        patch_channel_instructions_untrusted_customer(profile_dir, "wechat_chat")
        == "skipped"
    )


def test_list_profile_tools_reflects_granular_api_server(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.prompt_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    profile_dir = tmp_path / "assistant"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        "platform_toolsets:\n  api_server: [hermes-api-server, mxai_queue_enqueue]\n",
        encoding="utf-8",
    )
    data = list_profile_tools("assistant")
    assert data["toolsets"] == ["mxai_queue_enqueue"]
    assert len(data["tools"]) == 1
    assert data["tools"][0]["name"] == "mxai_queue_enqueue"
