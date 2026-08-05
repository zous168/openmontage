"""CR-169 · 客户视频评论独立 cron（不搭 benchmark_monitor 便车）。"""

from __future__ import annotations

import pytest

from plugins.mxai.scheduler.cron import (
    _feature_config_allows,
    video_comment_job_id,
    video_comment_job_name,
)
from plugins.mxai.scheduler.cron_schedule_expr import video_comment_schedule


def test_job_id_and_name() -> None:
    assert video_comment_job_id("douyin") == "mxai-douyin-video_comment"
    assert video_comment_job_name("douyin") == "抖音·客户视频评论"


def test_schedule_uses_own_window_not_collect_window() -> None:
    """时段必须取 video_comment 自己的 run_window（审查发现：曾取采集时段）。"""
    wb = {
        "comment_collect": {"run_window": {"start": "09:00", "end": "18:00"}},
        "video_comment": {
            "interval_minutes": 30,
            "run_window": {"start": "19:00", "end": "21:00"},
        },
    }
    expr = video_comment_schedule(wb)
    assert "19" in expr and "21" in expr
    assert "9-18" not in expr


def test_schedule_falls_back_to_interval_without_window() -> None:
    assert video_comment_schedule({"video_comment": {"interval_minutes": 45}}) == "every 45m"


@pytest.mark.parametrize(
    "wb,expected",
    [
        ({"video_comment": {"auto_enabled": True}}, True),
        ({"video_comment": {"auto_enabled": False}}, False),
        # D-b：正文一律 AI 生成，无话术可配 → 不再因话术为空而拦
        ({"video_comment": {"auto_enabled": True, "message": "  "}}, True),
        ({}, False),
    ],
)
def test_g3_gate_needs_switch_only(wb: dict, expected: bool) -> None:
    assert _feature_config_allows("douyin", "video_comment", wb) is expected


def test_g3_gate_rejects_non_douyin() -> None:
    wb = {"video_comment": {"auto_enabled": True}}
    assert _feature_config_allows("xiaohongshu", "video_comment", wb) is False


def test_benchmark_round_no_longer_enqueues_video_comment() -> None:
    """审查发现的重复入队：bootstrap 会经 benchmark_round + 直调各来一次。"""
    from pathlib import Path

    src = Path("src/plugins/mxai/scheduler/benchmark_monitor.py").read_text(encoding="utf-8")
    assert "bootstrap_video_comment(" not in src, "benchmark_monitor 不应再入队 video_comment"


def test_cron_kind_registered_for_records() -> None:
    from plugins.mxai.api.cron import _KIND_LABELS, _RECORD_KINDS

    assert "video_comment" in _RECORD_KINDS
    assert _KIND_LABELS["video_comment"] == "客户视频评论"
