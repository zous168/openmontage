"""first_comment → WorkLog.op_object 须含「对标 · 正文」。"""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.orchestrator.models import Task, TaskStatus
from plugins.mxai.orchestrator.queue_manager import _worklog_op_object
from plugins.mxai.rpa_worker import automan_bridge as ab


def _task(payload: dict | None = None) -> Task:
    return Task(
        task_id="tsk_fc",
        profile_id="douyin",
        name="自动首评",
        task_type="first_comment",
        status=TaskStatus.RUNNING,
        payload=payload or {"benchmarks": ["xinhuashe"]},
    )


def test_op_object_from_posts() -> None:
    op = _worklog_op_object(
        _task(),
        {"posts": [{"benchmark": "xinhuashe", "text": "首评正文ABC"}]},
    )
    assert op.startswith("xinhuashe · ")
    assert "首评正文ABC" in op


def test_op_object_fallback_payload_benchmarks_and_text() -> None:
    op = _worklog_op_object(
        _task({"benchmarks": ["@bench"]}),
        {"huifu_msg": "引流话术"},
    )
    assert op == "@bench · 引流话术"


def test_from_result_normalizes_flat_first_comment() -> None:
    out = ab.from_result(
        "first_comment",
        {"benchmark": "xinhuashe", "text": "密密麻麻的血管"},
    )
    assert out["posts"][0]["benchmark"] == "xinhuashe"
    assert "密密麻麻" in out["posts"][0]["text"]


def test_queue_success_writes_worklog_op_object(
    mxai_env: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模拟 Automan 回 posts 后 Hub 台账应含对标与正文。"""
    import time

    from plugins.mxai.orchestrator.queue_manager import QueueManager
    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge, reset_rpa_worker_bridge
    from plugins.mxai.worklog.service import list_worklogs

    del mxai_env
    reset_rpa_worker_bridge()
    bridge = get_rpa_worker_bridge()
    monkeypatch.setattr(bridge, "is_connected", lambda: True)
    monkeypatch.setattr(
        bridge,
        "execute_via_worker",
        lambda task, timeout=600.0: {
            "posts": [
                {
                    "benchmark": "xinhuashe",
                    "text": "这密密麻麻的血管神经真的让人不敢轻易动刀",
                }
            ],
            "mode": "automan",
        },
    )
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    q.enqueue(
        profile_id="douyin",
        name="自动首评: xinhuashe",
        task_type="first_comment",
        payload={"benchmarks": ["xinhuashe"]},
        skip_risk=True,
    )
    time.sleep(0.4)
    logs = list_worklogs(profile_id="douyin", limit=5)
    hit = next(
        (
            log
            for log in logs
            if log.get("op_type") == "first_comment" and log.get("exec_status") == "成功"
            and "xinhuashe" in (log.get("op_object") or "")
        ),
        None,
    )
    assert hit is not None
    assert "密密麻麻" in (hit.get("op_object") or "")
