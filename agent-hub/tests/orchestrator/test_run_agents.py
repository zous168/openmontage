"""分渠道启停（FR-RUN-02）与队列调度联动."""

from pathlib import Path

import pytest

from plugins.mxai.orchestrator.models import TaskStatus
from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_agent_enabled_blocks_drain(mxai_env: Path) -> None:
    del mxai_env
    QueueManager.reset()
    q = QueueManager.get()
    q.arm_work()
    q.set_agent_enabled("douyin", False)
    task = q.enqueue(
        profile_id="douyin",
        name="评论采集",
        task_type="comment_collect",
        skip_risk=True,
    )
    assert task.status == TaskStatus.QUEUED

    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    refreshed = q.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.status in {TaskStatus.RUNNING, TaskStatus.DONE, TaskStatus.FAILED}
    q.disable_all_agents()


def test_run_agents_status_reflects_enabled(mxai_env: Path) -> None:
    del mxai_env
    QueueManager.reset()
    q = QueueManager.get()
    q.disable_all_agents()
    assert q.agents_status()["agents"]["douyin"]["enabled"] is False
    q.set_agent_enabled("douyin", True)
    assert q.agents_status()["agents"]["douyin"]["enabled"] is True
    q.disable_all_agents()
    assert q.agents_status()["agents"]["douyin"]["enabled"] is False
