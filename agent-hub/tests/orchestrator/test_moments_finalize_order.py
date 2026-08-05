"""CR-168 §15 · finalize 返回值与成功路径语义（Q1–Q3）."""

from __future__ import annotations

from unittest.mock import patch

from plugins.mxai.orchestrator.models import Task, new_task_id
from plugins.mxai.orchestrator.queue_manager import (
    _finalize_moments_publish,
    _revert_moments_calendar_scheduled,
)


def _moments_task() -> Task:
    return Task(
        task_id=new_task_id(),
        profile_id="wechat",
        name="发朋友圈",
        task_type="moments_publish",
        payload={"moments_id": "m1", "date": "2026-08-06"},
    )


def test_finalize_wrapper_returns_false_when_not_ok() -> None:
    task = _moments_task()
    with patch(
        "plugins.mxai.scheduler.moments_cron.finalize_moments_publish",
        return_value={"ok": False, "error": "item_not_found"},
    ):
        assert _finalize_moments_publish(task, success=True) is False


def test_finalize_wrapper_returns_true_on_ok() -> None:
    task = _moments_task()
    with patch(
        "plugins.mxai.scheduler.moments_cron.finalize_moments_publish",
        return_value={"ok": True, "status": "done"},
    ):
        assert _finalize_moments_publish(task, success=True) is True


def test_finalize_wrapper_non_moments_is_noop_true() -> None:
    task = _moments_task()
    task.task_type = "dm_send"
    assert _finalize_moments_publish(task, success=True) is True


def test_revert_calls_scheduled(monkeypatch) -> None:
    calls: list[object] = []

    def fake_revert(task):
        calls.append(task)

    monkeypatch.setattr(
        "plugins.mxai.scheduler.moments_cron.revert_moments_to_scheduled",
        fake_revert,
    )
    task = _moments_task()
    _revert_moments_calendar_scheduled(task)
    assert calls == [task]
