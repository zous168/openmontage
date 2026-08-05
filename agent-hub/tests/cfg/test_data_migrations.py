"""CR-145 数据迁移框架（账本记账、bootstrap 跑一次、幂等）单测。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.mxai.cfg.data_migrations import (
    discover_migrations,
    read_ledger,
    run_pending_data_migrations,
)
from plugins.mxai.cfg.paths import (
    global_cfg_path,
    legacy_db_path,
    mxai_db_path,
    plugin_cfg_dir,
    state_path,
)


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    return tmp_path


def _seed_legacy(data_dir: Path) -> None:
    prof = data_dir / "profiles" / "douyin"
    prof.mkdir(parents=True, exist_ok=True)
    (prof / "workbench.yaml").write_text("scheduler: {}\n", encoding="utf-8")
    (data_dir / "client_settings.yaml").write_text("theme: dark\n", encoding="utf-8")
    (data_dir / "scheduler_state.json").write_text("{}", encoding="utf-8")
    conn = sqlite3.connect(legacy_db_path("hub.db", data_dir))
    try:
        conn.execute(
            "CREATE TABLE customers ("
            "customer_uid TEXT PRIMARY KEY, profile_id TEXT NOT NULL, "
            "display_name TEXT, created_at TEXT NOT NULL, last_inbound_at TEXT)"
        )
        conn.commit()
    finally:
        conn.close()


def _all_migration_ids() -> set[str]:
    return {m.id for m in discover_migrations()}


def test_first_run_relocates_and_records_ledger(data_dir: Path) -> None:
    _seed_legacy(data_dir)

    result = run_pending_data_migrations(data_dir)

    assert set(result["ran"]) == _all_migration_ids()
    assert result["ran"]["cr145-cfg-relocate"] == 3  # workbench + client_settings + scheduler_state
    assert result["ran"]["cr145-db-relocate"] == 1

    # 文件已搬到新位置，旧位置清空
    assert (plugin_cfg_dir("douyin", data_dir) / "workbench.yaml").is_file()
    assert global_cfg_path("client_settings.yaml", data_dir).is_file()
    assert state_path("scheduler_state.json", data_dir).is_file()
    assert mxai_db_path("hub.db", data_dir).is_file()
    assert not (data_dir / "profiles" / "douyin" / "workbench.yaml").exists()
    assert not legacy_db_path("hub.db", data_dir).exists()

    # 账本记录了全部已应用迁移
    ledger = read_ledger(data_dir)
    assert set(ledger["applied"]) == _all_migration_ids()
    assert ledger["applied"]["cr145-cfg-relocate"]["moved"] == 3


def test_second_run_is_noop_via_ledger(data_dir: Path) -> None:
    _seed_legacy(data_dir)
    run_pending_data_migrations(data_dir)

    # 二次调用：账本已记账 → 全部 skip，不再执行搬迁
    again = run_pending_data_migrations(data_dir)
    assert again["ran"] == {}
    assert set(again["skipped"]) == _all_migration_ids()


def test_nothing_to_migrate_still_records_ledger(data_dir: Path) -> None:
    # 全新环境（无旧文件）：迁移仍记账，避免每次开机重扫
    result = run_pending_data_migrations(data_dir)
    assert set(result["ran"]) == _all_migration_ids()
    assert all(result["ran"][mid] == 0 for mid in _all_migration_ids())
    ledger = read_ledger(data_dir)
    assert set(ledger["applied"]) == _all_migration_ids()


def test_ledger_survives_partial_reseed_of_legacy(data_dir: Path) -> None:
    # 迁移完成记账后，旧代码又把文件写回旧位置：账本已记账 → 不再回迁（run-once 语义）
    _seed_legacy(data_dir)
    run_pending_data_migrations(data_dir)

    (data_dir / "profiles" / "douyin" / "workbench.yaml").write_text("stale: 1\n", encoding="utf-8")
    result = run_pending_data_migrations(data_dir)
    assert result["ran"] == {}
    # 旧位置的这份陈旧文件不被框架回迁（read-fallback 另行兜底读取，与迁移无关）
    assert (data_dir / "profiles" / "douyin" / "workbench.yaml").is_file()
