"""CR-132 · add_records 单表服务单测：迁移 / 导入去重 / 双重筛选 / 渠道隔离 / 状态流转."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from plugins.mxai.crm.add_records import service as svc
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.contacts.structured_parser import ContactRow
from plugins.mxai.crm.storage.hub_repo import init_hub_schema
from core.timeutil import utc_now_iso


def _rows(*pairs: tuple[str | None, str], start: int = 1) -> list[ContactRow]:
    return [
        ContactRow(display_name=name, contact_id=cid, row_num=i)
        for i, (name, cid) in enumerate(pairs, start=start)
    ]


# ---- 导入 / 去重 / 空 contact_id / 客户名可空 ----

def test_import_writes_pending_and_skips_empty(tmp_path: Path) -> None:
    res = svc.import_rows(
        "wechat",
        _rows(("张三", "wxid_1"), (None, "wxid_2"), ("空号", "")),
        data_dir=tmp_path,
    )
    assert res["added"] == 2  # 客户名可空仍入库
    assert res["skipped_rows"] == [3]  # 空 contact_id 记行号
    listing = svc.list_records("wechat", data_dir=tmp_path)
    assert listing["total"] == 2
    assert {r["status"] for r in listing["records"]} == {"pending"}
    assert {r["import_source"] for r in listing["records"]} == {"manual"}
    # 客户名可空
    by_cid = {r["contact_id"]: r for r in listing["records"]}
    assert by_cid["wxid_2"]["display_name"] is None


def test_duplicate_contact_reported_then_replaced(tmp_path: Path) -> None:
    svc.import_rows("wechat", _rows(("张三", "wxid_1")), data_dir=tmp_path)
    dup = svc.import_rows("wechat", _rows(("张三改", "wxid_1")), data_dir=tmp_path)
    assert dup["added"] == 0
    assert len(dup["duplicates"]) == 1
    assert dup["duplicates"][0]["contact_id"] == "wxid_1"
    # replace → upsert 刷新客户名并回 pending
    rep = svc.import_rows(
        "wechat", _rows(("张三改", "wxid_1")), replace_duplicates=True, data_dir=tmp_path
    )
    assert rep["added"] == 1
    rec = svc.find_by_contact("wechat", "wxid_1", data_dir=tmp_path)
    assert rec["display_name"] == "张三改" and rec["status"] == "pending"


# ---- 双重筛选：状态 × 来源 AND 精准匹配 ----

def test_dual_filter_status_and_source(tmp_path: Path) -> None:
    svc.import_rows("wechat", _rows(("A", "a"), ("B", "b"), ("C", "c")), data_dir=tmp_path)
    svc.mark_success("wechat", "a", data_dir=tmp_path)
    svc.mark_failed("wechat", "b", reason="风控拦截", data_dir=tmp_path)
    # c 仍 pending

    only_pending = svc.list_records("wechat", statuses=["pending"], data_dir=tmp_path)
    assert only_pending["total"] == 1 and only_pending["records"][0]["contact_id"] == "c"

    manual_success = svc.list_records(
        "wechat", statuses=["success"], sources=["manual"], data_dir=tmp_path
    )
    assert manual_success["total"] == 1 and manual_success["records"][0]["contact_id"] == "a"

    # 来源不匹配 → 空（AND 交集）
    none_hit = svc.list_records(
        "wechat", statuses=["success"], sources=["douyin"], data_dir=tmp_path
    )
    assert none_hit["total"] == 0

    # 多状态 IN
    two = svc.list_records("wechat", statuses=["success", "failed"], data_dir=tmp_path)
    assert two["total"] == 2

    # 非法筛选值被忽略（等同不筛）
    all_rows = svc.list_records("wechat", statuses=["bogus"], data_dir=tmp_path)
    assert all_rows["total"] == 3


# ---- 渠道隔离 ----

def test_channel_isolation(tmp_path: Path) -> None:
    svc.import_rows("wechat", _rows(("张三", "shared_id")), data_dir=tmp_path)
    # 同号可在企微独立各存一份（唯一键含 profile_id）
    svc.import_rows("qiyeweixin", _rows(("张三", "shared_id")), data_dir=tmp_path)

    wx = svc.list_records("wechat", data_dir=tmp_path)
    ww = svc.list_records("qiyeweixin", data_dir=tmp_path)
    assert wx["total"] == 1 and ww["total"] == 1
    # op_type 随渠道
    assert wx["records"][0]["op_type"] == "add_friends"
    assert ww["records"][0]["op_type"] == "add_contacts"
    # 微信页导入不出现在企微查询（互不展示），且互不干扰
    svc.mark_success("wechat", "shared_id", data_dir=tmp_path)
    assert svc.list_records("qiyeweixin", statuses=["success"], data_dir=tmp_path)["total"] == 0


# ---- 状态流转：success / failed / retry ----

def test_status_transitions_and_retry(tmp_path: Path) -> None:
    svc.import_rows("wechat", _rows(("A", "a")), data_dir=tmp_path)
    svc.mark_failed("wechat", "a", reason="超时", data_dir=tmp_path)
    rec = svc.find_by_contact("wechat", "a", data_dir=tmp_path)
    assert rec["status"] == "failed" and rec["failed_reason"] == "超时" and rec["touched_at"]

    ok = svc.retry_record(rec["record_id"], "wechat", data_dir=tmp_path)
    assert ok is True
    rec2 = svc.find_by_contact("wechat", "a", data_dir=tmp_path)
    assert rec2["status"] == "pending" and rec2["failed_reason"] is None and rec2["touched_at"] is None

    # retry 仅对 failed 生效
    svc.mark_success("wechat", "a", data_dir=tmp_path)
    assert svc.retry_record(rec["record_id"], "wechat", data_dir=tmp_path) is False


def test_resolve_pending(tmp_path: Path) -> None:
    svc.import_rows("wechat", _rows(("A", "a"), ("B", "b")), data_dir=tmp_path)
    svc.mark_success("wechat", "a", data_dir=tmp_path)
    pend = svc.resolve_pending("wechat", None, all_pending=True, data_dir=tmp_path)
    assert [p["contact_id"] for p in pend] == ["b"]  # 仅 pending
    rec_b = svc.find_by_contact("wechat", "b", data_dir=tmp_path)
    sel = svc.resolve_pending("wechat", [rec_b["record_id"]], data_dir=tmp_path)
    assert len(sel) == 1 and sel[0]["contact_id"] == "b"


def test_delete_and_labels(tmp_path: Path) -> None:
    svc.import_rows("wechat", _rows(("A", "a")), data_dir=tmp_path)
    rec = svc.find_by_contact("wechat", "a", data_dir=tmp_path)
    assert rec["status_label"] == "待添加" and rec["import_source_label"] == "手工导入"
    assert svc.delete_record(rec["record_id"], "wechat", data_dir=tmp_path) is True
    assert svc.list_records("wechat", data_dir=tmp_path)["total"] == 0


# ---- 迁移：pending_add_contacts → add_records（_DDL_V13 幂等重放）----

def test_migration_from_pending_add_contacts(tmp_path: Path) -> None:
    from plugins.mxai.storage.schema_migrations.hub.v0013_add_records import DDL as _DDL_V13

    db = tmp_path / "v13_legacy.db"
    conn = sqlite3.connect(db)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS pending_add_contacts (
                pending_id TEXT PRIMARY KEY,
                profile_id TEXT NOT NULL,
                contact_id TEXT NOT NULL,
                display_name TEXT,
                import_method TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                last_failed_at TEXT,
                import_batch_id TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
            """
        )
        conn.execute(
            "INSERT INTO pending_add_contacts (pending_id, profile_id, contact_id, "
            "display_name, import_method, status, created_at) "
            "VALUES ('p1', 'qiyeweixin', 'qw_1', '老王', 'manual_excel', 'pending', ?)",
            (utc_now_iso(),),
        )
        conn.commit()
        conn.executescript(_DDL_V13)
        conn.commit()
        row = conn.execute(
            "SELECT * FROM add_records WHERE record_id = 'p1'"
        ).fetchone()
    finally:
        conn.close()
    assert row is not None
    # add_records 列序：record_id, profile_id, contact_id, display_name, import_source, op_type, status
    assert row[1] == "qiyeweixin"  # profile_id
    assert row[4] == "manual"  # import_source（import_method 折叠）
    assert row[5] == "add_contacts"  # op_type 按 profile 推断
    assert row[6] == "pending"  # status 保留
