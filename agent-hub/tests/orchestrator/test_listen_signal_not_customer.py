"""CR-152：``__listen_signal__`` 不得进客户 / 会话 / 台账客户列 / 预计算 LLM."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from plugins.mxai.agents.pipeline import resolve_reply
from plugins.mxai.api.deps import get_queue
from plugins.mxai.conversations.service import list_conversations
from plugins.mxai.crm.customer_inbound import touch_last_inbound
from plugins.mxai.crm.funnel import apply_funnel_from_task, upsert_customer_stage
from plugins.mxai.orchestrator.inbound_listen_coord import (
    LISTEN_SIGNAL_SENDER,
    is_listen_signal_peer,
    reset_inbound_listen_coord,
)
from plugins.mxai.orchestrator.models import Task
from plugins.mxai.orchestrator.queue_manager import _precompute_hub_reply, _worklog_op_object
from plugins.mxai.rpa_worker.automan_bridge import _inputs_for


@pytest.fixture(autouse=True)
def _reset_coord() -> None:
    reset_inbound_listen_coord()


def test_is_listen_signal_peer() -> None:
    assert is_listen_signal_peer(LISTEN_SIGNAL_SENDER) is True
    assert is_listen_signal_peer("real_customer") is False
    assert is_listen_signal_peer("") is False


def test_touch_last_inbound_skips_listen_signal(mxai_env) -> None:
    touch_last_inbound(LISTEN_SIGNAL_SENDER, "qiyeweixin", data_dir=mxai_env)
    upsert_customer_stage(
        LISTEN_SIGNAL_SENDER,
        "qiyeweixin",
        "consulting",
        data_dir=mxai_env,
    )
    apply_funnel_from_task(
        "qiyeweixin",
        "inbound_reply",
        {"sender": LISTEN_SIGNAL_SENDER, "message": "event_triggered"},
        {},
        data_dir=mxai_env,
    )
    from plugins.mxai.cfg.paths import mxai_db_path
    import sqlite3

    conn = sqlite3.connect(mxai_db_path("hub.db", mxai_env))
    try:
        n = conn.execute(
            "SELECT COUNT(*) FROM wecom_contacts WHERE customer_uid = ?",
            (LISTEN_SIGNAL_SENDER,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert n == 0


def test_resolve_reply_skips_listen_signal(mxai_env) -> None:
    out = resolve_reply("qiyeweixin", "event_triggered", recipient=LISTEN_SIGNAL_SENDER)
    assert out.get("source") == "listen_signal"
    assert out.get("text") == ""


def test_precompute_skips_listen_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple] = []

    def _boom(*a, **k):
        called.append((a, k))
        raise AssertionError("resolve_reply must not run for listen signal")

    monkeypatch.setattr("plugins.mxai.agents.pipeline.resolve_reply", _boom)
    task = Task(
        task_id="t1",
        name="监听回复",
        profile_id="qiyeweixin",
        task_type="inbound_reply",
        payload={
            "sender": LISTEN_SIGNAL_SENDER,
            "message": "event_triggered",
            "source": "automan_listen",
        },
    )
    _precompute_hub_reply(task)
    assert "hub_reply" not in task.payload
    assert any(s.get("reason") == "listen_signal" for s in task.steps)
    assert called == []


def test_precompute_dm_uses_fixed_message_without_resolve(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """主动 dm/follow_up 有出站话术时用 fixed，禁止 resolve_reply 污染真实 Session."""
    called = {"n": 0}

    def fake_resolve(*_a, **_k):
        called["n"] += 1
        return {"source": "faq", "text": "不应走到这里"}

    monkeypatch.setattr("plugins.mxai.agents.pipeline.resolve_reply", fake_resolve)
    script = "您好，看到您的项目经历很匹配，方便进一步聊聊吗？"
    task = Task(
        task_id="t-dm",
        name="主动发消息",
        profile_id="boss",
        task_type="follow_up",
        payload={
            "recipient": "张媛媛",
            "message": script,
        },
    )
    _precompute_hub_reply(task)
    assert called["n"] == 0
    assert task.payload.get("hub_reply") == {"text": script, "source": "fixed"}


def test_precompute_inbound_reply_uses_ephemeral_session(monkeypatch: pytest.MonkeyPatch) -> None:
    """inbound_reply 预计算不得写入真实客户 Session（ephemeral + persist=False）."""
    seen: dict[str, Any] = {}

    def fake_resolve(profile_id, message, *, recipient="", persist_session=True, **kwargs):
        seen["persist_session"] = persist_session
        seen["session_id"] = kwargs.get("session_id")
        seen["session_key"] = kwargs.get("session_key")
        return {"source": "faq", "text": "您好"}

    monkeypatch.setattr("plugins.mxai.agents.pipeline.resolve_reply", fake_resolve)
    task = Task(
        task_id="t-in",
        name="监听回复",
        profile_id="wechat",
        task_type="inbound_reply",
        payload={"sender": "客户A", "message": "在吗"},
    )
    _precompute_hub_reply(task)
    assert task.payload.get("hub_reply", {}).get("text") == "您好"
    assert seen.get("persist_session") is False
    assert "ephemeral" in str(seen.get("session_id") or "")
    assert "ephemeral" in str(seen.get("session_key") or "")


def test_precompute_skips_boss_position_peer(monkeypatch: pytest.MonkeyPatch, mxai_env) -> None:
    del mxai_env
    from plugins.mxai.crm.boss_greet_leads import register_greet_lead

    register_greet_lead(
        "boss",
        name="真人丁",
        reason="匹配",
        position="新媒体销售专员",
    )
    called: list[Any] = []

    def _boom(*a, **k):
        called.append(1)
        raise AssertionError("resolve_reply must not run for position peer")

    monkeypatch.setattr("plugins.mxai.agents.pipeline.resolve_reply", _boom)
    task = Task(
        task_id="t-pos",
        name="主动发消息",
        profile_id="boss",
        task_type="follow_up",
        payload={"recipient": "新媒体销售专员", "message": "拓聊话术"},
    )
    _precompute_hub_reply(task)
    assert "hub_reply" not in task.payload
    assert any(s.get("reason") == "boss_position_peer" for s in task.steps)
    assert called == []


def test_worklog_op_object_listen_signal() -> None:
    task = Task(
        task_id="t1",
        name="监听回复",
        profile_id="qiyeweixin",
        task_type="inbound_reply",
        payload={
            "sender": LISTEN_SIGNAL_SENDER,
            "message": "event_triggered",
            "source": "automan_listen",
        },
    )
    assert _worklog_op_object(task, {}) == "监听触发"


def test_worklog_op_object_after_inbound_bind() -> None:
    """/inbound 回写真实 peer 后，终态台账须带问/答，不得停留在「监听触发」."""
    task = Task(
        task_id="t2",
        name="监听回复: 范宇坤",
        profile_id="boss",
        task_type="inbound_reply",
        payload={
            "sender": "范宇坤",
            "message": "您好！我对您发布的职位十分感兴趣",
            "source": "automan_listen",
            "hub_reply": {
                "text": "您好！很高兴您对我们的职位感兴趣",
                "source": "llm",
            },
        },
    )
    op = _worklog_op_object(task, {})
    assert "范宇坤" in op
    assert "问:" in op
    assert "答:" in op
    assert op != "监听触发"


def test_inputs_for_listen_signal_empty_inputid() -> None:
    out = _inputs_for(
        "inbound_reply",
        {"sender": LISTEN_SIGNAL_SENDER, "hub_reply": {"text": ""}},
    )
    assert out["inputid"] == ""
    assert out["msg"] == ""


def test_list_conversations_hides_listen_signal(mxai_env, monkeypatch: pytest.MonkeyPatch) -> None:
    class _FakeDb:
        def list_sessions_by_id_prefix(self, prefix: str):
            return [
                {
                    "id": f"{prefix}deadbeef",
                    "user_id": LISTEN_SIGNAL_SENDER,
                    "title": LISTEN_SIGNAL_SENDER,
                    "last_active": "2026-07-16T00:00:00+00:00",
                },
                {
                    "id": f"{prefix}cafebabe",
                    "user_id": "real_peer",
                    "title": "真实客户",
                    "last_active": "2026-07-16T01:00:00+00:00",
                },
            ]

        def resolve_session_id(self, sid: str):
            return sid

        def get_messages(self, sid: str):
            return []

        def close(self):
            pass

    monkeypatch.setattr(
        "plugins.mxai.agents.hermes_agent._profile_session_db",
        lambda *_a, **_k: _FakeDb(),
    )
    items = list_conversations("qiyeweixin")
    uids = {c["name"] for c in items}
    assert LISTEN_SIGNAL_SENDER not in uids
    assert "real_peer" in uids


def test_listen_event_signal_queues_without_customer_name(
    mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    q = get_queue()
    q.set_agent_enabled("qiyeweixin", True)
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/listen-event",
        json={
            "sender": LISTEN_SIGNAL_SENDER,
            "message": "event_triggered",
            "message_id": "sig-1",
            "source": "automan_listen",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "queued"
    task = q.get_task(body["task_id"])
    assert task is not None
    assert task.name == "监听回复"
    assert task.payload.get("sender") == LISTEN_SIGNAL_SENDER


def test_inbound_rejects_listen_signal(mxai_client: TestClient) -> None:
    res = mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/inbound",
        json={"sender": LISTEN_SIGNAL_SENDER, "message": "hi"},
    )
    assert res.status_code == 422
