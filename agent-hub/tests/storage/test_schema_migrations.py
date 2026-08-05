"""SQL schema 补丁运行器（一版一文件、按版本号顺序 apply、幂等）单测。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.storage.schema import read_schema_version
from plugins.mxai.storage.schema_migrations import (
    discover_schema_migrations,
    max_schema_version,
    run_schema_migrations,
)
from plugins.mxai.storage.schema_migrations import hub as hub_pkg
from plugins.mxai.storage.schema_migrations import kb as kb_pkg
from plugins.mxai.storage.schema_migrations import materials as mat_pkg


def test_versions_are_contiguous_and_sorted() -> None:
    for pkg, top in ((hub_pkg, 22), (kb_pkg, 7), (mat_pkg, 3)):
        migs = discover_schema_migrations(pkg)
        versions = [m.version for m in migs]
        assert versions == list(range(1, top + 1)), f"{pkg.__name__} 版本链不连续：{versions}"
        assert max_schema_version(pkg) == top


def test_run_applies_all_and_is_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    db = mxai_db_path("hub.db", tmp_path)
    assert run_schema_migrations(db, hub_pkg) == 22
    # 第二次运行：已达顶，幂等无副作用
    assert run_schema_migrations(db, hub_pkg) == 22

    conn = sqlite3.connect(db)
    try:
        assert read_schema_version(conn) == 22
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {
            "wechat_contacts",
            "wecom_contacts",
            "wechat_identity_aliases",
            "wecom_identity_aliases",
            "wechat_touch_deliveries",
            "wecom_touch_deliveries",
            "douyin_leads",
            "work_logs",
            "reports",
            "wechat_add_records",
            "wecom_add_records",
            "train_ai_adopted",
            "train_ai_ignored",
            "train_ai_adopt_log",
        } <= tables
        assert "customers" not in tables
        assert "leads" not in tables
        assert "touch_deliveries" not in tables
        assert "queue_tasks" not in tables
        assert "pending_add_contacts" not in tables
        customer_columns = {
            row[1]: row for row in conn.execute("PRAGMA table_info(wechat_contacts)")
        }
        for name in (
            "channel_account_id",
            "customer_identity_key",
            "identity_confidence",
            "identity_revision",
        ):
            assert customer_columns[name][3] == 1
        assert "delivery_id" in {
            row[1] for row in conn.execute("PRAGMA table_info(work_logs)")
        }
    finally:
        conn.close()


def test_partial_upgrade_resumes_from_current(tmp_path: Path) -> None:
    # 先只有部分补丁（模拟旧库停在中间版本），再跑一次应补齐到最高版
    db = tmp_path / "kb.db"
    run_schema_migrations(db, kb_pkg)
    # 人为回退版本号到 3，再次运行应从 4 续跑到 7
    conn = sqlite3.connect(db)
    try:
        conn.execute("UPDATE schema_migrations SET version = 3 WHERE id = 1")
        conn.commit()
    finally:
        conn.close()
    assert run_schema_migrations(db, kb_pkg) == 7
