"""CR-168 阶段2 · 朋友圈拣选 / 过期跳过 / schedule ISO."""

from __future__ import annotations

from datetime import datetime

from core.timeutil import BEIJING
from cron.jobs import parse_schedule
from plugins.mxai.scheduler.cron_schedule_expr import moments_schedule
from plugins.mxai.scheduler.moments_cron import (
    classify_due,
    has_inflight_moments,
    moments_once_schedule_iso,
    pick_next_scheduled,
    plan_skip_and_pick,
)


def _moments(**days_map):
    return {"enabled": True, "days": dict(days_map)}


def test_pick_next_sorts_by_publish_at() -> None:
    moments = _moments(
        **{
            "2026-08-03": [
                {"id": "b", "time": "09:00", "status": "scheduled", "mode": "text", "content": "b"},
            ],
            "2026-08-01": [
                {"id": "a2", "time": "10:00", "status": "scheduled", "mode": "text", "content": "a2"},
                {"id": "a1", "time": "08:00", "status": "scheduled", "mode": "text", "content": "a1"},
            ],
        }
    )
    row = pick_next_scheduled(moments)
    assert row is not None
    assert row["id"] == "a1"
    assert row["date"] == "2026-08-01"


def test_plan_overdue_chain_then_not_due() -> None:
    now = datetime(2026, 8, 2, 12, 0, 0, tzinfo=BEIJING)
    moments = _moments(
        **{
            "2026-08-01": [
                {"id": "old1", "time": "08:00", "status": "scheduled", "mode": "text", "content": "1"},
                {"id": "old2", "time": "09:00", "status": "scheduled", "mode": "text", "content": "2"},
            ],
            "2026-08-05": [
                {"id": "future", "time": "10:00", "status": "scheduled", "mode": "text", "content": "f"},
            ],
        }
    )
    plan = plan_skip_and_pick(moments, now=now)
    assert plan["action"] == "not_due"
    assert len(plan["skips"]) == 2
    assert {s["id"] for s in plan["skips"]} == {"old1", "old2"}
    assert plan["target"]["id"] == "future"


def test_plan_due_enqueue() -> None:
    now = datetime(2026, 8, 1, 8, 0, 30, tzinfo=BEIJING)
    moments = _moments(
        **{
            "2026-08-01": [
                {"id": "due1", "time": "08:00", "status": "scheduled", "mode": "text", "content": "x"},
            ],
        }
    )
    plan = plan_skip_and_pick(moments, now=now)
    assert plan["action"] == "enqueue"
    assert plan["target"]["id"] == "due1"
    assert classify_due(plan["target"]["publish_at"], now=now) == "due"


def test_plan_inflight() -> None:
    moments = _moments(
        **{
            "2026-08-01": [
                {"id": "q1", "time": "08:00", "status": "queued", "mode": "text", "content": "x"},
                {"id": "s1", "time": "09:00", "status": "scheduled", "mode": "text", "content": "y"},
            ],
        }
    )
    assert has_inflight_moments(moments) is True
    plan = plan_skip_and_pick(moments)
    assert plan["action"] == "inflight"


def test_moments_schedule_once_parseable() -> None:
    wb = {
        "moments": _moments(
            **{
                "2026-08-01": [
                    {"id": "a", "time": "08:00", "status": "scheduled", "mode": "text", "content": "x"},
                ],
            }
        )
    }
    iso = moments_once_schedule_iso(wb["moments"])
    assert iso == "2026-08-01T08:00:00"
    assert moments_schedule(wb) == iso
    parsed = parse_schedule(iso)
    assert parsed["kind"] == "once"
