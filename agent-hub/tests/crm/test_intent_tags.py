"""评论意向细标签：落库原文 + 门闸归一."""

from __future__ import annotations

from pathlib import Path

from plugins.mxai.cfg.comment_reply import intent_meets_threshold
from plugins.mxai.crm.funnel import canonicalize_intent_level, intent_to_stage
from plugins.mxai.crm.lead_service import insert_comment_lead, list_leads


def test_canonicalize_fine_tags() -> None:
    assert canonicalize_intent_level("询价") == "高"
    assert canonicalize_intent_level("跟做") == "中"
    assert canonicalize_intent_level("buy") == "高"
    assert canonicalize_intent_level("learn") == "中"
    assert canonicalize_intent_level("高") == "高"
    assert canonicalize_intent_level("闲聊") == "低"


def test_intent_to_stage_fine_tags() -> None:
    assert intent_to_stage("询价") == "intent_qualified"
    assert intent_to_stage("跟做") == "intent_qualified"
    assert intent_to_stage("低") == "comment_lead"


def test_threshold_accepts_fine_tags() -> None:
    assert intent_meets_threshold("询价", "high")
    assert intent_meets_threshold("跟做", "high_and_medium")
    assert not intent_meets_threshold("跟做", "high")
    assert intent_meets_threshold("buy", "medium")


def test_insert_keeps_fine_tag_text(tmp_path: Path) -> None:
    insert_comment_lead(
        profile_id="douyin",
        nickname="小王",
        douyin_id="dy_tag_1",
        comment="多少钱",
        intent="询价",
        data_dir=tmp_path,
    )
    lead = list_leads(profile_id="douyin", data_dir=tmp_path)[0]
    assert lead["intent_level"] == "询价"
    assert lead["funnel_stage"] == "intent_qualified"
