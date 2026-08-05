"""CR-133 · insert_comment_lead：去重 / 传入意向 / 渠道隔离 / v14 迁移."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.funnel import intent_to_stage
from plugins.mxai.crm.lead_service import insert_comment_lead, list_leads
from plugins.mxai.crm.storage.hub_repo import init_hub_schema


def test_insert_new_comment_lead(tmp_path: Path) -> None:
    r = insert_comment_lead(
        profile_id="douyin", nickname="小王", douyin_id="dy_001",
        comment="价格多少", intent="高", data_dir=tmp_path,
    )
    assert r["inserted"] and not r["skipped"]
    leads = list_leads(profile_id="douyin", data_dir=tmp_path)
    assert len(leads) == 1
    l = leads[0]
    assert l["author"] == "小王"
    assert l["douyin_id"] == "dy_001"
    assert l["source_comment"] == "价格多少"
    assert l["intent_level"] == "高"
    # funnel_stage 由意向派生（沿用 save_leads 的 intent_to_stage），非固定 comment_lead
    assert l["funnel_stage"] == intent_to_stage("高")
    assert l["dm_touch_status"] == "not_sent"


def test_dedup_skips_duplicate_douyin_id(tmp_path: Path) -> None:
    insert_comment_lead(
        profile_id="douyin", nickname="小王", douyin_id="dy_001",
        comment="a", intent="高", data_dir=tmp_path,
    )
    r2 = insert_comment_lead(
        profile_id="douyin", nickname="小王改", douyin_id="dy_001",
        comment="b", intent="低", data_dir=tmp_path,
    )
    assert r2["skipped"] and r2["reason"] == "duplicate_douyin_id"
    # 仍只有 1 条，且是首次入库的内容（去重跳过、不覆盖）
    leads = list_leads(profile_id="douyin", data_dir=tmp_path)
    assert len(leads) == 1 and leads[0]["source_comment"] == "a"


def test_intent_is_passed_in_not_guessed(tmp_path: Path) -> None:
    # 评论无价格类词，_guess_intent 会猜「低」；但传入「高」应原样落库
    insert_comment_lead(
        profile_id="douyin", nickname="x", douyin_id="dy_x",
        comment="随便说说", intent="高", data_dir=tmp_path,
    )
    assert list_leads(profile_id="douyin", data_dir=tmp_path)[0]["intent_level"] == "高"


def test_channel_isolation_same_douyin_id(tmp_path: Path) -> None:
    insert_comment_lead(
        profile_id="douyin", nickname="a", douyin_id="shared",
        comment="c", intent="中", data_dir=tmp_path,
    )
    r = insert_comment_lead(
        profile_id="xiaohongshu", nickname="b", douyin_id="shared",
        comment="c", intent="中", data_dir=tmp_path,
    )
    assert r["inserted"]  # 不同渠道同 id 各存一份
    assert len(list_leads(profile_id="douyin", data_dir=tmp_path)) == 1
    assert len(list_leads(profile_id="xiaohongshu", data_dir=tmp_path)) == 1


def test_missing_douyin_id_raises(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        insert_comment_lead(
            profile_id="douyin", nickname="x", douyin_id="  ",
            comment="c", intent="高", data_dir=tmp_path,
        )


def test_time_iso_passed_through(tmp_path: Path) -> None:
    insert_comment_lead(
        profile_id="douyin", nickname="x", douyin_id="dy_t",
        comment="c", intent="高", time_iso="2026-07-05T01:02:03+00:00",
        data_dir=tmp_path,
    )
    assert list_leads(profile_id="douyin", data_dir=tmp_path)[0]["created_at"] == "2026-07-05T01:02:03+00:00"


def test_migration_v14_adds_douyin_id_column(tmp_path: Path) -> None:
    db = mxai_db_path("hub.db", tmp_path)
    init_hub_schema(db)
    conn = sqlite3.connect(db)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(douyin_leads)")}
    finally:
        conn.close()
    assert "douyin_id" in cols


def test_migration_v15_adds_dm_touch_status(tmp_path: Path) -> None:
    db = mxai_db_path("hub.db", tmp_path)
    init_hub_schema(db)
    conn = sqlite3.connect(db)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(douyin_leads)")}
        assert "dm_touch_status" in cols
        insert_comment_lead(
            profile_id="douyin", nickname="x", douyin_id="dy_m",
            comment="c", intent="高", data_dir=tmp_path,
        )
        row = conn.execute(
            "SELECT dm_touch_status FROM douyin_leads WHERE douyin_id = 'dy_m'",
        ).fetchone()
        assert row[0] == "not_sent"
    finally:
        conn.close()
