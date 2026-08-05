"""persist_user_message：落库用原文，打 LLM 前不得改写内存 messages。"""

from __future__ import annotations

from types import SimpleNamespace


def _agent_with_override(messages: list[dict], *, override: str, idx: int):
    from run_agent import AIAgent

    agent = object.__new__(AIAgent)
    agent.session_id = "test-session"
    agent._persist_user_message_idx = idx
    agent._persist_user_message_override = override
    agent._session_db = None
    agent._session_json_enabled = False
    agent._session_messages = None
    agent._last_flushed_db_idx = 0
    agent._session_db_created = True
    return agent


def test_early_persist_keeps_api_wrapped_user_in_memory() -> None:
    """turn 开头 crash-resilience persist 不得把包裹冲掉。"""
    wrapped = (
        '<untrusted_customer_message channel="wechat_chat">\n你好\n'
        "</untrusted_customer_message>"
    )
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": wrapped},
    ]
    agent = _agent_with_override(messages, override="你好", idx=1)
    agent._persist_session(messages)

    assert messages[1]["content"] == wrapped


def test_flush_writes_override_without_mutating_api_messages() -> None:
    wrapped = (
        '<untrusted_customer_message channel="wechat_chat">\n你好\n'
        "</untrusted_customer_message>"
    )
    messages = [{"role": "user", "content": wrapped}]
    written: list[dict] = []

    agent = _agent_with_override(messages, override="你好", idx=0)
    agent._session_db = SimpleNamespace(
        append_message=lambda **kw: written.append(kw),
    )
    agent._last_flushed_db_idx = 0
    agent._flush_messages_to_session_db(messages)

    assert messages[0]["content"] == wrapped
    assert written and written[0]["content"] == "你好"


def test_finalize_apply_rewrites_memory_after_llm() -> None:
    wrapped = "<untrusted_customer_message>你好</untrusted_customer_message>"
    messages = [{"role": "user", "content": wrapped}]
    agent = _agent_with_override(messages, override="你好", idx=0)
    agent._apply_persist_user_message_override(messages)
    assert messages[0]["content"] == "你好"
