"""LT-004.07.01：向导公司基础信息 hub.db 持久化（enterprise_profile 单表）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.storage.schema import read_schema_version
from plugins.mxai.wizard.persist import load_enterprise, load_product


@pytest.fixture
def wizard_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    profiles = data_dir / "profiles"
    profiles.mkdir()
    (profiles / "main").mkdir()
    (profiles / "main" / "config.yaml").write_text("model: test\n", encoding="utf-8")
    ensure_runtime_bootstrap(data_dir)
    return data_dir


def test_wizard_put_persists_hub_db(wizard_env: Path) -> None:
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)
    client.put(
        "/api/plugins/mxai/wizard/state",
        json={
            "enterprise": {
                "name": "Acme Corp",
                "contact_person": "Alice",
                "product_desc": "MxAI Suite",
                "business_scope": "营销自动化",
            },
        },
    )
    ent = load_enterprise(data_dir=wizard_env)
    prod = load_product(data_dir=wizard_env)
    assert ent.get("name") == "Acme Corp"
    assert ent.get("product_desc") == "MxAI Suite"
    assert prod.get("product_desc") == "MxAI Suite"
    conn = sqlite3.connect(mxai_db_path("hub.db", wizard_env))
    try:
        assert read_schema_version(conn) >= 18
        rows = conn.execute("SELECT id, product_desc FROM enterprise_profile").fetchall()
        assert len(rows) == 1
        assert rows[0][1] == "MxAI Suite"
        dead = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='product_info'"
        ).fetchall()
        assert dead == []
    finally:
        conn.close()


def test_wizard_put_product_merges_into_enterprise(wizard_env: Path) -> None:
    """兼容旧客户端仍传 product 时并入同一行。"""
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)
    client.put(
        "/api/plugins/mxai/wizard/state",
        json={
            "enterprise": {"name": "Acme Corp"},
            "product": {"name": "MxAI Suite", "business_scope": "获客"},
        },
    )
    ent = load_enterprise(data_dir=wizard_env)
    assert ent.get("enterprise_name") == "Acme Corp" or ent.get("name") == "Acme Corp"
    assert ent.get("product_desc") == "MxAI Suite"
    assert ent.get("business_scope") == "获客"


def test_wizard_self_check_reads_db(wizard_env: Path) -> None:
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)
    client.put(
        "/api/plugins/mxai/wizard/state",
        json={"enterprise": {"name": "E1", "product_desc": "P1"}},
    )
    check = client.post("/api/plugins/mxai/wizard/self-check").json()
    by_name = {c["name"]: c["ok"] for c in check["checks"]}
    assert "product" not in by_name
    assert by_name.get("enterprise") is True
    assert by_name.get("bootstrap") is True
