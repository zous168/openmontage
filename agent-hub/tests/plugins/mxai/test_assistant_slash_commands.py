"""Assistant channel slash-command resolution (assistant profile scope)."""

from __future__ import annotations

import agent.skill_commands as skill_commands_mod
from plugins.mxai.agents.assistant import (
    HERMES_ASSISTANT_PROFILE,
    _parse_slash_command,
    _resolve_assistant_slash,
    list_assistant_slash_commands,
)


def test_parse_slash_command_tolerates_wechat_source_prefix() -> None:
    command, args = _parse_slash_command("[微信] /plan 下周排期")
    assert command == "plan"
    assert args == "下周排期"


def test_parse_slash_command_plain() -> None:
    command, args = _parse_slash_command("/comfyui 画海报")
    assert command == "comfyui"
    assert args == "画海报"


def test_parse_slash_command_non_slash() -> None:
    command, args = _parse_slash_command("你好")
    assert command is None
    assert args == ""


def test_resolve_assistant_slash_skill_injection_via_channel(
    mxai_env, monkeypatch
) -> None:
    from plugins.mxai.agents.assistant import ASSISTANT_CHANNEL_WECOM

    monkeypatch.setattr(
        "agent.skill_commands.build_skill_invocation_message",
        lambda cmd_key, user_instruction="", **kwargs: f"SKILL:{cmd_key}:{user_instruction}",
    )
    monkeypatch.setattr(
        "agent.skill_commands.resolve_skill_command_key",
        lambda command: "/plan" if command == "plan" else None,
    )
    monkeypatch.setattr(
        "agent.skill_commands.get_skill_commands",
        lambda: {"/plan": {"name": "plan"}},
    )

    agent_text, direct = _resolve_assistant_slash(
        HERMES_ASSISTANT_PROFILE,
        "/plan 测试",
        channel=ASSISTANT_CHANNEL_WECOM,
    )
    assert direct is None
    assert agent_text == "SKILL:/plan:测试"


def test_resolve_assistant_slash_skill_injection(
    mxai_env, monkeypatch
) -> None:
    sentinel_before = skill_commands_mod._skill_commands.copy()
    sentinel_plat = skill_commands_mod._skill_commands_platform

    def _fake_build(cmd_key: str, user_instruction: str = "", **kwargs: object) -> str:
        return f"SKILL:{cmd_key}:{user_instruction}"

    monkeypatch.setattr(
        "agent.skill_commands.build_skill_invocation_message",
        _fake_build,
    )
    monkeypatch.setattr(
        "agent.skill_commands.resolve_skill_command_key",
        lambda command: "/plan" if command == "plan" else None,
    )
    monkeypatch.setattr(
        "agent.skill_commands.get_skill_commands",
        lambda: {"/plan": {"name": "plan"}},
    )

    agent_text, direct = _resolve_assistant_slash(
        HERMES_ASSISTANT_PROFILE,
        "[微信] /plan 测试",
    )
    assert direct is None
    assert agent_text == "SKILL:/plan:测试"
    assert skill_commands_mod._skill_commands == sentinel_before
    assert skill_commands_mod._skill_commands_platform == sentinel_plat


def test_resolve_assistant_slash_unknown_passthrough(
    mxai_env, monkeypatch
) -> None:
    monkeypatch.setattr(
        "agent.skill_commands.resolve_skill_command_key",
        lambda _command: None,
    )
    monkeypatch.setattr(
        "agent.skill_bundles.resolve_bundle_command_key",
        lambda _command: None,
    )

    original = "[微信] /sd hello"
    agent_text, direct = _resolve_assistant_slash(HERMES_ASSISTANT_PROFILE, original)
    assert direct is None
    assert agent_text == original


def test_resolve_assistant_slash_quick_command_exec(
    mxai_env, monkeypatch
) -> None:
    assistant_cfg = mxai_env / "profiles" / HERMES_ASSISTANT_PROFILE / "config.yaml"
    assistant_cfg.write_text(
        assistant_cfg.read_text(encoding="utf-8")
        + "\nquick_commands:\n  ping:\n    type: exec\n    command: echo PONG\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "plugins.mxai.agents.assistant._run_quick_command_exec",
        lambda _cmd: {"source": "quick_command", "text": "PONG"},
    )

    _agent_text, direct = _resolve_assistant_slash(HERMES_ASSISTANT_PROFILE, "/ping")
    assert direct == {"source": "quick_command", "text": "PONG"}


