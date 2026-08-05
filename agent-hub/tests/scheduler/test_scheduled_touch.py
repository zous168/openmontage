"""LT-018.04 Cron T6 定时触达."""

from __future__ import annotations

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.scheduler.benchmark_monitor import (
    is_scheduled_touch_due,
    run_scheduled_touch_enqueue,
)

# 配置变更清除 last_sent_date → tests/scheduler/test_single_touch_idempotency.py


def test_post_scheduled_msg_no_run_now(mxai_client: TestClient) -> None:
    QueueManager.reset()
    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/tasks/scheduled-msg",
        json={"recipient": "客户A", "message": "回访", "time": "10:00"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "scheduled"
    assert "task_id" not in res.json()


def test_trigger_scheduled_touch_enqueue(mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={
            "data": {
                "scheduler": {
                    "scheduled_touch": {
                        "enabled": True,
                        "time": "00:00",
                        "recipient": "客户B",
                        "message": "早安",
                    }
                }
            }
        },
    )
    mxai_client.post("/api/plugins/mxai/run/agents/wechat/start")
    result = run_scheduled_touch_enqueue("wechat", source="cron", operator="Cron")
    assert result.get("task_id") or result.get("skipped") in {
        "already_sent_today",
        "not_due_yet",
    }


def test_is_scheduled_touch_due() -> None:
    now = datetime(2026, 6, 25, 11, 0)
    assert is_scheduled_touch_due("10:30", now=now) is True
    assert is_scheduled_touch_due("12:00", now=now) is False
