"""Tests for mxai database admin service and routes."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentRegistry
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.db_admin.service import (
    DatabaseAdminError,
    browse_table,
    delete_table_rows,
    list_project_databases,
    list_tables,
    resolve_database,
    run_select_query,
    update_table_row,
    validate_select_sql,
)
from plugins.mxai.registry.databases import DatabaseRegistry


@pytest.fixture
def isolated_hub_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub_data"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    # HTTP 库管路由经 resolve_hub_data_dir_path，不读 HUB_DATA_DIR env
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.db_admin.service.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    profiles_root = data_dir / "profiles"
    profiles_root.mkdir()
    main_dir = profiles_root / "main"
    main_dir.mkdir()
    (main_dir / "config.yaml").write_text("model: test\n", encoding="utf-8")
    return data_dir


@pytest.fixture(autouse=True)
def reset_registries() -> None:
    AgentRegistry.clear()
    from plugins.mxai._bootstrap_imports import load_registries
    from plugins.mxai.agents._register import register_channel_agents

    load_registries()
    register_channel_agents()
    yield
    AgentRegistry.clear()


@pytest.fixture
def bootstrapped_hub(isolated_hub_data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    def fake_create_profile(name: str, **kwargs: object) -> Path:
        profile_dir = isolated_hub_data_dir / "profiles" / name
        profile_dir.mkdir(parents=True, exist_ok=True)
        if not (profile_dir / "config.yaml").exists():
            (profile_dir / "config.yaml").write_text("model: test\n", encoding="utf-8")
        return profile_dir

    monkeypatch.setattr("hermes_cli.profiles.create_profile", fake_create_profile)
    monkeypatch.setattr(
        "hermes_cli.profiles.profile_exists",
        lambda name: (isolated_hub_data_dir / "profiles" / name).is_dir(),
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: isolated_hub_data_dir / "profiles" / name,
    )
    ensure_runtime_bootstrap(isolated_hub_data_dir)
    return isolated_hub_data_dir


def test_list_project_databases_includes_path(bootstrapped_hub: Path) -> None:
    items = list_project_databases(data_dir=bootstrapped_hub)
    files = {item["file"] for item in items if item["category"] == "mxai"}
    assert files == {d.file for d in DatabaseRegistry.all()}
    hub = next(x for x in items if x["id"] == "hub.db")
    assert hub["path"].endswith("hub.db")
    assert hub["path_display"] == "{HUB_DATA_DIR}/plugins/mxai/data/hub.db"
    assert hub["label"] == "业务主库"
    assert hub["schema_version"] is not None
    assert hub["schema_version"] >= 1


def test_schema_version_from_schema_migrations_table(bootstrapped_hub: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("hub.db", bootstrapped_hub))
    try:
        conn.execute(
            """
            INSERT INTO schema_migrations (id, version) VALUES (1, 42)
            ON CONFLICT(id) DO UPDATE SET version = excluded.version
            """
        )
        conn.commit()
    finally:
        conn.close()

    items = list_project_databases(data_dir=bootstrapped_hub)
    worklog = next(x for x in items if x["id"] == "hub.db")
    assert worklog["schema_version"] == 42


def test_schema_version_from_hermes_schema_version_table(bootstrapped_hub: Path) -> None:
    path = bootstrapped_hub / "state.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (15)")
        conn.commit()
    finally:
        conn.close()

    items = list_project_databases(data_dir=bootstrapped_hub)
    hermes = next(x for x in items if x["id"] == "hermes/state.db")
    assert hermes["schema_version"] == 15


def test_profile_schema_version_ignores_schema_migrations(bootstrapped_hub: Path) -> None:
    profile_state = bootstrapped_hub / "profiles" / "main" / "state.db"
    profile_state.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(profile_state)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, source TEXT NOT NULL)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                version INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "INSERT INTO schema_migrations (id, version) VALUES (1, 99) "
            "ON CONFLICT(id) DO UPDATE SET version = excluded.version"
        )
        conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)")
        conn.execute("DELETE FROM schema_version")
        conn.execute("INSERT INTO schema_version (version) VALUES (12)")
        conn.commit()
    finally:
        conn.close()

    items = list_project_databases(data_dir=bootstrapped_hub)
    profile = next(x for x in items if x["id"] == "hermes/profiles/main/state.db")
    assert profile["schema_version"] == 12


def test_discover_profile_state_db(bootstrapped_hub: Path) -> None:
    profile_state = bootstrapped_hub / "profiles" / "main" / "state.db"
    conn = sqlite3.connect(profile_state)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, source TEXT NOT NULL)"
        )
        conn.commit()
    finally:
        conn.close()

    items = list_project_databases(data_dir=bootstrapped_hub)
    hermes_ids = {item["id"] for item in items if item["category"] == "hermes"}
    assert "hermes/profiles/main/state.db" in hermes_ids


def test_list_tables_has_chinese_labels(bootstrapped_hub: Path) -> None:
    tables = list_tables("hub.db", data_dir=bootstrapped_hub)
    wl = next(t for t in tables if t["name"] == "work_logs")
    assert wl["label"] == "工作日志"
    assert wl["readonly_tag"] is None


def test_is_fts_table_matches_trigram_shadow_names() -> None:
    from plugins.mxai.db_admin.service import (
        _is_fts_shadow_table,
        _is_fts_table,
        _open_readonly,
        _table_readonly_tag,
    )
    import sqlite3
    from pathlib import Path
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "fts.db"
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE VIRTUAL TABLE messages_fts_trigram USING fts5(content, tokenize='trigram')"
        )
        conn.commit()
        conn.close()
        ro = _open_readonly(path)
        try:
            assert _is_fts_table(ro, "messages_fts_trigram") is True
            assert _is_fts_shadow_table("messages_fts_trigram_config") is True
            assert _table_readonly_tag(ro, "messages_fts_trigram_config") == "system"
            assert _table_readonly_tag(ro, "messages_fts_trigram") == "readonly"
            assert _is_fts_table(ro, "messages") is False
        finally:
            ro.close()


def test_list_tables_marks_fts_readonly(bootstrapped_hub: Path) -> None:
    tables = list_tables("kb.db", data_dir=bootstrapped_hub)
    fts = next(t for t in tables if t["name"] == "kb_chunks_fts")
    assert fts["editable"] is False
    assert fts["readonly_tag"] == "readonly"


def test_browse_table_column_meta(bootstrapped_hub: Path) -> None:
    page1 = browse_table(
        "hub.db",
        "schema_migrations",
        page=1,
        page_size=1,
        data_dir=bootstrapped_hub,
    )
    assert page1["table_label"]
    assert page1["column_meta"]
    assert any(c["name"] == "version" for c in page1["column_meta"])
    version_col = next(c for c in page1["column_meta"] if c["name"] == "version")
    assert "editable" in version_col
    assert "input_type" in version_col


def test_browse_table_order_by(bootstrapped_hub: Path) -> None:
    asc = browse_table(
        "hub.db",
        "schema_migrations",
        page=1,
        page_size=10,
        order_by="version ASC",
        data_dir=bootstrapped_hub,
    )
    desc = browse_table(
        "hub.db",
        "schema_migrations",
        page=1,
        page_size=10,
        order_by="version DESC",
        data_dir=bootstrapped_hub,
    )
    asc_versions = [row["version"] for row in asc["rows"]]
    desc_versions = [row["version"] for row in desc["rows"]]
    assert asc_versions == sorted(asc_versions)
    assert desc_versions == sorted(desc_versions, reverse=True)


def test_run_select_query_order_by(bootstrapped_hub: Path) -> None:
    result = run_select_query(
        "hub.db",
        "SELECT version FROM schema_migrations",
        page=1,
        page_size=10,
        order_by="version DESC",
        data_dir=bootstrapped_hub,
    )
    versions = [row["version"] for row in result["rows"]]
    assert versions == sorted(versions, reverse=True)


def test_browse_table_rejects_invalid_order_column(bootstrapped_hub: Path) -> None:
    with pytest.raises(DatabaseAdminError, match="unknown order column"):
        browse_table(
            "hub.db",
            "schema_migrations",
            order_by="not_a_column DESC",
            data_dir=bootstrapped_hub,
        )


def test_timestamp_column_value_formats(bootstrapped_hub: Path) -> None:
    customers = browse_table(
        "hub.db",
        "wechat_contacts",
        page=1,
        page_size=1,
        data_dir=bootstrapped_hub,
    )
    created_text = next(c for c in customers["column_meta"] if c["name"] == "created_at")
    assert created_text["input_type"] == "datetime"
    assert created_text["value_format"] == "iso"


def test_hub_has_no_queue_tasks_table(bootstrapped_hub: Path) -> None:
    names = {t["name"] for t in list_tables("hub.db", data_dir=bootstrapped_hub)}
    assert "queue_tasks" not in names


def test_customers_created_at_readonly(bootstrapped_hub: Path) -> None:
    page = browse_table(
        "hub.db",
        "wechat_contacts",
        page=1,
        page_size=1,
        data_dir=bootstrapped_hub,
    )
    created = next(c for c in page["column_meta"] if c["name"] == "created_at")
    uid = next(c for c in page["column_meta"] if c["name"] == "customer_uid")
    assert created["editable"] is False
    assert created["input_type"] == "datetime"
    assert uid["editable"] is False
    assert uid["pk"] is True


def test_update_rejects_readonly_column(bootstrapped_hub: Path) -> None:
    with pytest.raises(DatabaseAdminError, match="read-only"):
        update_table_row(
            "hub.db",
            "wechat_contacts",
            original={"customer_uid": "mock-1"},
            values={"created_at": "2099-01-01T00:00:00"},
            data_dir=bootstrapped_hub,
        )


def test_update_table_row(bootstrapped_hub: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("hub.db", bootstrapped_hub))
    try:
        conn.execute(
            """
            INSERT INTO work_logs (
                log_id, op_time, profile_id, op_type, op_object,
                exec_status, fail_reason, elapsed_ms, task_id
            ) VALUES (?, datetime('now'), 'main', 'test', 'obj', '成功', '', 1, 't1')
            """,
            ("test-log-1",),
        )
        conn.commit()
    finally:
        conn.close()

    update_table_row(
        "hub.db",
        "work_logs",
        original={
            "log_id": "test-log-1",
            "profile_id": "main",
            "op_type": "test",
            "exec_status": "成功",
        },
        values={"exec_status": "失败", "fail_reason": "edited"},
        data_dir=bootstrapped_hub,
    )

    conn = sqlite3.connect(mxai_db_path("hub.db", bootstrapped_hub))
    try:
        row = conn.execute(
            "SELECT exec_status, fail_reason FROM work_logs WHERE log_id = ?",
            ("test-log-1",),
        ).fetchone()
        assert row[0] == "失败"
        assert row[1] == "edited"
    finally:
        conn.close()


def test_delete_table_row(bootstrapped_hub: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("hub.db", bootstrapped_hub))
    try:
        conn.execute(
            """
            INSERT INTO work_logs (
                log_id, op_time, profile_id, op_type, op_object,
                exec_status, fail_reason, elapsed_ms, task_id
            ) VALUES (?, datetime('now'), 'main', 'test', 'obj', '成功', '', 1, 't-del-1')
            """,
            ("test-log-del-1",),
        )
        conn.commit()
    finally:
        conn.close()

    page = browse_table(
        "hub.db",
        "work_logs",
        page=1,
        page_size=50,
        data_dir=bootstrapped_hub,
    )
    row = next(r for r in page["rows"] if r["log_id"] == "test-log-del-1")
    result = delete_table_rows(
        "hub.db",
        "work_logs",
        rows=[{"log_id": row["log_id"], "profile_id": row["profile_id"]}],
        data_dir=bootstrapped_hub,
    )
    assert result["deleted"] == 1

    conn = sqlite3.connect(mxai_db_path("hub.db", bootstrapped_hub))
    try:
        count = conn.execute(
            "SELECT COUNT(*) FROM work_logs WHERE log_id = ?",
            ("test-log-del-1",),
        ).fetchone()[0]
        assert count == 0
    finally:
        conn.close()


def test_delete_table_rows_bulk(bootstrapped_hub: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("hub.db", bootstrapped_hub))
    try:
        for idx in (1, 2):
            conn.execute(
                """
                INSERT INTO work_logs (
                    log_id, op_time, profile_id, op_type, op_object,
                    exec_status, fail_reason, elapsed_ms, task_id
                ) VALUES (?, datetime('now'), 'main', 'test', 'obj', '成功', '', 1, ?)
                """,
                (f"test-log-bulk-{idx}", f"t-bulk-{idx}"),
            )
        conn.commit()
    finally:
        conn.close()

    page = browse_table(
        "hub.db",
        "work_logs",
        page=1,
        page_size=50,
        data_dir=bootstrapped_hub,
    )
    targets = [
        {"log_id": r["log_id"], "profile_id": r["profile_id"]}
        for r in page["rows"]
        if str(r["log_id"]).startswith("test-log-bulk-")
    ]
    result = delete_table_rows(
        "hub.db",
        "work_logs",
        rows=targets,
        data_dir=bootstrapped_hub,
    )
    assert result["deleted"] == 2


def test_delete_rejects_readonly_table(bootstrapped_hub: Path) -> None:
    with pytest.raises(DatabaseAdminError, match="not editable"):
        delete_table_rows(
            "kb.db",
            "kb_chunks_fts",
            rows=[{"rowid": 1}],
            data_dir=bootstrapped_hub,
        )


def test_validate_select_sql_rejects_writes() -> None:
    with pytest.raises(DatabaseAdminError):
        validate_select_sql("DELETE FROM work_logs")
    with pytest.raises(DatabaseAdminError):
        validate_select_sql("SELECT 1; SELECT 2")


def test_run_select_simple_table_editable(bootstrapped_hub: Path) -> None:
    result = run_select_query(
        "hub.db",
        "SELECT * FROM work_logs",
        data_dir=bootstrapped_hub,
    )
    assert result["editable"] is True
    assert result["table"] == "work_logs"
    assert any(c.get("input_type") for c in result["column_meta"])


def test_run_select_aggregate_not_editable(bootstrapped_hub: Path) -> None:
    result = run_select_query(
        "hub.db",
        "SELECT COUNT(*) AS n FROM work_logs",
        data_dir=bootstrapped_hub,
    )
    assert result["editable"] is False


def test_resolve_hermes_db_id(bootstrapped_hub: Path) -> None:
    path = bootstrapped_hub / "state.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS t(x INTEGER)")
    conn.commit()
    conn.close()
    target = resolve_database("hermes/state.db", data_dir=bootstrapped_hub)
    assert target.category == "hermes"
    assert target.path == path


def test_database_routes(bootstrapped_hub: Path) -> None:
    from plugins.mxai.api.database import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/mxai")
    client = TestClient(app)

    resp = client.get("/api/plugins/mxai/databases")
    assert resp.status_code == 200
    assert len(resp.json()["items"]) >= 3

    resp = client.get("/api/plugins/mxai/databases/hub.db/tables")
    assert resp.status_code == 200
    assert any(t["name"] == "work_logs" for t in resp.json()["items"])

    resp = client.get(
        "/api/plugins/mxai/databases/hub.db/tables/work_logs/rows?page=1&page_size=10&order_by=created_at%20DESC"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "column_meta" in body

    resp = client.post(
        "/api/plugins/mxai/databases/hub.db/query",
        json={
            "sql": "SELECT version FROM schema_migrations",
            "page": 1,
            "page_size": 10,
            "order_by": "version DESC",
        },
    )
    assert resp.status_code == 200

    resp = client.post(
        "/api/plugins/mxai/databases/hub.db/query",
        json={"sql": "SELECT COUNT(*) AS n FROM work_logs", "page": 1, "page_size": 10},
    )
    assert resp.status_code == 200

    conn = sqlite3.connect(mxai_db_path("hub.db", bootstrapped_hub))
    try:
        conn.execute(
            """
            INSERT INTO work_logs (
                log_id, op_time, profile_id, op_type, op_object,
                exec_status, fail_reason, elapsed_ms, task_id
            ) VALUES (?, datetime('now'), 'main', 'test', 'obj', '成功', '', 1, 't-route')
            """,
            ("route-del-1",),
        )
        conn.commit()
    finally:
        conn.close()

    resp = client.request(
        "DELETE",
        "/api/plugins/mxai/databases/hub.db/tables/work_logs/rows",
        json={
            "rows": [
                {
                    "log_id": "route-del-1",
                }
            ]
        },
    )
    assert resp.status_code == 200
    assert resp.json()["deleted"] == 1

    resp = client.post(
        "/api/plugins/mxai/databases/not-a.db/query",
        json={"sql": "SELECT 1", "page": 1, "page_size": 10},
    )
    assert resp.status_code == 400
