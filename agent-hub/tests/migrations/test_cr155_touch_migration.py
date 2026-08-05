"""LT-045.02.01 · CR-155 Tier-1/Tier-2 协同迁移。"""

from __future__ import annotations

import json
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from core.timeutil import BEIJING, beijing_now
from plugins.mxai.cfg.data_migrations import read_ledger, run_pending_data_migrations
from plugins.mxai.cfg.paths import agent_cfg_path, mxai_db_path, state_path
from plugins.mxai.cfg.store import atomic_write_yaml, read_yaml
from plugins.mxai.storage.schema import read_schema_version, write_schema_version
from plugins.mxai.storage.schema_migrations import (
    discover_schema_migrations,
    run_schema_migrations,
)
from plugins.mxai.storage.schema_migrations import hub as hub_pkg
from tests.helpers.hub_channel_sql import (
    aliases_table,
    contacts_table,
    fetch_contact_row,
    migrate_hub_to,
)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    return tmp_path


def _seed_v18(data_dir: Path) -> Path:
    db = mxai_db_path("hub.db", data_dir)
    db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db)
    try:
        for migration in discover_schema_migrations(hub_pkg):
            if migration.version > 18:
                break
            migration.apply(conn, db)
            write_schema_version(conn, migration.version)
            conn.commit()
    finally:
        conn.close()
    return db


