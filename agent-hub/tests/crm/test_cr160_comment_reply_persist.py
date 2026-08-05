"""CR-160 · comment_reply 成功后写入 leads."""

from __future__ import annotations

from pathlib import Path

from plugins.mxai.crm.lead_service import (
    extract_comment_reply_results,
    get_lead,
    insert_comment_lead,
    list_leads,
    persist_comment_replies_from_result,
)
from plugins.mxai.rpa_worker.automan_bridge import from_result


def test_extract_results_list() -> None:
    items = extract_comment_reply_results(
        {
            "results": [
                {
                    "author": "小王",
                    "douyin_id": "dy_1",
                    "question": "价格多少",
                    "reply": {"text": "私聊报价"},
                },
                {"author": "空评论", "reply": {"text": "x"}},  # 无 comment → 跳过
            ]
        }
    )
    assert len(items) == 1
    assert items[0]["douyin_id"] == "dy_1"
    assert items[0]["comment"] == "价格多少"
    assert items[0]["reply_text"] == "私聊报价"


def test_extract_synthetic_douyin_id() -> None:
    items = extract_comment_reply_results(
        {
            "results": [
                {"author": "小美", "comment": "求联系", "reply_text": "好的"},
            ]
        }
    )
    assert len(items) == 1
    assert items[0]["douyin_id"].startswith("rpa:")


def test_from_result_normalizes_flat_comment_reply() -> None:
    out = from_result(
        "comment_reply",
        {
            "author": "老王",
            "comment": "怎么收费",
            "reply": "欢迎私信",
            "douyin_id": "dy_9",
        },
    )
    assert isinstance(out["results"], list) and len(out["results"]) == 1
    assert out["results"][0]["douyin_id"] == "dy_9"


def test_persist_inserts_and_marks_reply(tmp_path: Path) -> None:
    persisted = persist_comment_replies_from_result(
        "douyin",
        {
            "results": [
                {
                    "author": "小王",
                    "douyin_id": "dy_cr160",
                    "question": "套餐多少钱",
                    "reply": {"text": "稍后发您"},
                }
            ]
        },
        max_replies_per_lead=1,
        data_dir=tmp_path,
    )
    assert len(persisted) == 1
    assert persisted[0]["inserted"] is True
    lead = get_lead(lead_id=persisted[0]["lead_id"], data_dir=tmp_path)
    assert lead is not None
    assert lead["author"] == "小王"
    assert lead["source_comment"] == "套餐多少钱"
    assert lead["comment_reply_status"] == "sent"
    assert int(lead["comment_reply_count"]) == 1


def test_persist_dedup_updates_existing(tmp_path: Path) -> None:
    insert_comment_lead(
        profile_id="douyin",
        nickname="小王",
        douyin_id="dy_exist",
        comment="旧评论",
        intent="高",
        data_dir=tmp_path,
    )
    persisted = persist_comment_replies_from_result(
        "douyin",
        {
            "results": [
                {
                    "author": "小王",
                    "douyin_id": "dy_exist",
                    "comment": "新评论不会覆盖正文",
                    "reply_text": "已回复",
                }
            ]
        },
        max_replies_per_lead=2,
        data_dir=tmp_path,
    )
    assert len(persisted) == 1
    assert persisted[0]["skipped_dup"] is True
    assert persisted[0]["comment_reply_status"] == "partial"
    leads = list_leads(profile_id="douyin", data_dir=tmp_path)
    assert len(leads) == 1
    assert leads[0]["source_comment"] == "旧评论"


def test_persist_skips_empty_comment(tmp_path: Path) -> None:
    persisted = persist_comment_replies_from_result(
        "douyin",
        {"results": [{"author": "x", "reply": {"text": "y"}}]},
        data_dir=tmp_path,
    )
    assert persisted == []
    assert list_leads(profile_id="douyin", data_dir=tmp_path) == []
