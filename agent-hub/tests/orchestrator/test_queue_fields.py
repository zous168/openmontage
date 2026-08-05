"""LT-017.01.02：priority_label · execution_seq · drain 后台线程."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from plugins.mxai.orchestrator.models import Task, TaskStatus, new_task_id, priority_label_for
from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_priority_label_for_inbound_reply() -> None:
    assert priority_label_for(1) == "P1·客服应答"


def test_to_api_dict_priority_label() -> None:
    task = Task(
        task_id=new_task_id(),
        name="客服",
        profile_id="douyin",
        task_type="inbound_reply",
        priority=1,
    )
    body = task.to_api_dict()
    assert body["priority_label"] == "P1·客服应答"


def test_list_tasks_execution_seq(mxai_env: Path) -> None:
    del mxai_env
    q = QueueManager.get()
    q.set_global_pause(True)
    q.set_agent_enabled("douyin", True)
    t1 = Task(
        task_id=new_task_id(),
        name="采集",
        profile_id="douyin",
        task_type="comment_collect",
        priority=3,
        status=TaskStatus.QUEUED,
        created_at=100.0,
    )
    t2 = Task(
        task_id=new_task_id(),
        name="客服",
        profile_id="douyin",
        task_type="inbound_reply",
        priority=1,
        status=TaskStatus.QUEUED,
        created_at=200.0,
    )
    q.seed_in_memory([t1, t2])
    items = q.list_tasks(status="排队中")["items"]
    # 列表：入队时间新→旧；execution_seq：仍按 P 档出队序
    assert [x["task_id"] for x in items] == [t2.task_id, t1.task_id]
    by_id = {x["task_id"]: x for x in items}
    assert by_id[t2.task_id]["execution_seq"] == 1
    assert by_id[t1.task_id]["execution_seq"] == 2


def test_list_tasks_newest_created_first(mxai_env: Path) -> None:
    """列表面板按 created_at 降序，不受 P 档影响。"""
    del mxai_env
    q = QueueManager.get()
    q.set_global_pause(True)
    older_p1 = Task(
        task_id=new_task_id(),
        name="旧·P1",
        profile_id="wechat",
        task_type="inbound_reply",
        priority=1,
        status=TaskStatus.QUEUED,
        created_at=100.0,
    )
    newer_p3 = Task(
        task_id=new_task_id(),
        name="新·P3",
        profile_id="douyin",
        task_type="comment_collect",
        priority=3,
        status=TaskStatus.QUEUED,
        created_at=300.0,
    )
    mid_p2 = Task(
        task_id=new_task_id(),
        name="中·P2",
        profile_id="boss",
        task_type="dm",
        priority=2,
        status=TaskStatus.QUEUED,
        created_at=200.0,
    )
    q.seed_in_memory([older_p1, newer_p3, mid_p2])
    ids = [x["task_id"] for x in q.list_tasks()["items"]]
    assert ids == [newer_p3.task_id, mid_p2.task_id, older_p1.task_id]


def test_drain_submits_background_thread(
    mxai_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del mxai_env
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    started = threading.Event()
    released = threading.Event()

    def slow_handler(task: Task) -> dict:
        started.set()
        released.wait(timeout=2)
        return {"ok": True}

    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge
    _b = get_rpa_worker_bridge()
    monkeypatch.setattr(_b, "is_connected", lambda: True)
    monkeypatch.setattr(_b, "execute_via_worker", lambda task, timeout=600.0: slow_handler(task))
    task = Task(
        task_id=new_task_id(),
        name="慢任务",
        profile_id="douyin",
        task_type="comment_collect",
        status=TaskStatus.QUEUED,
    )
    q.seed_in_memory([task])
    assert started.wait(timeout=2)
    with q._mutex:
        assert q._rpa_holder == task.task_id
    released.set()
    time.sleep(0.2)
    finished = q.get_task(task.task_id)
    assert finished is not None
    assert finished.status == TaskStatus.DONE