def _insert_customer(
    db: Path,
    uid: str,
    profile_id: str,
    display_name: str,
    last_inbound_at: str,
) -> None:
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            """
            INSERT INTO customers (
                customer_uid, profile_id, display_name, source_channel,
                funnel_stage, funnel_stage_at, created_at, updated_at,
                last_inbound_at
            ) VALUES (?, ?, ?, ?, 'consulting', ?, ?, ?, ?)
            """,
            (
                uid,
                profile_id,
                display_name,
                profile_id,
                last_inbound_at,
                last_inbound_at,
                last_inbound_at,
                last_inbound_at,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _write_state(data_dir: Path, payload: dict) -> None:
    path = state_path("scheduler_state.json", data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _old_workbench(*, mode: str, prompt: str = "") -> dict:
    return {
        "scheduler": {
            "scheduled_touch": {
                "enabled": True,
                "mode": "segmented",
                "content_mode": mode,
                "revisit_prompt": prompt,
                "excluded_customer_uids": [],
                "global_filters": {"exclude_touched_within_hours": 24},
                "segments": [],
            }
        }
    }


def test_v18_upgrade_converts_config_and_imports_today_only(data_dir: Path) -> None:
    db = _seed_v18(data_dir)
    now = beijing_now().replace(microsecond=0)
    today_at = now.isoformat()
    yesterday_at = (now - timedelta(days=1)).isoformat()
    inbound_at = (now - timedelta(hours=3)).astimezone(BEIJING).isoformat()
    _insert_customer(db, "wx-customer-1", "wechat", "同名客户", inbound_at)
    _insert_customer(db, "wx-customer-2", "wechat", "同名客户", inbound_at)
    _insert_customer(db, "ww-customer-1", "qiyeweixin", "企微客户", inbound_at)

    wechat = _old_workbench(mode="static")
    wechat_touch = wechat["scheduler"]["scheduled_touch"]
    wechat_touch["excluded_customer_uids"] = ["wx-customer-1", "missing-customer"]
    wechat_touch["segments"] = [
        {
            "id": "silence_30m",
            "label": "30 分钟",
            "enabled": True,
            "silence_min_sec": 1800,
            "silence_max_sec": 3600,
            "run_at": "10:00",
            "message": "静态原话术",
        },
        {
            "id": "silence_60m",
            "label": "60 分钟",
            "enabled": True,
            "silence_min_sec": 3600,
            "message": "历史话术",
        },
    ]
    qiye = _old_workbench(mode="llm", prompt="询问售后使用情况")
    qiye["scheduler"]["scheduled_touch"]["segments"] = [
        {
            "id": "revisit_1h",
            "label": "1 小时",
            "enabled": True,
            "silence_min_sec": 3600,
            "message": "不得迁入静态字段",
        }
    ]
    atomic_write_yaml(agent_cfg_path("wechat", "workbench.yaml", data_dir), wechat)
    atomic_write_yaml(agent_cfg_path("qiyeweixin", "workbench.yaml", data_dir), qiye)
    _write_state(
        data_dir,
        {
            "agents": {
                "wechat": {
                    "scheduled_touch": {
                        "touches": {
                            "silence_30m": {"wx-customer-1": today_at},
                            "silence_60m": {"wx-customer-2": yesterday_at},
                        },
                        "segment_runs": {"silence_30m": now.strftime("%Y-%m-%d")},
                    }
                },
                "qiyeweixin": {
                    "scheduled_touch": {
                        "touches": {"revisit_1h": {"ww-customer-1": today_at}}
                    }
                },
            }
        },
    )

    first = run_pending_data_migrations(data_dir)
    assert "cr155-touch-config" in first["ran"]
    second = run_pending_data_migrations(data_dir)
    assert second["ran"] == {}
    backup_root = state_path("migration_backups/cr155", data_dir)
    assert (backup_root / "wechat" / "workbench.yaml").is_file()
    assert (backup_root / "qiyeweixin" / "workbench.yaml").is_file()
    assert (backup_root / "scheduler_state.json").is_file()

    migrated_wechat = read_yaml(agent_cfg_path("wechat", "workbench.yaml", data_dir))
    touch = migrated_wechat["scheduler"]["scheduled_touch"]
    assert "segments" not in touch
    assert "excluded_customer_uids" not in touch
    assert "content_mode" not in touch
    assert touch["global_filters"]["exclude_touched_within_hours"] == 0
    assert touch["touch_subtasks"][0] == {
        "id": "silence_30m",
        "label": "30 分钟",
        "enabled": True,
        "threshold": {"days": 0, "hours": 0, "minutes": 30},
        "threshold_sec": 1800,
        "content_mode": "static",
        "message": "静态原话术",
    }
    assert len(touch["excluded_customer_keys"]) == 1
    assert "wx-customer-1" not in touch["excluded_customer_keys"][0]

    migrated_qiye = read_yaml(agent_cfg_path("qiyeweixin", "workbench.yaml", data_dir))
    qiye_subtask = migrated_qiye["scheduler"]["scheduled_touch"]["touch_subtasks"][0]
    assert qiye_subtask["content_mode"] == "llm"
    assert qiye_subtask["ai_instruction"] == "询问售后使用情况"
    assert "message" not in qiye_subtask

    state = json.loads(state_path("scheduler_state.json", data_dir).read_text(encoding="utf-8"))
    assert "touches" not in state["agents"]["wechat"]["scheduled_touch"]
    assert "segment_runs" not in state["agents"]["wechat"]["scheduled_touch"]
    handoff_path = state_path("cr155_touch_migration.json", data_dir)
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff["status"] == "ready"
    assert handoff["summary"] == {"deliveries": 2, "historical": 1, "conflicts": 1}

    assert migrate_hub_to(db, 20) == 20
    assert migrate_hub_to(db, 20) == 20
    imported = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert imported["status"] == "imported"

    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    try:
        customers = conn.execute(
            """
            SELECT channel_account_id, customer_identity_key,
                   channel_identity_type, identity_confidence, identity_revision
            FROM customers ORDER BY customer_uid
            """
        ).fetchall()
        assert len(customers) == 3
        assert all(
            row["channel_account_id"] == "single-account-default" for row in customers
        )
        assert all(str(row["customer_identity_key"]).startswith("cid_v1_") for row in customers)
        assert all(row["identity_revision"] == 1 for row in customers)
        assert [row["identity_confidence"] for row in customers].count("conflict") == 2

        aliases = conn.execute(
            "SELECT identity_lookup_key, identity_value_enc FROM customer_identity_aliases"
        ).fetchall()
        assert len(aliases) == 3
        assert all(str(row["identity_lookup_key"]).startswith("ilk_v1_") for row in aliases)
        assert all(row["identity_value_enc"] is None for row in aliases)
        assert all("同名客户" not in row["identity_lookup_key"] for row in aliases)

        deliveries = conn.execute(
            """
            SELECT status, dispatch_state, attempt_count, business_date, migration_source
            FROM touch_deliveries ORDER BY profile_id
            """
        ).fetchall()
        assert len(deliveries) == 2
        assert all(row["status"] == "legacy_assumed_success" for row in deliveries)
        assert all(row["dispatch_state"] == "terminal" for row in deliveries)
        assert all(row["attempt_count"] == 0 for row in deliveries)
        assert all(row["business_date"] == now.strftime("%Y-%m-%d") for row in deliveries)
        assert all(row["migration_source"] == "cr155" for row in deliveries)
        assert "delivery_id" in {
            row[1] for row in conn.execute("PRAGMA table_info(work_logs)")
        }
    finally:
        conn.close()


def test_late_handoff_accepts_existing_success_business_key(data_dir: Path) -> None:
    db = _seed_v18(data_dir)
    now = beijing_now().replace(microsecond=0)
    now_iso = now.isoformat()
    business_date = now.strftime("%Y-%m-%d")
    _insert_customer(db, "existing-success-customer", "wechat", "已成功客户", now_iso)
    assert migrate_hub_to(db, 20) == 20

    conn = sqlite3.connect(db)
    try:
        identity_key = str(
            conn.execute(
                """
                SELECT customer_identity_key
                FROM customers
                WHERE customer_uid = 'existing-success-customer'
                """
            ).fetchone()[0]
        )
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
                ?, ?, 'single-account-default', ?, ?, ?, 'success', 'existing-task',
                'terminal', 'existing-execution', ?, 3, 1800, 1800, ?,
                1, 'existing-decision', 'low', ?, ?, NULL, NULL,
                'existing-live-send', ?
            )
            """,
            (
                "existing-success-delivery",
                "wechat",
                "late-subtask",
                identity_key,
                business_date,
                now_iso,
                now_iso,
                now_iso,
                now_iso,
                now_iso,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    handoff_delivery = {
        "delivery_id": "late-handoff-delivery",
        "profile_id": "wechat",
        "channel_account_id": "single-account-default",
        "subtask_id": "late-subtask",
        "customer_identity_key": identity_key,
        "business_date": business_date,
        "customer_uid": "existing-success-customer",
        "threshold_sec": 1800,
        "silence_sec": 1800,
        "last_inbound_at_snapshot": now_iso,
        "identity_revision": 1,
        "decision_hash": "late-handoff-decision",
        "identity_confidence": "low",
        "old_timestamp": now_iso,
    }
    handoff_path = state_path("cr155_touch_migration.json", data_dir)
    handoff = {
        "schema": 1,
        "migration": "cr155-touch-config",
        "status": "ready",
        "migration_business_date": business_date,
        "deliveries": [{**handoff_delivery, "subtask_id": ""}],
    }
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    with pytest.raises(ValueError, match="missing required fields: subtask_id"):
        run_schema_migrations(db, hub_pkg)
    assert json.loads(handoff_path.read_text(encoding="utf-8"))["status"] == "ready"

    handoff["deliveries"] = [handoff_delivery]
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    assert migrate_hub_to(db, 20) == 20
    assert json.loads(handoff_path.read_text(encoding="utf-8"))["status"] == "imported"

    conn = sqlite3.connect(db)
    try:
        rows = conn.execute(
            """
            SELECT delivery_id, status, task_id, execution_id, attempt_count,
                   decision_hash, migration_source
            FROM touch_deliveries
            WHERE profile_id = 'wechat'
              AND channel_account_id = 'single-account-default'
              AND subtask_id = 'late-subtask'
              AND customer_identity_key = ?
              AND business_date = ?
            """,
            (identity_key, business_date),
        ).fetchall()
        assert rows == [
            (
                "existing-success-delivery",
                "success",
                "existing-task",
                "existing-execution",
                3,
                "existing-decision",
                "existing-live-send",
            )
        ]
    finally:
        conn.close()


def test_new_customer_gets_identity_and_remark_alias(data_dir: Path) -> None:
    db = mxai_db_path("hub.db", data_dir)
    assert run_schema_migrations(db, hub_pkg) == 21
    from plugins.mxai.crm.customer_inbound import touch_last_inbound

    touch_last_inbound(
        "new-external-id",
        "wechat",
        display_name="新客户备注",
        data_dir=data_dir,
    )
    conn = sqlite3.connect(db)
    try:
        customer = conn.execute(
            f"""
            SELECT channel_account_id, customer_identity_key,
                   channel_identity_type, identity_confidence, identity_revision
            FROM {contacts_table('wechat')} WHERE customer_uid = 'new-external-id'
            """
        ).fetchone()
        assert customer is not None
        assert customer[0] == "single-account-default"
        assert str(customer[1]).startswith("cid_v1_")
        assert customer[2:] == ("remark", "low", 1)
        alias = conn.execute(
            f"""
            SELECT identity_type, identity_lookup_key, identity_value_enc
            FROM {aliases_table('wechat')}
            WHERE customer_identity_key = ?
            """,
            (customer[1],),
        ).fetchone()
        assert alias is not None
        assert alias[0] == "remark"
        assert str(alias[1]).startswith("ilk_v1_")
        assert "新客户备注" not in alias[1]
        assert alias[2] is None
    finally:
        conn.close()


def test_schema_failure_keeps_v18_and_retry_succeeds(data_dir: Path) -> None:
    db = _seed_v18(data_dir)
    now = beijing_now().replace(microsecond=0)
    _insert_customer(db, "retry-customer", "wechat", "重试客户", now.isoformat())
    workbench = _old_workbench(mode="static")
    workbench["scheduler"]["scheduled_touch"]["segments"] = [
        {
            "id": "retry-segment",
            "label": "重试",
            "enabled": True,
            "silence_min_sec": 1800,
            "message": "重试话术",
        }
    ]
    atomic_write_yaml(agent_cfg_path("wechat", "workbench.yaml", data_dir), workbench)
    _write_state(
        data_dir,
        {
            "agents": {
                "wechat": {
                    "scheduled_touch": {
                        "touches": {"retry-segment": {"retry-customer": now.isoformat()}}
                    }
                }
            }
        },
    )
    run_pending_data_migrations(data_dir)
    handoff_path = state_path("cr155_touch_migration.json", data_dir)
    handoff = json.loads(handoff_path.read_text(encoding="utf-8"))
    original_key = handoff["deliveries"][0]["customer_identity_key"]
    handoff["deliveries"][0]["customer_identity_key"] = "cid_v1_tampered"
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")

    with pytest.raises(ValueError, match="identity key mismatch"):
        run_schema_migrations(db, hub_pkg)
    conn = sqlite3.connect(db)
    try:
        assert read_schema_version(conn) == 18
        assert conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='touch_deliveries'"
        ).fetchone() is None
    finally:
        conn.close()

    handoff["deliveries"][0]["customer_identity_key"] = original_key
    handoff_path.write_text(json.dumps(handoff), encoding="utf-8")
    assert migrate_hub_to(db, 20) == 20


def test_tier1_failure_is_not_recorded_and_retries(
    data_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = _seed_v18(data_dir)
    now = beijing_now().replace(microsecond=0)
    _insert_customer(db, "late-customer", "wechat", "延迟交接客户", now.isoformat())
    workbench = _old_workbench(mode="static")
    workbench["scheduler"]["scheduled_touch"]["segments"] = [
        {
            "id": "same-1",
            "label": "重复 1",
            "enabled": True,
            "silence_min_sec": 1800,
            "message": "a",
        },
        {
            "id": "same-2",
            "label": "重复 2",
            "enabled": True,
            "silence_min_sec": 1800,
            "message": "b",
        },
    ]
    atomic_write_yaml(agent_cfg_path("wechat", "workbench.yaml", data_dir), workbench)
    run_enabled_path = agent_cfg_path("wechat", "run_enabled.yaml", data_dir)
    original_run_enabled = {"enabled": True, "marker": "keep-agent-enabled"}
    atomic_write_yaml(run_enabled_path, original_run_enabled)
    _write_state(
        data_dir,
        {
            "agents": {
                "wechat": {
                    "scheduled_touch": {
                        "touches": {"same-1": {"late-customer": now.isoformat()}}
                    }
                }
            }
        },
    )

    import plugins.mxai.cfg.migrations.m0006_cr155_touch_config as migration

    original_write = migration.atomic_write_yaml
    with monkeypatch.context() as scoped:
        scoped.setattr(
            migration,
            "atomic_write_yaml",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("simulated crash")),
        )
        result = run_pending_data_migrations(data_dir)
    assert "cr155-touch-config" not in result["ran"]
    assert "cr155-touch-config" not in read_ledger(data_dir)["applied"]
    assert migrate_hub_to(db, 20) == 20

    monkeypatch.setattr(migration, "atomic_write_yaml", original_write)
    retried = run_pending_data_migrations(data_dir)
    assert "cr155-touch-config" in retried["ran"]
    assert migrate_hub_to(db, 20) == 20
    assert read_yaml(run_enabled_path) == original_run_enabled
    assert not state_path(
        "migration_backups/cr155/wechat/run_enabled.yaml",
        data_dir,
    ).exists()
    migrated = read_yaml(agent_cfg_path("wechat", "workbench.yaml", data_dir))
    assert migrated["scheduler"]["scheduled_touch"]["enabled"] is False
    handoff = json.loads(
        state_path("cr155_touch_migration.json", data_dir).read_text(encoding="utf-8")
    )
    assert handoff["status"] == "imported"
    assert any(item["reason"] == "duplicate_threshold" for item in handoff["conflicts"])
    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM touch_deliveries").fetchone()[0] == 1
    finally:
        conn.close()
