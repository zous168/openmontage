"""LT-027.01.01 · kb schema v7 intent 列."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.engine.search import search_chunks
from plugins.mxai.kb.service import ingest_text
from plugins.mxai.kb.storage.kb_repo import init_kb_schema
from plugins.mxai.storage.schema import read_schema_version
from plugins.mxai.kb.worker import KbWorker
import sqlite3


@pytest.fixture
def kb_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    init_kb_schema(mxai_db_path("kb.db", data_dir))
    KbWorker.reset()
    KbWorker.get().start()
    return data_dir


def test_schema_v7_intent_columns(kb_env: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        assert read_schema_version(conn) == 7
        chunk_cols = {row[1] for row in conn.execute("PRAGMA table_info(kb_chunks)").fetchall()}
        assert "intent_phrases" in chunk_cols
        assert "intent_embedding" in chunk_cols
        fts_cols = {row[1] for row in conn.execute("PRAGMA table_info(kb_chunks_fts)").fetchall()}
        assert "intent_phrases" in fts_cols
        assert "text" in fts_cols
    finally:
        conn.close()


def test_legacy_chunks_without_intent_still_search(kb_env: Path) -> None:
    ingest_text("legacy.txt", "旧库迁移后仍可检索 unique-legacy-token。", wait=True)
    hits = search_chunks("unique-legacy-token", limit=3, data_dir=kb_env)
    assert hits
    assert hits[0]["score"] > 0
