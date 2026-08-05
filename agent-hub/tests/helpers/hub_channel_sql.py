"""测试用 hub 渠道表 / 分版本迁移辅助（CR-42）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from plugins.mxai.storage.schema import read_schema_version, write_schema_version
from plugins.mxai.storage.schema_migrations import discover_schema_migrations
from plugins.mxai.storage.schema_migrations import hub as hub_pkg

_CONTACT_TABLES = (
    ("wechat", "wechat_contacts"),
    ("qiyeweixin", "wecom_contacts"),
)
_ALIAS_TABLES = (
    ("wechat", "wechat_identity_aliases"),
    ("qiyeweixin", "wecom_identity_aliases"),
)
_TOUCH_TABLES = (
    ("wechat", "wechat_touch_deliveries"),
    ("qiyeweixin", "wecom_touch_deliveries"),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def migrate_hub_to(db: Path, max_version: int) -> int:
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        current = read_schema_version(conn)
        for mig in discover_schema_migrations(hub_pkg):
            if mig.version <= current and mig.after_commit is not None:
                mig.after_commit(conn, db)
        for migration in discover_schema_migrations(hub_pkg):
            if migration.version > max_version:
                break
            if current >= migration.version:
                continue
            migration.apply(conn, db)
            write_schema_version(conn, migration.version)
            conn.commit()
            current = migration.version
            if migration.after_commit is not None:
                migration.after_commit(conn, db)
        return int(read_schema_version(conn))
    finally:
        conn.close()


def contacts_table(profile_id: str) -> str:
    if profile_id == "wechat":
        return "wechat_contacts"
    if profile_id == "qiyeweixin":
        return "wecom_contacts"
    raise ValueError(profile_id)


def touch_table(profile_id: str) -> str:
    if profile_id == "wechat":
        return "wechat_touch_deliveries"
    if profile_id == "qiyeweixin":
        return "wecom_touch_deliveries"
    raise ValueError(profile_id)


def aliases_table(profile_id: str) -> str:
    if profile_id == "wechat":
        return "wechat_identity_aliases"
    if profile_id == "qiyeweixin":
        return "wecom_identity_aliases"
    raise ValueError(profile_id)


def fetch_contact_row(
    conn: sqlite3.Connection,
    customer_uid: str,
    profile_id: str = "wechat",
) -> sqlite3.Row | None:
    conn.row_factory = sqlite3.Row
    table = contacts_table(profile_id)
    if _table_exists(conn, table):
        return conn.execute(
            f"SELECT * FROM {table} WHERE customer_uid = ?",
            (customer_uid,),
        ).fetchone()
    if _table_exists(conn, "customers"):
        return conn.execute(
            "SELECT * FROM customers WHERE profile_id = ? AND customer_uid = ?",
            (profile_id, customer_uid),
        ).fetchone()
    return None


def count_contacts(conn: sqlite3.Connection, profile_id: str | None = None) -> int:
    if profile_id:
        table = contacts_table(profile_id)
        if _table_exists(conn, table):
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        if _table_exists(conn, "customers"):
            return int(
                conn.execute(
                    "SELECT COUNT(*) FROM customers WHERE profile_id = ?",
                    (profile_id,),
                ).fetchone()[0]
            )
        return 0
    total = 0
    if _table_exists(conn, "customers"):
        return int(conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0])
    for _pid, table in _CONTACT_TABLES:
        if _table_exists(conn, table):
            total += int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    return total


def insert_touch_delivery(
    conn: sqlite3.Connection,
    *,
    delivery_id: str,
    profile_id: str,
    channel_account_id: str,
    subtask_id: str,
    customer_identity_key: str,
    business_date: str,
    status: str,
    **fields: Any,
) -> None:
    if _table_exists(conn, "touch_deliveries"):
        conn.execute(
            """
            INSERT INTO touch_deliveries (
                delivery_id, profile_id, channel_account_id, subtask_id,
                customer_identity_key, business_date, status, task_id,
                dispatch_state, execution_id, accepted_at, attempt_count,
                threshold_sec, silence_sec, last_inbound_at_snapshot,
                identity_revision, decision_hash, identity_confidence,
                reserved_at, completed_at, fail_code, fail_reason,
                migration_source, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                delivery_id,
                profile_id,
                channel_account_id,
                subtask_id,
                customer_identity_key,
                business_date,
                status,
                fields.get("task_id"),
                fields.get("dispatch_state", "terminal"),
                fields.get("execution_id"),
                fields.get("accepted_at"),
                fields.get("attempt_count", 1),
                fields.get("threshold_sec", 1800),
                fields.get("silence_sec", 1800),
                fields.get("last_inbound_at_snapshot", ""),
                fields.get("identity_revision", 1),
                fields.get("decision_hash", "test"),
                fields.get("identity_confidence", "low"),
                fields.get("reserved_at", ""),
                fields.get("completed_at"),
                fields.get("fail_code"),
                fields.get("fail_reason"),
                fields.get("migration_source"),
                fields.get("updated_at", ""),
            ),
        )
        return
    table = touch_table(profile_id)
    conn.execute(
        f"""
        INSERT INTO {table} (
            delivery_id, channel_account_id, subtask_id,
            customer_identity_key, business_date, status, task_id,
            dispatch_state, execution_id, accepted_at, attempt_count,
            threshold_sec, silence_sec, last_inbound_at_snapshot,
            identity_revision, decision_hash, identity_confidence,
            reserved_at, completed_at, fail_code, fail_reason,
            migration_source, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
        )
        """,
        (
            delivery_id,
            channel_account_id,
            subtask_id,
            customer_identity_key,
            business_date,
            status,
            fields.get("task_id"),
            fields.get("dispatch_state", "terminal"),
            fields.get("execution_id"),
            fields.get("accepted_at"),
            fields.get("attempt_count", 1),
            fields.get("threshold_sec", 1800),
            fields.get("silence_sec", 1800),
            fields.get("last_inbound_at_snapshot", ""),
            fields.get("identity_revision", 1),
            fields.get("decision_hash", "test"),
            fields.get("identity_confidence", "low"),
            fields.get("reserved_at", ""),
            fields.get("completed_at"),
            fields.get("fail_code"),
            fields.get("fail_reason"),
            fields.get("migration_source"),
            fields.get("updated_at", ""),
        ),
    )
