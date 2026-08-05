"""LT-018.02.02 / 02.03 run API + scheduler_active."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.orchestrator.queue_manager import QueueManager


def _enable_channel(mxai_client: TestClient, channel: str) -> None:
    mxai_client.post(f"/api/plugins/mxai/run/agents/{channel}/start")


def _seed_douyin_keywords(mxai_client: TestClient) -> None:
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/comment-keywords",
        json={"search_keywords": ["营销", "自动化"], "match_keywords": ["怎么联系"]},
    )


def test_start_scheduler_active_and_pause(mxai_client: TestClient) -> None:
    QueueManager.reset()
    start = mxai_client.post("/api/plugins/mxai/run/all/start")
    assert start.status_code == 200
    body = start.json()
    assert body["scheduler_active"] is True
    assert body.get("work_armed") is True
    assert "bootstrap" in body

    pause = mxai_client.post("/api/plugins/mxai/run/all/pause")
    assert pause.json()["scheduler_active"] is False


def test_start_response_bootstrap_summary(mxai_client: TestClient) -> None:
    _seed_douyin_keywords(mxai_client)
    QueueManager.reset()
    res = mxai_client.post("/api/plugins/mxai/run/all/start").json()
    assert "bootstrap" in res
    assert "total_enqueued" in res["bootstrap"]


def test_stop_clears_queue_and_scheduler(mxai_client: TestClient) -> None:
    _seed_douyin_keywords(mxai_client)
    QueueManager.reset()
    mxai_client.post("/api/plugins/mxai/run/all/start")
    stop = mxai_client.post("/api/plugins/mxai/run/all/stop")
    assert stop.status_code == 200
    assert stop.json()["scheduler_active"] is False
    summary = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary.get("queued_count", 0) == 0


def test_start_enqueues_when_keywords(mxai_client: TestClient) -> None:
    _seed_douyin_keywords(mxai_client)
    QueueManager.reset()
    _enable_channel(mxai_client, "douyin")
    mxai_client.post("/api/plugins/mxai/run/all/start")
    tasks = mxai_client.get("/api/plugins/mxai/queue/tasks").json()
    items = tasks.get("items") or []
    assert any(t.get("task_type") == "comment_collect" for t in items)


def test_run_all_start_stop_sends_monitor(mxai_client: TestClient, monkeypatch) -> None:
    """LT-032.06.01：开始工作发 monitor.start，停止工作发 monitor.stop."""
    calls: list[tuple[str, object]] = []
    stop_all_calls: list[int] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

        def send_stop_all_executions(self) -> bool:
            stop_all_calls.append(1)
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    monkeypatch.setattr("plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()

    _enable_channel(mxai_client, "wechat")
    mxai_client.patch(
        "/api/plugins/mxai/agents/wechat/modules/inbound_reply",
        json={"enabled": True},
    )
    start = mxai_client.post("/api/plugins/mxai/run/all/start").json()
    assert start["monitor"] is True
    assert calls and calls[0][0] == "start"
    assert isinstance(calls[0][1], list)

    stop = mxai_client.post("/api/plugins/mxai/run/all/stop").json()
    assert stop["monitor"] is True
    assert stop.get("executions_stopped") is True
    assert stop_all_calls == [1]
    assert calls[-1][0] == "stop"
    assert isinstance(calls[-1][1], list)
    assert "weixin_listen" in calls[-1][1]


def test_run_agent_toggle_sends_monitor_single_channel(mxai_client: TestClient, monkeypatch) -> None:
    """LT-032.06.01：单渠道 start/stop 仅对该渠道发 monitor slug."""
    calls: list[tuple[str, object]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()
    QueueManager.get().arm_work()

    mxai_client.patch(
        "/api/plugins/mxai/agents/wechat/modules/inbound_reply",
        json={"enabled": True},
    )
    res = mxai_client.post("/api/plugins/mxai/run/agents/wechat/start").json()
    assert res["monitor"] is True
    assert calls[-1][0] == "start"
    assert calls[-1][1] == ["weixin_listen"]


def test_enqueue_rejected_before_start_work(mxai_client: TestClient) -> None:
    q = QueueManager.get()
    q.disarm_work()
    q.set_global_pause(True)
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"keywords": ["营销"]},
    )
    assert resp.status_code == 409
    assert "尚未开始工作" in resp.json()["detail"]
