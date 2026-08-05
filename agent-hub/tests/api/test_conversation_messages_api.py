"""POST …/conversations/{id}/messages API."""

from urllib.parse import quote

from fastapi.testclient import TestClient

from plugins.mxai.conversations.service import set_conversation_mode
from plugins.mxai.worklog.service import append_worklog


def _conv_id(peer: str) -> str:
    return f"C-{peer}"


def _session_messages(channel_id: str, recipient: str) -> list[dict]:
    """读 Hermes SessionDB 中该客户会话的全部消息（CR-159：业务 Agent 库）."""
    from plugins.mxai.agents.hermes_agent import _profile_session_db, inbound_session_id
    from plugins.mxai.cfg.agent_bindings import inbound_session_profile

    hp = inbound_session_profile(channel_id)
    sid = inbound_session_id(hp, recipient)
    db = _profile_session_db(hp)
    try:
        resolved = db.resolve_session_id(sid) or sid
        return db.get_messages(resolved)
    finally:
        db.close()


def test_post_message_requires_takeover(mxai_client: TestClient, mxai_env) -> None:
    peer = "mock_douyin_peer"
    append_worklog(
        profile_id="douyin",
        op_type="inbound_reply",
        exec_status="成功",
        op_object=f"{peer} · 问:在吗 · 答:您好",
        data_dir=mxai_env,
    )
    conv_id = _conv_id(peer)
    denied = mxai_client.post(
        f"/api/plugins/mxai/agents/douyin/conversations/{conv_id}/messages",
        json={"text": "人工回复"},
    )
    assert denied.status_code == 409

    set_conversation_mode("douyin", conv_id, "takeover", data_dir=mxai_env)
    ok = mxai_client.post(
        f"/api/plugins/mxai/agents/douyin/conversations/{conv_id}/messages",
        json={"text": "人工跟进报价"},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["message"]["id"]
    msgs = mxai_client.get(
        f"/api/plugins/mxai/agents/douyin/conversations/{conv_id}/messages",
    ).json()
    assert any(m.get("text") == "人工跟进报价" for m in msgs["items"])


def test_takeover_and_operator_message_append_to_session(
    mxai_client: TestClient, mxai_env
) -> None:
    """接管 marker + 坐席 assistant 消息落进同一客户 Hermes session（ADR-06 v2 §3.3④）."""
    peer = "mock_douyin_peer2"
    conv_id = _conv_id(peer)

    # 1) 人工接管开始 → takeover 标记消息（role=tool）
    takeover = mxai_client.post(
        f"/api/plugins/mxai/agents/douyin/conversations/{conv_id}/takeover",
        json={"takeover": True},
    )
    assert takeover.status_code == 200
    assert takeover.json()["mode"] == "takeover"

    msgs = _session_messages("douyin", peer)
    markers = [m for m in msgs if m.get("role") == "tool" and m.get("tool_name") == "takeover"]
    assert len(markers) == 1
    assert "[takeover]" in str(markers[0].get("content") or "")

    # 2) 坐席出站 → role=assistant 消息，与 marker 同一 session
    ok = mxai_client.post(
        f"/api/plugins/mxai/agents/douyin/conversations/{conv_id}/messages",
        json={"text": "人工报价 199"},
    )
    assert ok.status_code == 200

    msgs = _session_messages("douyin", peer)
    assistants = [
        m for m in msgs if m.get("role") == "assistant" and m.get("content") == "人工报价 199"
    ]
    assert len(assistants) == 1
    # marker 与坐席消息确实落进同一 session（同序列）
    roles = [m.get("role") for m in msgs]
    assert "tool" in roles and "assistant" in roles


def test_close_inbound_session_ends_with_closed_reason(mxai_client: TestClient, mxai_env) -> None:
    """办结 → end_session(end_reason='closed')（ADR-06 v2 §3.3④）。

    当前无办结 API 触发点（仅有 接管/切回自动/发送），直接验证 helper 表达。
    """
    from plugins.mxai.agents.hermes_agent import (
        _profile_session_db,
        close_inbound_session,
        inbound_session_id,
    )
    from plugins.mxai.cfg.agent_bindings import inbound_session_profile

    peer = "mock_douyin_peer3"
    hp = inbound_session_profile("douyin")
    close_inbound_session(hp, peer)

    sid = inbound_session_id(hp, peer)
    db = _profile_session_db(hp)
    try:
        resolved = db.resolve_session_id(sid) or sid
        meta = db.get_session(resolved)
    finally:
        db.close()
    assert meta is not None
    assert meta.get("end_reason") == "closed"
    assert meta.get("ended_at") is not None


def test_close_endpoint_ends_session_and_switches_auto(
    mxai_client: TestClient, mxai_env
) -> None:
    """POST …/conversations/{id}/close → end_session(closed) + 切回自动态。"""
    from plugins.mxai.agents.hermes_agent import _profile_session_db, inbound_session_id
    from plugins.mxai.cfg.agent_bindings import inbound_session_profile
    from plugins.mxai.conversations.service import get_conversation_mode

    peer = "mock_douyin_peer_close"
    conv_id = _conv_id(peer)
    hp = inbound_session_profile("douyin")

    # 先接管，验证 close 会把模式切回 auto
    mxai_client.post(
        f"/api/plugins/mxai/agents/douyin/conversations/{conv_id}/takeover",
        json={"takeover": True},
    )

    res = mxai_client.post(
        f"/api/plugins/mxai/agents/douyin/conversations/{conv_id}/close",
        json={},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["closed"] is True
    assert body["end_reason"] == "closed"

    # Hermes session 已 end_reason=closed（业务 Agent 库）
    sid = inbound_session_id(hp, peer)
    db = _profile_session_db(hp)
    try:
        resolved = db.resolve_session_id(sid) or sid
        meta = db.get_session(resolved)
    finally:
        db.close()
    assert meta is not None
    assert meta.get("end_reason") == "closed"

    # 模式切回自动
    assert get_conversation_mode("douyin", conv_id) != "takeover"


def test_boss_post_message(mxai_client: TestClient, mxai_env) -> None:
    peer = "cand_front_li"
    conv_id = _conv_id(peer)
    set_conversation_mode("boss", conv_id, "takeover", data_dir=mxai_env)
    path = f"/api/plugins/mxai/agents/boss/conversations/{quote(conv_id, safe='')}/messages"
    res = mxai_client.post(path, json={"text": "明天下午方便面试吗"})
    assert res.status_code == 200
    assert res.json()["send"].get("sent") is True
