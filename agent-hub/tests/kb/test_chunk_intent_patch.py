"""LT-027.01.03 · PATCH chunk intent + re-slice 继承."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.intent import parse_intent_phrases_json
from plugins.mxai.kb.service import ingest_text, patch_chunk_intent, reslice_document
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


@pytest.fixture
def api_client() -> TestClient:
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    return TestClient(app)


def test_patch_rejects_too_many_phrases(kb_env: Path, api_client: TestClient) -> None:
    result = ingest_text("patch.txt", "第一段内容。\n\n第二段内容。", wait=True, data_dir=kb_env)
    doc_id = result["doc_id"]
    chunks = api_client.get(f"/api/plugins/mxai/kb/documents/{doc_id}/chunks")
    assert chunks.status_code == 200
    chunk_id = chunks.json()["items"][0]["chunk_id"]
    resp = api_client.patch(
        f"/api/plugins/mxai/kb/chunks/{chunk_id}",
        json={"intent_phrases": [f"q{i}" for i in range(6)]},
    )
    assert resp.status_code == 422


def test_patch_updates_intent_not_body_embedding(kb_env: Path) -> None:
    result = ingest_text("emb.txt", "embedding 保持不变的正文段落。", wait=True, data_dir=kb_env)
    doc_id = result["doc_id"]
    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        row = conn.execute(
            "SELECT chunk_id, embedding FROM kb_chunks WHERE doc_id = ? ORDER BY seq LIMIT 1",
            (doc_id,),
        ).fetchone()
        chunk_id, before_emb = row[0], row[1]
    finally:
        conn.close()

    patched = patch_chunk_intent(chunk_id, ["支持本地部署吗"], data_dir=kb_env)
    assert patched["embedding_unchanged"] is True
    assert patched["intent_phrases"] == ["支持本地部署吗"]

    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        after = conn.execute(
            "SELECT embedding, intent_embedding, intent_phrases FROM kb_chunks WHERE chunk_id = ?",
            (chunk_id,),
        ).fetchone()
        assert after[0] == before_emb
        assert after[1]
        assert parse_intent_phrases_json(after[2]) == ["支持本地部署吗"]
    finally:
        conn.close()


def test_reslice_inherits_intent_by_seq(kb_env: Path) -> None:
    result = ingest_text(
        "inherit.txt", "Alpha 段落内容。\n\nBeta 段落内容。", wait=True, data_dir=kb_env
    )
    doc_id = result["doc_id"]
    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        row = conn.execute(
            "SELECT chunk_id FROM kb_chunks WHERE doc_id = ? ORDER BY seq LIMIT 1",
            (doc_id,),
        ).fetchone()
        first_id = row[0]
    finally:
        conn.close()

    patch_chunk_intent(first_id, ["继承测试问法"], data_dir=kb_env)
    reslice_document(doc_id, data_dir=kb_env)

    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        row = conn.execute(
            "SELECT intent_phrases FROM kb_chunks WHERE doc_id = ? ORDER BY seq LIMIT 1",
            (doc_id,),
        ).fetchone()
        assert parse_intent_phrases_json(row[0]) == ["继承测试问法"]
    finally:
        conn.close()
