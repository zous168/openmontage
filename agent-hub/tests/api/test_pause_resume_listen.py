from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_pause_all_then_queue_resume_restarts_wechat_listen(mxai_client: TestClient, monkeypatch) -> None:
    """Dashboard: 暂停全部(run/all/pause) → 继续工作(queue/resume) 须再发 weixin_listen start."""
    calls: list[tuple[str, object]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, list(monitor_slugs or [])))
            return True

        def send_stop_all_executions(self) -> bool:
            return True

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge",
        lambda: _FakeBridge(),
    )
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: _FakeBridge(),
    )
    QueueManager.reset()

    mxai_client.post("/api/plugins/mxai/run/agents/wechat/start")
    mxai_client.post("/api/plugins/mxai/run/agents/qiyeweixin/start")
    mxai_client.patch(
        "/api/plugins/mxai/agents/wechat/modules/inbound_reply",
        json={"enabled": True},
    )
    mxai_client.patch(
        "/api/plugins/mxai/agents/qiyeweixin/modules/inbound_reply",
        json={"enabled": True},
    )

    start = mxai_client.post("/api/plugins/mxai/run/all/start").json()
    assert start["scheduler_active"] is True
    assert start.get("monitor") is True
    assert any(a == "start" and "weixin_listen" in (slugs or []) for a, slugs in calls)

    pause = mxai_client.post("/api/plugins/mxai/run/all/pause").json()
    assert pause["scheduler_active"] is False
    assert any(a == "stop" for a, _ in calls)

    q = QueueManager.get()
    assert q.is_agent_enabled("wechat") is False  # pause disables agents
    assert q.is_agent_enabled("qiyeweixin") is False

    calls.clear()
    resume = mxai_client.post("/api/plugins/mxai/queue/resume").json()
    assert resume["paused"] is False
    assert resume.get("scheduler_active") is True
    assert resume.get("monitor") is True, resume
    assert any(
        a == "start" and "weixin_listen" in (slugs or []) for a, slugs in calls
    ), calls
    assert any(
        a == "start" and "qiwei_listen" in (slugs or []) for a, slugs in calls
    ), calls
    # 队列渠道必须恢复，否则 listen-event 会 agent_disabled 跳过
    assert q.is_agent_enabled("wechat") is True
    assert q.is_agent_enabled("qiyeweixin") is True


def test_pause_resume_listen_event_not_agent_disabled(mxai_client: TestClient, monkeypatch) -> None:
    """暂停后再恢复，listen-event 不得再返回 agent_disabled."""
    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            return True

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge",
        lambda: _FakeBridge(),
    )
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: _FakeBridge(),
    )
    QueueManager.reset()
    mxai_client.post("/api/plugins/mxai/run/agents/wechat/start")
    mxai_client.patch(
        "/api/plugins/mxai/agents/wechat/modules/inbound_reply",
        json={"enabled": True},
    )
    mxai_client.post("/api/plugins/mxai/run/all/start")
    mxai_client.post("/api/plugins/mxai/run/all/pause")
    mxai_client.post("/api/plugins/mxai/queue/resume")

    # 模拟 Automan 常驻监听到消息
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={"message_id": "m_resume_1", "sender": "__listen_signal__", "message": "event_triggered"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("reason") != "agent_disabled"
    assert body.get("task_id") or body.get("status") in {"queued", "running", "deduped", "busy"}
