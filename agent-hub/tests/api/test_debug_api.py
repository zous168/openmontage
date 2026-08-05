"""AI debug REST contract (CR-119 / LT-034.01.3)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.agents.hermes_agent import (
    _profile_session_db,
    debug_session_id,
    inbound_session_id,
)
from plugins.mxai.api.deps import get_queue
from plugins.mxai.cfg.agent_bindings import BUSINESS_AGENT_IDS, BUSINESS_AGENT_LABELS
from plugins.mxai.worklog.service import list_worklogs

_BASE = "/api/plugins/mxai/debug"


def _create(client: TestClient, agent: str = "wechat_chat", **body) -> dict:
    res = client.post(f"{_BASE}/agents/{agent}/sessions", json=body)
    assert res.status_code == 200, res.text
    return res.json()


def _send(client: TestClient, sid: str, content: str, agent: str = "wechat_chat", **extra) -> dict:
    res = client.post(
        f"{_BASE}/agents/{agent}/sessions/{sid}/messages",
        json={"content": content, **extra},
    )
    assert res.status_code == 200, res.text
    return res.json()


def test_debug_agents_list_shape(mxai_client: TestClient) -> None:
    res = mxai_client.get(f"{_BASE}/agents")
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == len(BUSINESS_AGENT_IDS)
    pids = {it["profile_id"] for it in body["items"]}
    assert pids == set(BUSINESS_AGENT_IDS)
    names = {it["profile_id"]: it["name"] for it in body["items"]}
    assert names["wechat_chat"] == BUSINESS_AGENT_LABELS["wechat_chat"]
    assert names["douyin_comment"] == BUSINESS_AGENT_LABELS["douyin_comment"]
    assert names["boss_dm"] == BUSINESS_AGENT_LABELS["boss_dm"]
    for it in body["items"]:
        assert it["agent"] == it["profile_id"]
        assert it["channel"]
        assert it["name"] == BUSINESS_AGENT_LABELS[it["profile_id"]]
        assert "ready" in it and isinstance(it["ready"], bool)
        assert set(it["model"]) == {"provider", "name"}


def test_non_debuggable_agent_rejected(mxai_client: TestClient) -> None:
    res = mxai_client.post(f"{_BASE}/agents/assistant/sessions", json={})
    assert res.status_code == 400
    assert "not debuggable" in res.json()["detail"]
    res2 = mxai_client.post(f"{_BASE}/agents/wechat/sessions", json={})
    assert res2.status_code == 400


def test_create_session_shape(mxai_client: TestClient) -> None:
    body = _create(mxai_client, "wechat_chat", customer_name="Zhang")
    assert body["agent"] == "wechat_chat"
    assert body["channel"] == "wechat"
    assert body["customer_name"] == "Zhang"
    assert body["bound_customer_uid"] is None
    assert body["seeded_memory_rounds"] == 0
    sid = body["session_id"]
    assert len(sid) == 16
    assert body["real_session_id"] == debug_session_id("wechat_chat", sid)


def test_send_message_returns_reply_and_diagnostics(mxai_client: TestClient) -> None:
    sid = _create(mxai_client)["session_id"]
    body = _send(mxai_client, sid, "hello?")
    assert body["reply"]
    diag = body["diagnostics"]
    assert "source" in diag
    assert "timing_ms" in diag
    assert "memory_rounds" in diag
    assert "tool_trace" in body
    assert isinstance(body["tool_trace"], list)


def test_send_message_does_not_write_worklog_or_enqueue(mxai_client: TestClient) -> None:
    q = get_queue()
    worklogs_before = len(list_worklogs(profile_id="wechat", limit=1000))
    tasks_before = len(q._tasks)
    sid = _create(mxai_client)["session_id"]
    _send(mxai_client, sid, "q1")
    _send(mxai_client, sid, "q2")
    assert len(list_worklogs(profile_id="wechat", limit=1000)) == worklogs_before
    assert len(q._tasks) == tasks_before


def test_debug_session_user_id_is_none(mxai_client: TestClient) -> None:
    sid = _create(mxai_client)["session_id"]
    _send(mxai_client, sid, "hi")
    real_sid = debug_session_id("wechat_chat", sid)
    db = _profile_session_db("wechat_chat")
    try:
        sess = db.get_session(real_sid)
    finally:
        db.close()
    assert sess is not None
    assert sess.get("user_id") is None


def test_multi_turn_continuity(mxai_client: TestClient) -> None:
    sid = _create(mxai_client)["session_id"]
    first = _send(mxai_client, sid, "turn1")
    rounds_1 = first["diagnostics"]["memory_rounds"]
    second = _send(mxai_client, sid, "turn2")
    rounds_2 = second["diagnostics"]["memory_rounds"]
    assert rounds_2 > rounds_1
    msgs = mxai_client.get(f"{_BASE}/agents/wechat_chat/sessions/{sid}/messages").json()
    contents = [m.get("content") or "" for m in msgs["items"]]
    assert any("turn1" in c for c in contents)
    assert any("turn2" in c for c in contents)
    assert msgs["total"] >= 4


def test_bind_customer_uid_seeds_readonly(mxai_client: TestClient) -> None:
    customer = "u_10086"
    src_sid = inbound_session_id("wechat_chat", customer)
    db = _profile_session_db("wechat_chat")
    try:
        db.ensure_session(src_sid, "api_server", user_id=customer)
        db.append_message(src_sid, "user", "hist-q")
        db.append_message(src_sid, "assistant", "hist-a")
        before = len(db.get_messages(src_sid))
    finally:
        db.close()
    body = _create(mxai_client, "wechat_chat", bind_customer_uid=customer)
    assert body["bound_customer_uid"] == customer
    assert body["seeded_memory_rounds"] == 1
    _send(mxai_client, body["session_id"], "debug-msg")
    db = _profile_session_db("wechat_chat")
    try:
        after = len(db.get_messages(src_sid))
    finally:
        db.close()
    assert after == before


def test_send_message_stream_sse_shape(mxai_client: TestClient) -> None:
    sid = _create(mxai_client)["session_id"]
    res = mxai_client.post(
        f"{_BASE}/agents/wechat_chat/sessions/{sid}/messages/stream",
        json={"content": "stream?"},
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/event-stream")
    body = res.text
    assert "event: delta" in body
    assert "event: done" in body
    assert '"diagnostics"' in body
    assert '"tool_trace"' in body


def test_send_message_stream_persists_turn(mxai_client: TestClient) -> None:
    sid = _create(mxai_client)["session_id"]
    res = mxai_client.post(
        f"{_BASE}/agents/wechat_chat/sessions/{sid}/messages/stream",
        json={"content": "persist-stream"},
    )
    assert res.status_code == 200, res.text
    _ = res.text
    msgs = mxai_client.get(f"{_BASE}/agents/wechat_chat/sessions/{sid}/messages").json()
    contents = [m.get("content") or "" for m in msgs["items"]]
    assert any("persist-stream" in c for c in contents)


def test_delete_session_clears_messages(mxai_client: TestClient) -> None:
    sid = _create(mxai_client)["session_id"]
    _send(mxai_client, sid, "to-delete")
    before = mxai_client.get(f"{_BASE}/agents/wechat_chat/sessions/{sid}/messages").json()
    assert before["total"] > 0
    res = mxai_client.delete(f"{_BASE}/agents/wechat_chat/sessions/{sid}")
    assert res.status_code == 200
    assert res.json()["deleted"] is True
    after = mxai_client.get(f"{_BASE}/agents/wechat_chat/sessions/{sid}/messages").json()
    assert after["total"] == 0