def test_resolve_assistant_slash_quick_command_alias(
    mxai_env, monkeypatch
) -> None:
    from hermes_cli import config as hermes_config

    assistant_cfg = mxai_env / "profiles" / HERMES_ASSISTANT_PROFILE / "config.yaml"
    assistant_cfg.write_text(
        assistant_cfg.read_text(encoding="utf-8")
        + "\nquick_commands:\n  p:\n    type: alias\n    target: /plan\n",
        encoding="utf-8",
    )
    hermes_config._LOAD_CONFIG_CACHE.clear()
    hermes_config._RAW_CONFIG_CACHE.clear()

    monkeypatch.setattr(
        "agent.skill_commands.resolve_skill_command_key",
        lambda command: "/plan" if command == "plan" else None,
    )
    monkeypatch.setattr(
        "agent.skill_commands.get_skill_commands",
        lambda: {"/plan": {"name": "plan"}},
    )
    monkeypatch.setattr(
        "agent.skill_commands.build_skill_invocation_message",
        lambda cmd_key, user_instruction="", **kwargs: f"SKILL:{cmd_key}",
    )

    agent_text, direct = _resolve_assistant_slash(HERMES_ASSISTANT_PROFILE, "/p 别名测试")
    assert direct is None
    assert agent_text == "SKILL:/plan"


def test_complete_assistant_message_applies_slash_before_mock(
    mxai_env, monkeypatch
) -> None:
    from plugins.mxai.agents.assistant import complete_assistant_message

    monkeypatch.setenv("MXAI_MOCK", "1")
    captured: dict[str, str] = {}

    def _fake_resolve(profile_id: str, text: str, **kwargs) -> tuple[str, dict | None]:
        captured["text"] = text
        return "INJECTED_SKILL_BODY", None

    monkeypatch.setattr(
        "plugins.mxai.agents.assistant._resolve_assistant_slash",
        _fake_resolve,
    )

    result = complete_assistant_message(HERMES_ASSISTANT_PROFILE, "/plan 测试")
    assert captured["text"] == "/plan 测试"
    assert result.get("text")


def test_hermes_session_chat_passes_persist_message_on_skill_rewrite(
    mxai_env, monkeypatch
) -> None:
    from plugins.mxai.agents.assistant import _hermes_session_chat

    captured: dict[str, str | None] = {}

    def _fake_complete(*_args, **kwargs):
        captured["message"] = kwargs.get("message") or (_args[1] if len(_args) > 1 else "")
        captured["persist_message"] = kwargs.get("persist_message")
        return {"text": "ok", "source": "agent_llm"}

    monkeypatch.setattr(
        "plugins.mxai.agents.hermes_agent.complete_profile_agent_reply",
        _fake_complete,
    )

    _hermes_session_chat(
        "INJECTED",
        persist_message="/plan 测试",
    )
    assert captured["message"] == "INJECTED"
    assert captured["persist_message"] == "/plan 测试"


def test_list_assistant_slash_commands_includes_quick_and_skills(
    mxai_env, monkeypatch
) -> None:
    assistant_cfg = mxai_env / "profiles" / HERMES_ASSISTANT_PROFILE / "config.yaml"
    assistant_cfg.write_text(
        assistant_cfg.read_text(encoding="utf-8")
        + "\nquick_commands:\n  ping:\n    type: exec\n    command: echo PONG\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "agent.skill_commands.get_skill_commands",
        lambda: {"/plan": {"name": "plan", "description": "开发计划"}},
    )
    monkeypatch.setattr("agent.skill_commands.scan_skill_commands", lambda: None)

    items = list_assistant_slash_commands(HERMES_ASSISTANT_PROFILE, prefix="", limit=50)
    texts = {item["text"] for item in items}
    assert "/ping" in texts
    assert "/plan" in texts

    filtered = list_assistant_slash_commands(HERMES_ASSISTANT_PROFILE, prefix="pl", limit=10)
    assert all(item["text"].lstrip("/").startswith("pl") for item in filtered)
    assert any(item["text"] == "/plan" for item in filtered)


def test_chat_commands_slash_api(mxai_client, monkeypatch) -> None:
    monkeypatch.setattr(
        "agent.skill_commands.get_skill_commands",
        lambda: {"/plan": {"name": "plan", "description": "开发计划"}},
    )
    monkeypatch.setattr("agent.skill_commands.scan_skill_commands", lambda: None)

    res = mxai_client.get(
        "/api/plugins/mxai/chat/commands/slash",
        params={"agent": "assistant", "prefix": "pl", "limit": 10},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["agent"] == "assistant"
    assert any(item["text"] == "/plan" for item in body["items"])
