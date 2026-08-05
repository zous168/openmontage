"""LT-033：worklog.db + report.db 并入 hub.db 的 schema 合并 + 数据迁移单测."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.storage.hub_repo import init_hub_schema


def _make_legacy_worklog(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE work_logs (
            log_id TEXT PRIMARY KEY, op_time TEXT NOT NULL, profile_id TEXT NOT NULL,
            op_type TEXT NOT NULL, op_object TEXT, exec_status TEXT NOT NULL,
            fail_reason TEXT, elapsed_ms INTEGER, task_id TEXT,
            created_at TEXT NOT NULL DEFAULT (datetime('now')), touch_class TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO work_logs (log_id, op_time, profile_id, op_type, exec_status, touch_class) "
        "VALUES ('lg1','2026-06-01 10:00:00','wechat','dm','success','active')"
    )
    conn.commit()
    conn.close()


def _make_legacy_report(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE reports (report_id TEXT PRIMARY KEY, report_type TEXT NOT NULL,
            title TEXT, created_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE TABLE report_snapshots (snapshot_id TEXT PRIMARY KEY, report_id TEXT NOT NULL,
            snapshot_at TEXT NOT NULL, payload_json TEXT);
        """
    )
    conn.execute("INSERT INTO reports (report_id, report_type, title) VALUES ('r1','weekly','周报')")
    conn.execute(
        "INSERT INTO report_snapshots (snapshot_id, report_id, snapshot_at, payload_json) "
        "VALUES ('s1','r1','2026-06-07','{\"k\":1}')"
    )
    conn.commit()
    conn.close()


def _tables(db: Path) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()


def test_v10_creates_merged_tables(tmp_path: Path) -> None:
    hub = mxai_db_path("hub.db", tmp_path)
    init_hub_schema(hub)
    tables = _tables(hub)
    assert {"work_logs", "reports", "report_snapshots", "customers", "leads"} <= tables


def test_legacy_data_migrated_and_renamed(tmp_path: Path) -> None:
    _make_legacy_worklog(tmp_path / "worklog.db")
    _make_legacy_report(tmp_path / "report.db")
    hub = mxai_db_path("hub.db", tmp_path)

    init_hub_schema(hub)

    conn = sqlite3.connect(hub)
    try:
        wl = conn.execute("SELECT touch_class FROM work_logs WHERE log_id='lg1'").fetchone()
        rp = conn.execute("SELECT title FROM reports WHERE report_id='r1'").fetchone()
        sn = conn.execute("SELECT payload_json FROM report_snapshots WHERE snapshot_id='s1'").fetchone()
    finally:
        conn.close()
    assert wl and wl[0] == "active"   # 含 v2 touch_class 列也迁过来
    assert rp and rp[0] == "周报"
    assert sn is not None

    # 旧文件改名 .migrated 兜底，不再以原名残留
    assert not (tmp_path / "worklog.db").exists()
    assert not (tmp_path / "report.db").exists()
    assert (tmp_path / "worklog.db.migrated").exists()
    assert (tmp_path / "report.db.migrated").exists()


def test_migration_idempotent_no_legacy(tmp_path: Path) -> None:
    """无旧库时再次 init 不报错、不重复迁移（版本号取补丁链最高版，不硬编码）."""
    from plugins.mxai.storage.schema_migrations import hub as _hub_pkg
    from plugins.mxai.storage.schema_migrations import max_schema_version

    top = max_schema_version(_hub_pkg)
    hub = mxai_db_path("hub.db", tmp_path)
    assert init_hub_schema(hub) == top
    assert init_hub_schema(hub) == top  # 第二次幂等
