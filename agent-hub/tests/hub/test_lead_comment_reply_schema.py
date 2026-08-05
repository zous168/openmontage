"""LT-020.01.01 hub.db v8 Lead comment_reply 列."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.lead_service import (
    get_lead,
    record_comment_reply_success,
    save_leads,
    update_comment_reply_state,
)
from plugins.mxai.crm.storage.hub_repo import init_hub_schema
from plugins.mxai.rpa.types import CollectedComment


def _columns(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute("PRAGMA table_info(leads)").fetchall()
        return {str(r[1]) for r in rows}
    finally:
        conn.close()


def test_migration_adds_comment_reply_columns(tmp_path: Path) -> None:
    db = mxai_db_path("hub.db", tmp_path)
    init_hub_schema(db)
    cols = _columns(db)
    assert "comment_reply_count" in cols
    assert "comment_reply_status" in cols
    assert "comment_reply_at" in cols
    assert "platform_reply_comment_id" in cols


def test_insert_lead_default_count_zero(tmp_path: Path) -> None:
    db = mxai_db_path("hub.db", tmp_path)
    data_dir = tmp_path
    ids = save_leads(
        profile_id="douyin",
        source_channel="douyin",
        comments=[CollectedComment("c1", "u1", "多少钱", "v1", "kw")],
        data_dir=data_dir,
    )
    lead = get_lead(lead_id=ids[0], data_dir=data_dir)
    assert lead is not None
    assert int(lead["comment_reply_count"]) == 0
    assert lead["comment_reply_status"] == "none"


def test_update_increments_count_and_status(tmp_path: Path) -> None:
    db = mxai_db_path("hub.db", tmp_path)
    data_dir = tmp_path
    lead_id = save_leads(
        profile_id="douyin",
        source_channel="douyin",
        comments=[CollectedComment("c1", "u1", "咨询", "v1", "kw")],
        data_dir=data_dir,
    )[0]
    partial = record_comment_reply_success(
        lead_id,
        platform_reply_comment_id="rc_001",
        max_replies_per_lead=2,
        data_dir=data_dir,
    )
    assert partial["comment_reply_count"] == 1
    assert partial["comment_reply_status"] == "partial"
    sent = record_comment_reply_success(
        lead_id,
        platform_reply_comment_id="rc_002",
        max_replies_per_lead=2,
        data_dir=data_dir,
    )
    assert sent["comment_reply_count"] == 2
    assert sent["comment_reply_status"] == "sent"
    update_comment_reply_state(lead_id, status="failed", data_dir=data_dir)
    lead = get_lead(lead_id=lead_id, data_dir=data_dir)
    assert lead["comment_reply_status"] == "failed"
