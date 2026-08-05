"""LT-017.02.02：queue REST 集成测试."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.api.deps import get_queue
from plugins.mxai.orchestrator.models import Task, TaskStatus, new_task_id


def _seed_queued(mxai_client: TestClient) -> tuple[str, str]:
    q = get_queue()
    q.set_global_pause(True)
    q.set_agent_enabled("douyin", True)
    p1_id = new_task_id()
    p3_id = new_task_id()
    q.seed_in_memory(
        [
            Task(
                task_id=p3_id,
                name="采集",
                profile_id="douyin",
                task_type="comment_collect",
                priority=3,
                status=TaskStatus.QUEUED,
                created_at=10.0,
            ),
            Task(
                task_id=p1_id,
                name="客服",
                profile_id="douyin",
                task_type="inbound_reply",
                priority=1,
                status=TaskStatus.QUEUED,
                created_at=20.0,
            ),
        ]
    )
    return p1_id, p3_id


def test_queue_resume(mxai_client: TestClient) -> None:
    mxai_client.post("/api/plugins/mxai/queue/pause")
    resp = mxai_client.post("/api/plugins/mxai/queue/resume")
    assert resp.status_code == 200
    assert resp.json()["paused"] is False
    summary = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary["paused"] is False


def test_queue_pause_stops_monitor_and_blocks_listen_event(
    mxai_client: TestClient, monkeypatch
) -> None:
    """底栏全局暂停须停 listen，且 listen-event 不得再入队."""
    from unittest.mock import MagicMock

    from plugins.mxai.orchestrator.inbound_listen_coord import (
        is_monitor_session_active,
        mark_monitor_sessions,
        reset_inbound_listen_coord,
    )

    reset_inbound_listen_coord()
    q = get_queue()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("boss", True)
    mark_monitor_sessions(["boss"])
    assert is_monitor_session_active("boss")

    stops: list[tuple] = []
    mock_bridge = MagicMock()
    mock_bridge.send_monitor = lambda action, channels=None: stops.append((action, channels)) or True
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge",
        lambda: mock_bridge,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.cron.sync_all_mxai_scheduler_jobs",
        lambda: [],
    )

    pause = mxai_client.post("/api/plugins/mxai/queue/pause")
    assert pause.status_code == 200
    assert pause.json()["paused"] is True
    assert is_monitor_session_active("boss") is False
    assert any(a == "stop" for a, _ in stops)

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/boss/listen-event",
        json={
            "sender": "__listen_signal__",
            "message": "event_triggered",
            "message_id": "after-pause",
            "source": "automan_listen",
        },
    )
    assert res.status_code == 409


def test_queue_live(mxai_client: TestClient) -> None:
    _seed_queued(mxai_client)
    body = mxai_client.get("/api/plugins/mxai/queue/live").json()
    assert "running" in body
    assert "queued_head" in body
    assert "recent_done" in body
    assert len(body["queued_head"]) >= 1


def test_queue_tasks_priority_label_and_seq(mxai_client: TestClient) -> None:
    p1_id, p3_id = _seed_queued(mxai_client)
    items = mxai_client.get("/api/plugins/mxai/queue/tasks").json()["items"]
    by_id = {x["task_id"]: x for x in items}
    assert by_id[p1_id]["priority_label"] == "P1·客服应答"
    assert by_id[p1_id]["execution_seq"] == 1
    assert by_id[p3_id]["execution_seq"] == 2


def test_patch_priority_reorders_list(mxai_client: TestClient) -> None:
    p1_id, p3_id = _seed_queued(mxai_client)
    mxai_client.patch(
        f"/api/plugins/mxai/queue/tasks/{p3_id}/priority",
        json={"priority": 1},
    )
    items = mxai_client.get(
        "/api/plugins/mxai/queue/tasks",
        params={"status": "排队中"},
    ).json()["items"]
    by_id = {x["task_id"]: x for x in items}
    assert by_id[p3_id]["execution_seq"] == 1
    assert by_id[p1_id]["execution_seq"] == 2


def test_task_pause_resume_single(mxai_client: TestClient) -> None:
    q = get_queue()
    q.set_global_pause(True)
    tid = new_task_id()
    q.seed_in_memory(
        [
            Task(
                task_id=tid,
                name="待暂停",
                profile_id="douyin",
                task_type="comment_collect",
                status=TaskStatus.QUEUED,
            )
        ]
    )
    paused = mxai_client.post(f"/api/plugins/mxai/queue/tasks/{tid}/pause").json()
    assert paused["status"] == "已暂停"
    resumed = mxai_client.post(f"/api/plugins/mxai/queue/tasks/{tid}/resume").json()
    assert resumed["status"] == "排队中"


def test_pause_running_task_rejected(mxai_client: TestClient) -> None:
    q = get_queue()
    q.set_global_pause(True)
    tid = new_task_id()
    q.seed_in_memory(
        [
            Task(
                task_id=tid,
                name="执行中",
                profile_id="douyin",
                task_type="comment_collect",
                status=TaskStatus.RUNNING,
            )
        ]
    )
    resp = mxai_client.post(f"/api/plugins/mxai/queue/tasks/{tid}/pause")
    assert resp.status_code == 409


def test_queue_stop_and_retry_failed(mxai_client: TestClient) -> None:
    q = get_queue()
    tid = new_task_id()
    q.seed_in_memory(
        [
            Task(
                task_id=tid,
                name="失败",
                profile_id="douyin",
                task_type="comment_collect",
                status=TaskStatus.FAILED,
                fail_reason="err",
            )
        ]
    )
    mxai_client.post(f"/api/plugins/mxai/queue/tasks/{tid}/stop")
    retried = mxai_client.post("/api/plugins/mxai/queue/retry-failed").json()
    assert retried["retried"] >= 1
