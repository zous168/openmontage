"""CR-151 cron schedule expression builder tests."""

from __future__ import annotations

from plugins.mxai.scheduler.cron_schedule_expr import (
    benchmark_monitor_schedule,
    boss_greet_schedule,
    boss_proactive_dm_schedule,
    build_interval_window_cron,
    build_minute_scan_window_cron,
    comment_collect_schedule,
    first_comment_schedule,
    scheduled_touch_schedule,
)


def test_build_interval_window_cron_same_day() -> None:
    assert build_interval_window_cron(30, "09:00", "18:00") == "*/30 9-18 * * *"


def test_build_interval_window_cron_all_day() -> None:
    """全天窗 → cron 小时域 *."""
    assert build_interval_window_cron(40, "00:00", "23:59") == "*/40 * * * *"
    assert build_interval_window_cron(40, "00:00", "24:00") == "*/40 * * * *"


def test_build_minute_scan_window_cron() -> None:
    assert build_minute_scan_window_cron("09:00", "18:00") == "* 9-18 * * *"


def test_comment_collect_schedule_uses_collect_interval_and_window() -> None:
    wb = {
        "comment_collect": {
            "interval_minutes": 40,
            "run_window": {"start": "00:00", "end": "23:59"},
        },
    }
    assert comment_collect_schedule(wb) == "*/40 * * * *"


def test_comment_collect_schedule_falls_back_bm_interval() -> None:
    wb = {
        "comment_collect": {"run_window": {"start": "09:00", "end": "18:00"}},
        "scheduler": {"benchmark_monitor": {"interval_minutes": 30}},
    }
    assert comment_collect_schedule(wb) == "*/30 9-18 * * *"


def test_comment_reply_schedule_uses_reply_interval_and_window() -> None:
    from plugins.mxai.scheduler.cron_schedule_expr import comment_reply_schedule

    wb = {
        "comment_reply": {
            "interval_minutes": 30,
            "run_window": {"start": "09:00", "end": "18:00"},
        },
    }
    assert comment_reply_schedule(wb) == "*/30 9-18 * * *"


def test_comment_reply_schedule_without_window_falls_back_every() -> None:
    from plugins.mxai.scheduler.cron_schedule_expr import comment_reply_schedule

    wb = {"comment_reply": {"interval_minutes": 45}}
    assert comment_reply_schedule(wb) == "every 45m"


def test_benchmark_monitor_schedule_without_window_falls_back_every() -> None:
    wb = {"scheduler": {"benchmark_monitor": {"interval_minutes": 45}}}
    assert benchmark_monitor_schedule(wb) == "every 45m"


def test_benchmark_monitor_schedule_with_window() -> None:
    wb = {
        "comment_collect": {"run_window": {"start": "09:00", "end": "18:00"}},
        "scheduler": {"benchmark_monitor": {"interval_minutes": 30}},
    }
    assert benchmark_monitor_schedule(wb) == "*/30 9-18 * * *"


def test_benchmark_monitor_schedule_all_day() -> None:
    wb = {
        "comment_collect": {"run_window": {"start": "00:00", "end": "23:59"}},
        "scheduler": {"benchmark_monitor": {"interval_minutes": 40}},
    }
    assert benchmark_monitor_schedule(wb) == "*/40 * * * *"


def test_boss_greet_schedule_with_window() -> None:
    wb = {"boss": {"greet": {"run_window": {"start": "10:00", "end": "20:00"}}}}
    assert boss_greet_schedule(wb) == "* 10-20 * * *"


def test_boss_proactive_dm_schedule_with_window() -> None:
    wb = {"boss": {"proactive_dm": {"interval_minutes": 15, "run_window": {"start": "09:00", "end": "17:00"}}}}
    assert boss_proactive_dm_schedule(wb) == "*/15 9-17 * * *"


def test_first_comment_schedule_interval_window() -> None:
    wb = {
        "scheduler": {
            "first_comment": {
                "interval_minutes": 30,
                "run_window": {"start": "09:00", "end": "18:00"},
            }
        }
    }
    assert first_comment_schedule(wb) == "*/30 9-18 * * *"


def test_scheduled_touch_segmented_window_cron() -> None:
    wb = {
        "scheduler": {
            "scheduled_touch": {
                "mode": "segmented",
                "interval_minutes": 15,
                "run_window": {"start": "10:00", "end": "20:00"},
            }
        }
    }
    assert scheduled_touch_schedule(wb) == "*/15 10-20 * * *"


def test_boss_and_touch_all_day_cron() -> None:
    assert boss_greet_schedule(
        {"boss": {"greet": {"run_window": {"start": "00:00", "end": "23:59"}}}}
    ) == "* * * * *"
    assert boss_proactive_dm_schedule(
        {
            "boss": {
                "proactive_dm": {
                    "interval_minutes": 20,
                    "run_window": {"start": "00:00", "end": "23:59"},
                }
            }
        }
    ) == "*/20 * * * *"
    assert scheduled_touch_schedule(
        {
            "scheduler": {
                "scheduled_touch": {
                    "mode": "segmented",
                    "interval_minutes": 15,
                    "run_window": {"start": "00:00", "end": "23:59"},
                }
            }
        }
    ) == "*/15 * * * *"
