"""LT-017.02.01：QueueManager 优先级 · drain · CR-66 · task_action."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from plugins.mxai.orchestrator.models import Task, TaskStatus, new_task_id
from plugins.mxai.orchestrator.queue_manager import QueueManager, WorkNotStartedError


def test_p1_drains_before_p3(mxai_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    del mxai_env
    order: list[str] = []

    def track(task: Task) -> dict:
        order.append(task.task_id)
        return {"ok": True}

    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge
    _b = get_rpa_worker_bridge()
    monkeypatch.setattr(_b, "is_connected", lambda: True)
    monkeypatch.setattr(_b, "execute_via_worker", lambda task, timeout=600.0: track(task))
    q = QueueManager.get()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    now = time.time()
    p3 = Task(
        task_id=new_task_id(),
        name="采集",
        profile_id="douyin",
        task_type="comment_collect",
        priority=3,
        status=TaskStatus.QUEUED,
        created_at=now,
    )
    # P1 须带可出站 hub_reply：空 inbound_reply 会在预计算后 skip RPA，进不了 execute_via_worker
    p1 = Task(
        task_id=new_task_id(),
        name="客服",
        profile_id="douyin",
        task_type="inbound_reply",
        priority=1,
        status=TaskStatus.QUEUED,
        created_at=now + 1.0,
        payload={
            "sender": "wxid_demo",
            "message": "你好",
            "hub_reply": {"text": "您好", "source": "fixed"},
        },
    )
    q.seed_in_memory([p3, p1])
    deadline = time.time() + 2.0
    while len(order) < 2 and time.time() < deadline:
        time.sleep(0.05)
    assert order[:2] == [p1.task_id, p3.task_id]


def test_global_paused_blocks_drain(mxai_env: Path) -> None:
    del mxai_env
    q = QueueManager.get()
    q.set_agent_enabled("douyin", True)
    q.set_global_pause(True)
    task = Task(
        task_id=new_task_id(),
        name="等待",
        profile_id="douyin",
        task_type="comment_collect",
        status=TaskStatus.QUEUED,
    )
    q.seed_in_memory([task])
    assert q.get_task(task.task_id).status == TaskStatus.QUEUED


def test_agent_disabled_blocks_drain(mxai_env: Path) -> None:
    del mxai_env
    q = QueueManager.get()
    q.set_agent_enabled("douyin", False)
    task = Task(
        task_id=new_task_id(),
        name="禁用",
        profile_id="douyin",
        task_type="comment_collect",
        status=TaskStatus.QUEUED,
    )
    q.seed_in_memory([task])
    assert q.get_task(task.task_id).status == TaskStatus.QUEUED


def test_enqueue_rejects_report_cr66(mxai_env: Path) -> None:
    del mxai_env
    q = QueueManager.get()
    with pytest.raises(ValueError, match="not an RPA queue operation"):
        q.enqueue(
            profile_id="douyin",
            name="报表",
            task_type="report",
            skip_risk=True,
        )


def test_enqueue_rejects_when_work_not_armed(mxai_env: Path) -> None:
    del mxai_env
    q = QueueManager.get()
    q.disarm_work()
    q.set_global_pause(True)
    with pytest.raises(WorkNotStartedError, match="尚未开始工作"):
        q.enqueue(
            profile_id="douyin",
            name="采集",
            task_type="comment_collect",
            skip_risk=True,
        )


def test_enqueue_allowed_when_paused_but_armed(mxai_env: Path) -> None:
    del mxai_env
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(True)
    q.set_agent_enabled("douyin", True)
    task = q.enqueue(
        profile_id="douyin",
        name="暂停态预入队",
        task_type="comment_collect",
        skip_risk=True,
    )
    assert task.status == TaskStatus.QUEUED


def test_task_action_pause_resume_stop_retry(mxai_env: Path) -> None:
    del mxai_env
    q = QueueManager.get()
    q.set_global_pause(True)
    task = Task(
        task_id=new_task_id(),
        name="操作",
        profile_id="douyin",
        task_type="comment_collect",
        status=TaskStatus.QUEUED,
    )
    q.seed_in_memory([task])
    q.task_action(task.task_id, "pause")
    assert q.get_task(task.task_id).status == TaskStatus.PAUSED
    q.task_action(task.task_id, "resume")
    assert q.get_task(task.task_id).status == TaskStatus.QUEUED
    q.task_action(task.task_id, "stop")
    assert q.get_task(task.task_id).status == TaskStatus.FAILED
    q.task_action(task.task_id, "retry")
    assert q.get_task(task.task_id).status == TaskStatus.QUEUED


def test_set_priority(mxai_env: Path) -> None:
    del mxai_env
    q = QueueManager.get()
    q.set_global_pause(True)
    task = Task(
        task_id=new_task_id(),
        name="调档",
        profile_id="douyin",
        task_type="dm",
        priority=2,
        status=TaskStatus.QUEUED,
    )
    q.seed_in_memory([task])
    q.set_priority(task.task_id, 1)
    assert q.get_task(task.task_id).priority == 1


def test_worker_dispatch_precomputes_hub_reply(mxai_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """RPA Worker 连接时 inbound 仍走 Hub profile Agent，而非 Mock 硬编码."""
    del mxai_env
    import json
    import threading
    import asyncio

    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge, reset_rpa_worker_bridge

    reset_rpa_worker_bridge()
    dispatched: list[dict] = []

    class _FakeWs:
        async def send_text(self, payload: str) -> None:
            dispatched.append(json.loads(payload))

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    try:
        bridge.register(_FakeWs(), loop, {"worker_id": "t", "channels": ["wechat"]})

        def fake_resolve(profile_id, message, *, recipient="", persist_session=True, **kwargs):
            return {"source": "faq", "text": f"[{profile_id}] FAQ答：{message}"}

        monkeypatch.setattr(
            "plugins.mxai.agents.pipeline.resolve_reply",
            fake_resolve,
        )

        captured: list[dict] = []

        def fake_worker(self, task: Task, timeout=600.0, **kwargs) -> dict:
            captured.append(dict(task.payload))
            return {"reply": task.payload.get("hub_reply", {}), "send": {"sent": True}}

        monkeypatch.setattr(
            "plugins.mxai.rpa_worker.bridge.RpaWorkerBridge.execute_via_worker",
            fake_worker,
        )

        q = QueueManager.get()
        q.set_global_pause(False)
        q.set_agent_enabled("wechat", True)
        task = Task(
            task_id=new_task_id(),
            name="入站",
            profile_id="wechat",
            task_type="inbound_reply",
            status=TaskStatus.QUEUED,
            payload={"message": "在吗", "sender": "u1"},
        )
        q.seed_in_memory([task])
        deadline = time.time() + 2.0
        done = q.get_task(task.task_id)
        while done.status in (TaskStatus.QUEUED, TaskStatus.RUNNING) and time.time() < deadline:
            time.sleep(0.05)
            done = q.get_task(task.task_id)
        assert done.status == TaskStatus.DONE, (done.status, done.fail_reason, done.steps)
        assert captured
        assert captured[0]["hub_reply"]["text"] == "[wechat] FAQ答：在吗"
    finally:
        loop.call_soon_threadsafe(loop.stop)
        reset_rpa_worker_bridge()


def test_inbound_reply_worklog_persists_ai_text(mxai_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """应答任务成功落库时 op_object 含问/答摘要."""
    del mxai_env
    from plugins.mxai.rpa_worker.bridge import reset_rpa_worker_bridge
    from plugins.mxai.worklog.service import list_worklogs

    reset_rpa_worker_bridge()

    def fake_handler(task: Task) -> dict:
        return {
            "reply": {"text": "您好，报价请咨询顾问。", "source": "llm"},
            "send": {"sent": True},
        }

    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge
    _b = get_rpa_worker_bridge()
    monkeypatch.setattr(_b, "is_connected", lambda: True)
    monkeypatch.setattr(_b, "execute_via_worker", lambda task, timeout=600.0: fake_handler(task))
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    q.enqueue(
        profile_id="douyin",
        name="入站应答",
        task_type="inbound_reply",
        payload={"message": "多少钱", "sender": "user_x"},
        skip_risk=True,
    )
    time.sleep(0.25)
    logs = list_worklogs(profile_id="douyin", limit=5)
    assert logs
    obj = logs[0].get("op_object") or ""
    assert "多少钱" in obj
    assert "报价" in obj
    assert logs[0].get("op_type") == "inbound_reply"


def test_rpa_online_http_mode_uses_health_not_ws(mxai_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """http 集成模式：在线判定用 automan /health 探活；WS 桥未连也算在线（否则任务永卡「排队中」）."""
    del mxai_env
    import plugins.mxai.cfg.client_settings as cs_mod
    from plugins.mxai.rpa_worker import automan_bridge
    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge

    monkeypatch.setattr(
        cs_mod, "read_client_settings",
        lambda *a, **k: {"rpa_integrate_mode": "http", "rpa_outbound_url": "http://127.0.0.1:8123"},
    )
    monkeypatch.setattr(get_rpa_worker_bridge(), "is_connected", lambda: False)  # WS 桥断开
    q = QueueManager.get()
    monkeypatch.setattr(automan_bridge, "probe_http_health", lambda url, **k: True)
    assert q._rpa_online() is True  # 探活通过即在线，不看 WS 桥
    monkeypatch.setattr(automan_bridge, "probe_http_health", lambda url, **k: False)
    assert q._rpa_online() is False


def test_cr164_http_health_edge_triggers_drain(mxai_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-164：HTTP health 503→200 边沿调用 notify→_drain_rpa 一次。"""
    del mxai_env
    from types import SimpleNamespace

    import httpx

    import plugins.mxai.cfg.client_settings as cs_mod
    from plugins.mxai.rpa_worker import automan_bridge

    monkeypatch.setattr(
        cs_mod,
        "read_client_settings",
        lambda *a, **k: {
            "rpa_integrate_mode": "http",
            "rpa_outbound_url": "http://127.0.0.1:18123",
        },
    )
    automan_bridge.reset_http_health_probe_state()
    q = QueueManager.get()
    drained: list[str] = []
    monkeypatch.setattr(q, "_drain_rpa", lambda: drained.append("drain"))

    codes = [503, 200, 200]

    class _FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, url):  # noqa: ARG002
            return SimpleNamespace(status_code=codes.pop(0))

    monkeypatch.setattr(httpx, "Client", _FakeClient)
    url = "http://127.0.0.1:18123"
    assert automan_bridge.probe_http_health(url, ttl=0.0) is False
    assert drained == []
    assert automan_bridge.probe_http_health(url, ttl=0.0) is True
    assert drained == ["drain"]
    assert automan_bridge.probe_http_health(url, ttl=0.0) is True
    assert drained == ["drain"]


def test_rpa_online_ws_mode_uses_bridge(mxai_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """ws 集成模式：仍用 WS 桥 is_connected 判定（不受 http 探活影响）."""
    del mxai_env
    import plugins.mxai.cfg.client_settings as cs_mod
    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge

    monkeypatch.setattr(
        cs_mod, "read_client_settings",
        lambda *a, **k: {"rpa_integrate_mode": "ws", "rpa_outbound_url": ""},
    )
    q = QueueManager.get()
    monkeypatch.setattr(get_rpa_worker_bridge(), "is_connected", lambda: True)
    assert q._rpa_online() is True
    monkeypatch.setattr(get_rpa_worker_bridge(), "is_connected", lambda: False)
    assert q._rpa_online() is False
