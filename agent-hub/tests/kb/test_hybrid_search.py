"""LT-021.07.01 · 混合检索."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.engine.search import last_vector_candidate_count, search_chunks
from plugins.mxai.kb.embeddings import embedding_to_json, embed_text
from plugins.mxai.kb.service import ingest_text, search_test, set_kb_retrieval
from plugins.mxai.kb.storage.kb_repo import init_kb_schema
from plugins.mxai.kb.worker import KbWorker


@pytest.fixture
def kb_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    init_kb_schema(mxai_db_path("kb.db", data_dir))
    KbWorker.reset()
    KbWorker.get().start()
    return data_dir


def test_search_test_score_source(kb_env: Path) -> None:
    del kb_env
    ingest_text("hybrid.txt", "混合检索关键词 zeta-unique。", wait=True)
    result = search_test("zeta-unique", limit=5)
    assert result["items"]
    assert result["items"][0].get("score_source") in {"fts", "vector", "hybrid"}


def test_hybrid_does_not_vector_scan_all_chunks(kb_env: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        conn.execute("INSERT INTO kb_partitions (partition_id, name) VALUES (1, 'default')")
        conn.execute(
            """
            INSERT INTO kb_documents (doc_id, partition_id, file_path, display_name, content_md5, current_version)
            VALUES ('doc_bulk', 1, 'bulk.txt', 'bulk.txt', 'md5bulk', 1)
            """
        )
        for i in range(200):
            text = f"noise chunk {i}"
            cid = f"chk_{uuid.uuid4().hex[:10]}"
            conn.execute(
                """
                INSERT INTO kb_chunks (
                    chunk_id, doc_id, partition_id, seq, text, embedding,
                    content_version, unit_type, heading_path, quality_flags
                ) VALUES (?, 'doc_bulk', 1, ?, ?, ?, 1, 'paragraph', '', '[]')
                """,
                (cid, i, text, embedding_to_json(embed_text(text))),
            )
            conn.execute(
                "INSERT INTO kb_chunks_fts (chunk_id, doc_id, partition_id, content_version, intent_phrases, text) VALUES (?, 'doc_bulk', 1, 1, '', ?)",
                (cid, text),
            )
        conn.execute(
            """
            INSERT INTO kb_chunks (
                chunk_id, doc_id, partition_id, seq, text, embedding,
                content_version, unit_type, heading_path, quality_flags
            ) VALUES ('chk_target', 'doc_bulk', 1, 999, 'needle-target-phrase', ?, 1, 'paragraph', '', '[]')
            """,
            (embedding_to_json(embed_text("needle-target-phrase")),),
        )
        conn.execute(
            """
            INSERT INTO kb_chunks_fts (chunk_id, doc_id, partition_id, content_version, intent_phrases, text)
            VALUES ('chk_target', 'doc_bulk', 1, 1, '', 'needle-target-phrase')
            """
        )
        conn.commit()
    finally:
        conn.close()

    set_kb_retrieval({"mode": "hybrid"}, data_dir=kb_env)
    hits = search_chunks("needle-target", limit=3, data_dir=kb_env)
    assert hits
    assert last_vector_candidate_count() < 200


def test_retrieval_persisted_to_yaml(kb_env: Path) -> None:
    set_kb_retrieval({"mode": "fts_only", "fts_weight": 0.9}, data_dir=kb_env)
    yaml_path = kb_env / "shared" / "knowledge" / "kb_plugin.yaml"
    assert yaml_path.is_file()
    text = yaml_path.read_text(encoding="utf-8")
    assert "fts_only" in text

    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)
    resp = client.get("/api/plugins/mxai/kb/retrieval")
    assert resp.json()["item"]["mode"] == "fts_only"
