"""CR-159：渠道 list/mode 与业务 Agent SessionDB 写侧对齐."""

from __future__ import annotations

from plugins.mxai.agents.hermes_agent import record_inbound_turn, record_operator_message
from plugins.mxai.cfg.agent_bindings import (
    AGENT_QIYEWEIXIN_CHAT,
    inbound_session_profile,
)
from plugins.mxai.conversations.service import (
    get_conversation_mode,
    list_conversations,
    list_messages,
    set_conversation_mode,
)


def test_inbound_session_profile_defaults():
    assert inbound_session_profile("qiyeweixin") == AGENT_QIYEWEIXIN_CHAT
    assert inbound_session_profile("wechat") == "wechat_chat"
    assert inbound_session_profile("boss") == "boss_dm"
    assert inbound_session_profile(AGENT_QIYEWEIXIN_CHAT) == AGENT_QIYEWEIXIN_CHAT


def test_channel_list_sees_hermes_writes(mxai_env) -> None:
    del mxai_env
    hp = inbound_session_profile("qiyeweixin")
    record_inbound_turn(hp, "align_peer", "你好", "您好")
    convs = list_conversations("qiyeweixin")
    assert any(c["id"] == "C-align_peer" and c.get("channel") == "qiyeweixin" for c in convs)
    msgs = list_messages("qiyeweixin", "C-align_peer")
    assert [m["from"] for m in msgs] == ["user", "ai"]


def test_takeover_and_operator_same_db(mxai_env) -> None:
    del mxai_env
    peer = "align_takeover"
    set_conversation_mode("qiyeweixin", f"C-{peer}", "takeover")
    assert get_conversation_mode("qiyeweixin", f"C-{peer}") == "takeover"
    hp = inbound_session_profile("qiyeweixin")
    record_operator_message(hp, peer, "坐席说")
    msgs = list_messages("qiyeweixin", f"C-{peer}")
    assert any(m.get("text") == "坐席说" for m in msgs)
