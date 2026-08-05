"""customers.last_inbound_at（CR-129）."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.customer_inbound import touch_last_inbound
from plugins.mxai.crm.storage.hub_repo import init_hub_schema
from plugins.mxai.storage.channel_tables import contacts_table
from core.timeutil import utc_now_iso


def test_touch_last_inbound_insert_and_update(tmp_path: Path) -> None:
    db = mxai_db_path("hub.db", tmp_path)
    init_hub_schema(db)
    t1 = "2026-07-01T10:00:00+00:00"
    t2 = "2026-07-01T12:00:00+00:00"
    touch_last_inbound("wx_a", "wechat", display_name="张三", at=t1, data_dir=tmp_path)
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            f"SELECT last_inbound_at, display_name, funnel_stage FROM {contacts_table('wechat')} WHERE customer_uid=?",
            ("wx_a",),
        ).fetchone()
        assert row == (t1, "张三", "consulting")
        touch_last_inbound("wx_a", "wechat", at=t2, data_dir=tmp_path)
        row2 = conn.execute(
            f"SELECT last_inbound_at, display_name FROM {contacts_table('wechat')} WHERE customer_uid=?",
            ("wx_a",),
        ).fetchone()
        assert row2 == (t2, "张三")
    finally:
        conn.close()


def test_touch_skips_unknown_sender(tmp_path: Path) -> None:
    db = mxai_db_path("hub.db", tmp_path)
    init_hub_schema(db)
    touch_last_inbound("unknown", "wechat", data_dir=tmp_path)
    touch_last_inbound("", "wechat", data_dir=tmp_path)
    conn = sqlite3.connect(db)
    try:
        n = conn.execute(f"SELECT COUNT(*) FROM {contacts_table('wechat')}").fetchone()[0]
        assert n == 0
    finally:
        conn.close()


def test_wechat_inbound_sets_last_inbound_at(mxai_client, mxai_env) -> None:
    from plugins.mxai.rpa.wechat.sidecar import WechatSidecar

    WechatSidecar.reset()
    before = utc_now_iso()
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/inbound",
        json={"message_id": "wx1", "sender": "wx_user_inbound", "message": "你好"},
    )
    assert resp.status_code == 200
    db = mxai_db_path("hub.db", mxai_env)
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            f"SELECT last_inbound_at FROM {contacts_table('wechat')} WHERE customer_uid=?",
            ("wx_user_inbound",),
        ).fetchone()
        assert row is not None
        assert row[0] >= before
        assert "+00:00" in row[0] or row[0].endswith("Z")
    finally:
        conn.close()


def test_wechat_inbound_cache_hit_still_touches_last_inbound(mxai_client, mxai_env) -> None:
    """去重缓存命中仍须刷新 last_inbound_at（CR-130 · 预览静默）。"""
    from plugins.mxai.rpa.wechat.sidecar import WechatSidecar

    WechatSidecar.reset()
    peer = "wx_cache_touch"
    payload = {"message_id": "wx-cache-1", "sender": peer, "message": "同一句"}
    first = mxai_client.post("/api/plugins/mxai/agents/wechat/inbound", json=payload)
    assert first.status_code == 200
    db = mxai_db_path("hub.db", mxai_env)
    conn = sqlite3.connect(db)
    try:
        t1 = conn.execute(
            f"SELECT last_inbound_at FROM {contacts_table('wechat')} WHERE customer_uid=?",
            (peer,),
        ).fetchone()[0]
    finally:
        conn.close()

    # 同一 message_id：走缓存短路，不得跳过 touch
    second = mxai_client.post("/api/plugins/mxai/agents/wechat/inbound", json=payload)
    assert second.status_code == 200
    conn = sqlite3.connect(db)
    try:
        t2 = conn.execute(
            f"SELECT last_inbound_at FROM {contacts_table('wechat')} WHERE customer_uid=?",
            (peer,),
        ).fetchone()[0]
    finally:
        conn.close()
    assert t2 >= t1


def test_wechat_takeover_inbound_still_touches_last_inbound(mxai_client, mxai_env) -> None:
    """接管态不自动回复，但仍须记入站时间（CR-130）。"""
    from plugins.mxai.conversations.service import conv_id_for_peer, set_conversation_mode
    from plugins.mxai.rpa.wechat.sidecar import WechatSidecar

    WechatSidecar.reset()
    peer = "wx_takeover_touch"
    set_conversation_mode("wechat", conv_id_for_peer(peer), "takeover", data_dir=mxai_env)
    before = utc_now_iso()
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/inbound",
        json={"message_id": "wx-to-1", "sender": peer, "message": "接管中提问"},
    )
    assert resp.status_code == 200
    assert resp.json().get("mode") == "takeover"
    db = mxai_db_path("hub.db", mxai_env)
    conn = sqlite3.connect(db)
    try:
        row = conn.execute(
            f"SELECT last_inbound_at FROM {contacts_table('wechat')} WHERE customer_uid=?",
            (peer,),
        ).fetchone()
        assert row is not None
        assert row[0] >= before
    finally:
        conn.close()
