"""Boss 职位名不得写入 Session / inbound."""

from __future__ import annotations

import pytest

from plugins.mxai.agents.hermes_agent import (
    _profile_session_db,
    inbound_session_id,
    record_inbound_turn,
)
from plugins.mxai.cfg.agent_bindings import inbound_session_profile
from plugins.mxai.crm.boss_greet_leads import register_greet_lead


def test_inbound_rejects_position_peer(mxai_client, mxai_env) -> None:
    del mxai_env
    register_greet_lead(
        "boss",
        name="真人甲",
        reason="匹配",
        position="新媒体销售专员",
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/boss/inbound",
        json={
            "message_id": "m1",
            "sender": "新媒体销售专员",
            "message": "你好",
        },
    )
    assert res.status_code == 422
    hermes = inbound_session_profile("boss")
    sid = inbound_session_id(hermes, "新媒体销售专员")
    db = _profile_session_db(hermes)
    try:
        assert db.resolve_session_id(sid) in (None, "")
    finally:
        db.close()


def test_record_inbound_turn_skips_position_peer(mxai_env) -> None:
    del mxai_env
    register_greet_lead(
        "boss",
        name="真人乙",
        reason="匹配",
        position="新媒体销售专员",
    )
    hermes = inbound_session_profile("boss")
    record_inbound_turn(hermes, "新媒体销售专员", "问", "答")
    sid = inbound_session_id(hermes, "新媒体销售专员")
    db = _profile_session_db(hermes)
    try:
        assert db.resolve_session_id(sid) in (None, "")
    finally:
        db.close()


def test_purge_position_sessions(mxai_client, mxai_env) -> None:
    del mxai_env
    register_greet_lead(
        "boss",
        name="真人丙",
        reason="匹配",
        position="新媒体销售专员",
    )
    hermes = inbound_session_profile("boss")
    # 绕过门禁直接造脏 session（模拟历史污染）
    from plugins.mxai.agents.hermes_agent import _ensure_inbound_session

    sid = inbound_session_id(hermes, "新媒体销售专员")
    db = _profile_session_db(hermes)
    try:
        _ensure_inbound_session(db, sid, "新媒体销售专员")
        assert db.resolve_session_id(sid)
    finally:
        db.close()

    res = mxai_client.post("/api/plugins/mxai/agents/boss/purge-position-sessions").json()
    assert res["deleted"] >= 1
    assert "新媒体销售专员" in res["user_ids"]

    db = _profile_session_db(hermes)
    try:
        assert db.resolve_session_id(sid) in (None, "")
    finally:
        db.close()


def test_follow_up_rejects_position_peer(mxai_client, mxai_env) -> None:
    del mxai_env
    register_greet_lead(
        "boss",
        name="真人戊",
        reason="匹配",
        position="新媒体销售专员",
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/boss/tasks/follow-up",
        json={
            "candidate": "新媒体销售专员",
            "recipient": "新媒体销售专员",
            "message": "拓聊",
        },
    )
    assert res.status_code == 422


def test_register_greet_lead_rejects_position_as_name(mxai_env) -> None:
    del mxai_env
    with pytest.raises(ValueError, match="not position"):
        register_greet_lead(
            "boss",
            name="运营专员",
            reason="x",
            position="运营专员",
        )
