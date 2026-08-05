"""CustomerIdentityResolver 单元测试."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.storage.hub_repo import init_hub_schema
from plugins.mxai.storage.channel_tables import contacts_table
from plugins.mxai.storage.customer_identity import (
    DEFAULT_CHANNEL_ACCOUNT_ID,
    insert_remark_alias,
    load_or_create_identity_secret,
    migrated_customer_identity_key,
)
from plugins.mxai.storage.customer_identity_resolver import CustomerIdentityResolver


def _seed_identity_customer(
    data_dir: Path,
    uid: str,
    *,
    display_name: str,
    confidence: str = "low",
) -> str:
    db = mxai_db_path("hub.db", data_dir)
    init_hub_schema(db)
    secret = load_or_create_identity_secret(data_dir)
    identity_key = migrated_customer_identity_key(
        secret,
        "wechat",
        DEFAULT_CHANNEL_ACCOUNT_ID,
        uid,
    )
    table = contacts_table("wechat")
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {table} (
                customer_uid, display_name, created_at,
                channel_account_id, customer_identity_key,
                identity_confidence, identity_revision
            ) VALUES (?, ?, datetime('now'), ?, ?, ?, 1)
            """,
            (uid, display_name, DEFAULT_CHANNEL_ACCOUNT_ID, identity_key, confidence),
        )
        insert_remark_alias(
            conn,
            data_dir=data_dir,
            profile_id="wechat",
            customer_identity_key=identity_key,
            remark=display_name,
            created_at="2026-07-15T00:00:00+00:00",
            source="test",
        )
        conn.commit()
    finally:
        conn.close()
    return identity_key


def test_resolver_remark_unique_is_send_capable(tmp_path: Path) -> None:
    key = _seed_identity_customer(tmp_path, "u1", display_name="Alice")
    resolver = CustomerIdentityResolver(data_dir=tmp_path)
    locator = resolver.resolve(
        "wechat",
        customer_uid="u1",
        customer_identity_key=key,
        identity_confidence="low",
        display_name="Alice",
    )
    assert locator.send_capable is True
    assert locator.locator_type == "remark"
    assert locator.locator_value == "Alice"


def test_resolver_duplicate_remark_not_send_capable(tmp_path: Path) -> None:
    key_a = _seed_identity_customer(tmp_path, "u_a", display_name="Bob")
    key_b = _seed_identity_customer(tmp_path, "u_b", display_name="Bob")
    resolver = CustomerIdentityResolver(data_dir=tmp_path)
    locator_a = resolver.resolve(
        "wechat",
        customer_uid="u_a",
        customer_identity_key=key_a,
        display_name="Bob",
    )
    locator_b = resolver.resolve(
        "wechat",
        customer_uid="u_b",
        customer_identity_key=key_b,
        display_name="Bob",
    )
    assert locator_a.send_capable is False
    assert locator_a.skip_reason == "identity_conflict"
    assert locator_b.send_capable is False


def test_resolver_conflict_blocked(tmp_path: Path) -> None:
    resolver = CustomerIdentityResolver(data_dir=tmp_path)
    locator = resolver.resolve(
        "wechat",
        customer_uid="missing",
        identity_confidence="conflict",
    )
    assert locator.send_capable is False
    assert locator.skip_reason == "identity_conflict"
