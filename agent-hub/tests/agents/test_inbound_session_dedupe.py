"""Session 入站防双写 / 空消息不写."""

from __future__ import annotations

from plugins.mxai.agents.hermes_agent import (
    canonical_inbound_peer,
    inbound_session_id,
    record_inbound_turn,
    record_inbound_user,
    _profile_session_db,
)
from plugins.mxai.cfg.agent_bindings import inbound_session_profile


def test_record_inbound_turn_skips_empty_user(mxai_env) -> None:
    del mxai_env
    hermes = inbound_session_profile("wechat")
    peer = "空消息客户"
    record_inbound_turn(hermes, peer, "", "只有 AI")
    db = _profile_session_db(hermes)
    try:
        sid = inbound_session_id(hermes, peer)
        rows = db.get_messages(sid) or []
        assert rows == []
    finally:
        db.close()


def test_record_inbound_turn_dedupes_same_user(mxai_env) -> None:
    del mxai_env
    hermes = inbound_session_profile("wechat")
    peer = "双写客户"
    record_inbound_user(hermes, peer, "你好在吗")
    record_inbound_turn(hermes, peer, "你好在吗", "您好，请问有什么可以帮您？")
    db = _profile_session_db(hermes)
    try:
        sid = inbound_session_id(hermes, peer)
        rows = db.get_messages(sid) or []
        users = [r for r in rows if str(r.get("role") or "").lower() == "user"]
        assistants = [r for r in rows if str(r.get("role") or "").lower() == "assistant"]
        assert len(users) == 1
        assert len(assistants) == 1
        assert str(users[0].get("content") or "") == "你好在吗"
    finally:
        db.close()


def test_boss_peer_canonical_shares_session(mxai_env) -> None:
    del mxai_env
    hermes = inbound_session_profile("boss")
    a = canonical_inbound_peer(hermes, " 冯杰 ")
    b = canonical_inbound_peer("boss", "冯杰")
    assert a == b == "冯杰"
    assert inbound_session_id(hermes, " 冯杰 ") == inbound_session_id(hermes, "冯杰")
