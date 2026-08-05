"""Boss greet_plans 数据安全：多时刻拆分 / 非法时刻拒绝 / workbench 落盘门禁."""

from __future__ import annotations

import pytest

from plugins.mxai.cfg.boss_greet_plans import (
    sanitize_greet_plans,
    sanitize_workbench_greet_plans,
)
from plugins.mxai.cfg.workbench_scheduler import normalize_workbench


def test_sanitize_expands_multi_enqueue_at() -> None:
    plans = sanitize_greet_plans(
        [{"zhiwei": "开发工程师", "enqueue_at": "10:00,11:30", "new_number": 10}],
        strict=True,
    )
    assert [p["enqueue_at"] for p in plans] == ["10:00", "11:30"]
    assert all("," not in p["enqueue_at"] for p in plans)
    assert plans[0]["id"] != plans[1]["id"]


def test_sanitize_rejects_invalid_enqueue_at() -> None:
    with pytest.raises(ValueError, match="非法入队时刻"):
        sanitize_greet_plans(
            [{"zhiwei": "开发工程师", "enqueue_at": "明天上午", "new_number": 10}],
            strict=True,
        )


def test_sanitize_accepts_yaml_sexagesimal_enqueue_at() -> None:
    """YAML 1.1：未加引号的 10:00 会被读成整数 600。"""
    plans = sanitize_greet_plans(
        [{"zhiwei": "开发工程师", "enqueue_at": 600, "new_number": 10}],
        strict=True,
    )
    assert [p["enqueue_at"] for p in plans] == ["10:00"]


def test_sanitize_rejects_bad_new_number() -> None:
    with pytest.raises(ValueError, match="打招呼数量"):
        sanitize_greet_plans(
            [{"zhiwei": "开发工程师", "enqueue_at": "09:00", "new_number": "x"}],
            strict=True,
        )


def test_sanitize_rejects_empty_new_number() -> None:
    with pytest.raises(ValueError, match="打招呼数量不应为空"):
        sanitize_greet_plans(
            [{"zhiwei": "开发工程师", "enqueue_at": "09:00", "new_number": None}],
            strict=True,
        )


def test_normalize_workbench_heals_boss_greet_plans() -> None:
    wb = normalize_workbench(
        {
            "boss": {
                "greet_plans": [
                    {
                        "id": "gp1",
                        "zhiwei": "开发工程师",
                        "enqueue_at": "10 11:30",
                        "new_number": 8,
                        "zhize": "",
                    }
                ]
            }
        },
        channel_id="boss",
    )
    plans = wb["boss"]["greet_plans"]
    assert sorted(p["enqueue_at"] for p in plans) == ["10:00", "11:30"]


def test_sanitize_workbench_passthrough_non_boss() -> None:
    wb = {"comment_collect": {"enabled": True}}
    assert sanitize_workbench_greet_plans(wb)["comment_collect"]["enabled"] is True
