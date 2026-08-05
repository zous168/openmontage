"""CR-169 D6/D7 · 统计口径：核心卡合并、目标环单列。"""

from __future__ import annotations

from plugins.mxai.api.agents import METRIC_OP_TYPES
from plugins.mxai.stats.service import _core_metrics, core_rule_by_label


def test_core_card_merges_video_comment_into_ai_reply() -> None:
    """D7：不单列卡片，客户视频评论并入「AI 评论回复」计数。"""
    assert core_rule_by_label("客户视频评论发送") is None  # 独立卡已移除

    rule = core_rule_by_label("AI 评论回复")
    assert rule is not None
    assert "video_comment" in rule[1]
    assert "comment_reply" in rule[1]

    rows = [
        {"profile_id": "douyin", "op_type": "comment_reply"},
        {"profile_id": "douyin", "op_type": "comment_reply"},
        {"profile_id": "douyin", "op_type": "video_comment"},
        {"profile_id": "xiaohongshu", "op_type": "comment_reply"},
    ]
    card = {c["label"]: c for c in _core_metrics(rows)}["AI 评论回复"]
    assert card["value"] == 4  # 3 抖音（含 1 条视频评论）+ 1 小红书
    by_agent = {a["profile_id"]: a["value"] for a in card.get("by_agent") or []}
    assert by_agent.get("douyin") == 3


def test_goal_ring_keeps_video_comment_separate() -> None:
    """D6：目标环是独立指标，不与 AI 评论回复混算。"""
    douyin = METRIC_OP_TYPES["douyin"]
    assert douyin["客户视频评论"] == ["video_comment", "客户视频评论"]
    # 「AI 评论回复」环仍只算评论回复，不含 video_comment（与卡片口径有意不同）
    assert "video_comment" not in douyin["AI 评论回复"]
    # 仅抖音有该指标
    assert "客户视频评论" not in METRIC_OP_TYPES.get("xiaohongshu", {})
    assert "客户视频评论" not in METRIC_OP_TYPES.get("shipinhao", {})
