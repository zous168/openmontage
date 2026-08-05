"""CR-169 · 客户视频评论日上限（风控 SSOT，非工作台字段）。"""

from __future__ import annotations

import pytest

from plugins.mxai.risk.engine import check_enqueue


def test_daily_video_comment_limit_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.risk.engine._load_risk",
        lambda _pid: {"enabled": True, "daily_video_comment_limit": 5},
    )
    monkeypatch.setattr(
        "plugins.mxai.risk.engine.count_success_today",
        lambda *_a, **_k: 5,
    )
    r = check_enqueue("douyin", "video_comment")
    assert not r.allowed
    assert "daily_video_comment_limit" in r.reason


def test_zero_limit_means_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.risk.engine._load_risk",
        lambda _pid: {"enabled": True, "daily_video_comment_limit": 0},
    )
    monkeypatch.setattr(
        "plugins.mxai.risk.engine.count_success_today",
        lambda *_a, **_k: 999,
    )
    assert check_enqueue("douyin", "video_comment").allowed


def test_counts_only_video_comment_op_type(monkeypatch: pytest.MonkeyPatch) -> None:
    """日上限只数 video_comment，不与私信/首评互相挤占。"""
    seen: list[list[str]] = []

    def _count(_pid: str, op_types: list[str], **_k: object) -> int:
        seen.append(list(op_types))
        return 0

    monkeypatch.setattr(
        "plugins.mxai.risk.engine._load_risk",
        lambda _pid: {"enabled": True, "daily_video_comment_limit": 3},
    )
    monkeypatch.setattr("plugins.mxai.risk.engine.count_success_today", _count)
    check_enqueue("douyin", "video_comment")
    assert ["video_comment"] in seen
