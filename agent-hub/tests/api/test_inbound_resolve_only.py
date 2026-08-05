"""POST /inbound 只取文案、不入队（对齐 CR-152；公域首评/评论回复勿叠出站）."""

from __future__ import annotations

import pytest

from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_douyin_inbound_does_not_enqueue(mxai_client) -> None:
    qm = QueueManager.get()
    qm.reset()
    qm = QueueManager.get()
    mxai_client.post("/api/plugins/mxai/run/all/start")
    before = set(qm._tasks)

    resp = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/inbound",
        json={
            "message_id": "fc-1",
            "sender": "bench_user",
            "message": "请为这条视频生成首评",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "replied"
    assert body["task_id"] is None
    assert body["send_status"] == "not_enqueued"
    assert str(body.get("reply", {}).get("text") or "").strip()
    assert set(qm._tasks) == before
    assert not any(t.task_type == "inbound_reply" for t in qm._tasks.values())
    assert not any(t.task_type == "dm" for t in qm._tasks.values())


def test_wechat_inbound_does_not_enqueue(mxai_client) -> None:
    qm = QueueManager.get()
    qm.reset()
    qm = QueueManager.get()
    mxai_client.post("/api/plugins/mxai/run/all/start")
    before = set(qm._tasks)

    resp = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/inbound",
        json={"message_id": "wx1", "sender": "wx_user", "message": "你好"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "replied"
    assert body["task_id"] is None
    assert body["send_status"] == "not_enqueued"
    assert body["reply"]["source"] == "llm"
    assert set(qm._tasks) == before


def test_inbound_same_message_id_is_idempotent(mxai_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """同一 message_id 重试 /inbound：不二次调 LLM，避免 Session 双写。"""
    from plugins.mxai.orchestrator.inbound_listen_coord import reset_inbound_listen_coord

    reset_inbound_listen_coord()
    qm = QueueManager.get()
    qm.reset()
    qm = QueueManager.get()
    mxai_client.post("/api/plugins/mxai/run/all/start")

    calls = {"n": 0}

    def _fake_resolve(agent, text, recipient=None, **kwargs):
        calls["n"] += 1
        return {"source": "mock", "text": f"reply-{calls['n']}"}

    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.resolve_reply",
        _fake_resolve,
    )
    payload = {"message_id": "idem-1", "sender": "idem_user", "message": "同一句"}
    r1 = mxai_client.post("/api/plugins/mxai/agents/wechat/inbound", json=payload)
    r2 = mxai_client.post("/api/plugins/mxai/agents/wechat/inbound", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["reply"]["text"] == "reply-1"
    assert r2.json()["reply"]["text"] == "reply-1"
    assert calls["n"] == 1


def test_inbound_binds_listen_signal_reply_task(mxai_client, monkeypatch: pytest.MonkeyPatch) -> None:
    """signal 入队的 RUNNING inbound_reply，经 /inbound 回写真实 peer 供台账."""
    from plugins.mxai.orchestrator.inbound_listen_coord import (
        LISTEN_SIGNAL_MESSAGE,
        LISTEN_SIGNAL_SENDER,
        reset_inbound_listen_coord,
    )
    from plugins.mxai.orchestrator.models import TaskStatus
    from plugins.mxai.orchestrator.queue_manager import _worklog_op_object

    reset_inbound_listen_coord()
    qm = QueueManager.get()
    qm.reset()
    qm = QueueManager.get()
    mxai_client.post("/api/plugins/mxai/run/all/start")

    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline.resolve_reply",
        lambda *_a, **_k: {"source": "mock", "text": "很高兴您感兴趣"},
    )

    task = qm.enqueue(
        profile_id="boss",
        name="监听回复",
        task_type="inbound_reply",
        operator="系统自动",
        payload={
            "sender": LISTEN_SIGNAL_SENDER,
            "message": LISTEN_SIGNAL_MESSAGE,
            "source": "automan_listen",
        },
        skip_risk=True,
    )
    with qm._mutex:
        qm._tasks[task.task_id].status = TaskStatus.RUNNING

    resp = mxai_client.post(
        "/api/plugins/mxai/agents/boss/inbound",
        json={
            "message_id": "boss-1",
            "sender": "范宇坤",
            "message": "我对职位感兴趣",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == task.task_id
    bound = qm.get_task(task.task_id)
    assert bound is not None
    assert bound.payload.get("sender") == "范宇坤"
    assert "感兴趣" in str(bound.payload.get("message") or "")
    assert bound.payload.get("hub_reply", {}).get("text") == "很高兴您感兴趣"
    op = _worklog_op_object(bound, {})
    assert "范宇坤" in op and "问:" in op and "答:" in op
    assert op != "监听触发"
