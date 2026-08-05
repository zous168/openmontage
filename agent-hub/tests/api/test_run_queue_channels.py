"""分渠道启停 × 全局队列暂停 × 任务出队 — REST 集成验收."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.api.deps import get_queue
from plugins.mxai.orchestrator.models import TaskStatus


def _enqueue_douyin_comment(skip_risk: bool = True):
    q = get_queue()
    return q.enqueue(
        profile_id="douyin",
        name="评论采集验收",
        task_type="comment_collect",
        payload={"keywords": ["测试"]},
        skip_risk=skip_risk,
    )


def test_assistant_run_control_rejected(mxai_client: TestClient) -> None:
    res = mxai_client.post("/api/plugins/mxai/run/agents/assistant/pause")
    assert res.status_code == 400
    assert "no RPA run control" in res.json()["detail"]


def test_run_agents_reflects_per_channel_toggle(mxai_client: TestClient) -> None:
    start = mxai_client.post("/api/plugins/mxai/run/agents/douyin/start")
    assert start.status_code == 200
    assert start.json()["enabled"] is True

    pause = mxai_client.post("/api/plugins/mxai/run/agents/douyin/pause")
    assert pause.status_code == 200
    assert pause.json()["enabled"] is False

    agents = mxai_client.get("/api/plugins/mxai/run/agents").json()["agents"]
    assert agents["douyin"]["enabled"] is False
    assert agents["wechat"]["enabled"] is False


def test_channel_start_does_not_clear_global_pause(mxai_client: TestClient) -> None:
    mxai_client.post("/api/plugins/mxai/queue/pause")
    mxai_client.post("/api/plugins/mxai/run/agents/douyin/start")
    summary = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary["paused"] is True


def test_disabled_channel_keeps_task_queued(mxai_client: TestClient) -> None:
    mxai_client.post("/api/plugins/mxai/queue/resume")
    mxai_client.post("/api/plugins/mxai/run/agents/douyin/pause")

    task = _enqueue_douyin_comment()
    assert task.status == TaskStatus.QUEUED

    summary = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary["paused"] is False
    assert summary["queued"] >= 1
    assert summary["running"] == 0


def test_enabled_channel_drains_after_global_resume(mxai_client: TestClient) -> None:
    mxai_client.post("/api/plugins/mxai/queue/pause")
    mxai_client.post("/api/plugins/mxai/run/agents/douyin/pause")

    task = _enqueue_douyin_comment()
    assert task.status == TaskStatus.QUEUED

    mxai_client.post("/api/plugins/mxai/run/agents/douyin/start")
    mxai_client.post("/api/plugins/mxai/queue/resume")

    import time

    deadline = time.time() + 5.0
    final = task
    while time.time() < deadline:
        refreshed = get_queue().get_task(task.task_id)
        assert refreshed is not None
        final = refreshed
        if final.status in {TaskStatus.DONE, TaskStatus.FAILED}:
            break
        time.sleep(0.05)

    assert final.status in {TaskStatus.DONE, TaskStatus.FAILED}
    summary = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary["paused"] is False


def test_global_pause_blocks_drain_with_enabled_channel(mxai_client: TestClient) -> None:
    mxai_client.post("/api/plugins/mxai/run/agents/douyin/start")
    mxai_client.post("/api/plugins/mxai/queue/pause")

    task = _enqueue_douyin_comment()
    assert task.status == TaskStatus.QUEUED

    summary = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary["paused"] is True
    assert summary["queued"] >= 1
