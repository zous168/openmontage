"""全渠道配置落盘门禁：时段 / 限额 / 风控."""

from __future__ import annotations

import pytest

from plugins.mxai.cfg.config_sanitize import sanitize_risk, sanitize_workbench_fields
from plugins.mxai.cfg.run_window import normalize_hhmm, require_hhmm
from plugins.mxai.cfg.workbench_scheduler import normalize_workbench


def test_normalize_hhmm_rejects_garbage() -> None:
    assert normalize_hhmm("明天上午") == ""
    assert normalize_hhmm("25:00") == ""
    assert normalize_hhmm("09:30") == "09:30"
    with pytest.raises(ValueError, match="HH:MM"):
        require_hhmm("明天上午", field="run_window.start")


def test_sanitize_workbench_run_window_and_limits() -> None:
    wb = sanitize_workbench_fields(
        {
            "comment_collect": {
                "run_window": {"start": "9:0", "end": "18:00"},
                "interval_minutes": 40,
                "max_videos_per_run": 10,
            },
            "dm": {"run_window": {"start": "09:00", "end": "21:00"}, "interval_sec": 6},
        },
        strict=True,
    )
    assert wb["comment_collect"]["run_window"] == {"start": "09:00", "end": "18:00"}
    assert wb["dm"]["interval_minutes"] == 30
    assert "interval_sec" not in wb["dm"]


def test_sanitize_workbench_rejects_bad_time_strict() -> None:
    with pytest.raises(ValueError, match="HH:MM"):
        sanitize_workbench_fields(
            {"add_friends": {"run_window": {"start": "上午", "end": "18:00"}}},
            strict=True,
        )


def test_sanitize_workbench_heals_bad_time_nonstrict() -> None:
    wb = sanitize_workbench_fields(
        {"batch_add": {"run_window": {"start": "坏", "end": "18:00"}}},
        strict=False,
    )
    assert wb["batch_add"]["run_window"]["start"] == ""
    assert wb["batch_add"]["run_window"]["end"] == ""


def test_sanitize_rejects_bad_max() -> None:
    with pytest.raises(ValueError, match="每轮视频上限"):
        sanitize_workbench_fields(
            {"comment_collect": {"max_videos_per_run": 0}},
            strict=True,
        )


def test_sanitize_rejects_empty_interval_named() -> None:
    with pytest.raises(ValueError, match="发送间隔不应为空"):
        sanitize_workbench_fields(
            {"boss": {"proactive_dm": {"interval_minutes": None}}},
            strict=True,
        )


def test_sanitize_rejects_empty_max_enqueue() -> None:
    with pytest.raises(ValueError, match="每轮入队上限不应为空"):
        sanitize_workbench_fields(
            {
                "scheduler": {
                    "scheduled_touch": {
                        "global_filters": {"max_enqueue_per_run": None},
                    }
                }
            },
            strict=True,
        )


def test_normalize_rejects_empty_silence_threshold() -> None:
    with pytest.raises(ValueError, match="静默时长不应为空"):
        normalize_workbench(
            {
                "scheduler": {
                    "scheduled_touch": {
                        "mode": "segmented",
                        "interval_minutes": 30,
                        "touch_subtasks": [
                            {
                                "id": "s1",
                                "enabled": True,
                                "threshold": {"days": None, "hours": 0, "minutes": 30},
                                "content_mode": "static",
                                "message": "hi",
                            }
                        ],
                    }
                }
            },
            channel_id="wechat",
            strict=True,
        )


def test_sanitize_risk_bounds() -> None:
    out = sanitize_risk({"daily_dm_limit": 80, "min_interval_sec": 5, "enabled": "true"}, strict=True)
    assert out["daily_dm_limit"] == 80
    assert out["enabled"] is True
    with pytest.raises(ValueError, match="daily_dm_limit"):
        sanitize_risk({"daily_dm_limit": -1}, strict=True)


def test_normalize_workbench_covers_public_and_boss() -> None:
    wb = normalize_workbench(
        {
            "comment_reply": {
                "run_window": {"start": "10:00", "end": "20:00"},
                "interval_minutes": 30,
                "max_comments_per_run": 20,
            },
            "boss": {
                "greet": {"run_window": {"start": "09:00", "end": "18:00"}},
                "greet_plans": [{"zhiwei": "前端", "enqueue_at": "10:00,11:00", "new_number": 5}],
            },
        },
        channel_id="boss",
        strict=True,
    )
    assert wb["comment_reply"]["run_window"]["start"] == "10:00"
    assert [p["enqueue_at"] for p in wb["boss"]["greet_plans"]] == ["10:00", "11:00"]


def test_sanitize_moments_strips_base64_and_heals() -> None:
    wb = sanitize_workbench_fields(
        {
            "moments": {
                "enabled": "true",
                "days": {
                    "2026-08-01": [
                        {
                            "id": "m1",
                            "content": "hello",
                            "mode": "bad",
                            "status": "nope",
                            "time": "8:0",
                            "visibility": "public",
                            "image_refs": [
                                {"name": "a.jpg", "size": 12, "data": "data:image/png;base64," + ("x" * 600)},
                                {"name": "data:evil", "size": 1},
                            ],
                        },
                        {
                            "id": "m2",
                            "content": "later",
                            "mode": "text",
                            "status": "scheduled",
                            "time": "09:00",
                        },
                    ],
                    "bad-key": [{"id": "x"}],
                },
            }
        },
        strict=False,
    )
    moments = wb["moments"]
    assert moments["enabled"] is True
    assert "bad-key" not in moments["days"]
    day = moments["days"]["2026-08-01"]
    assert day[0]["id"] == "m1"
    assert day[0]["mode"] == "image"
    assert day[0]["status"] == "draft"
    assert day[0]["time"] == "08:00"
    assert day[0]["image_refs"] == [{"name": "a.jpg", "size": 12}]
    assert "data" not in day[0]["image_refs"][0]
    assert day[0]["retry_count"] == 0
    assert day[1]["id"] == "m2"
    assert day[1]["time"] == "09:00"


def test_sanitize_moments_keeps_material_id_and_retry() -> None:
    wb = sanitize_workbench_fields(
        {
            "moments": {
                "enabled": True,
                "days": {
                    "2026-08-01": [
                        {
                            "id": "m3",
                            "content": "pic",
                            "mode": "image",
                            "status": "scheduled",
                            "time": "10:00",
                            "visibility": "public",
                            "retry_count": 2,
                            "next_attempt_at": "2026-08-01T10:05:00",
                            "image_refs": [
                                {
                                    "name": "a.jpg",
                                    "size": 3,
                                    "material_id": 99,
                                    "path": "D:/mat/a.jpg",
                                }
                            ],
                        }
                    ]
                },
            }
        },
        strict=False,
    )
    item = wb["moments"]["days"]["2026-08-01"][0]
    assert item["retry_count"] == 2
    assert item["next_attempt_at"] == "2026-08-01T10:05:00"
    assert item["image_refs"][0]["material_id"] == 99
    assert item["image_refs"][0]["path"] == "D:/mat/a.jpg"


def test_sanitize_moments_rejects_long_content_strict() -> None:
    with pytest.raises(ValueError, match="2000"):
        sanitize_workbench_fields(
            {
                "moments": {
                    "enabled": True,
                    "days": {
                        "2026-08-01": [
                            {"id": "m1", "content": "字" * 2001, "mode": "text", "status": "draft", "time": "10:00"},
                        ]
                    },
                }
            },
            strict=True,
        )
