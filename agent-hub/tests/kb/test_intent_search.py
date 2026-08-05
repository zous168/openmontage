"""LT-027.01.02 · 双向量检索 + search-test matched_via."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.embeddings import embed_text, embedding_to_json
from plugins.mxai.kb.engine.search import enrich_search_debug_scores, search_chunks
from plugins.mxai.kb.intent import intent_phrases_to_json, parse_intent_phrases_json
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
    conn = sqlite3.connect(mxai_db_path("kb.db", data_dir))
    try:
        conn.execute("INSERT INTO kb_partitions (partition_id, name) VALUES (1, 'default')")
        conn.commit()
    finally:
        conn.close()
    return data_dir


def _insert_chunk(
    conn: sqlite3.Connection,
    *,
    doc_id: str,
    chunk_id: str,
    seq: int,
    text: str,
    intent_phrases: list[str],
) -> None:
    phrases_json = intent_phrases_to_json(intent_phrases)
    intent_emb = (
        embedding_to_json(embed_text(" ".join(intent_phrases))) if intent_phrases else None
    )
    conn.execute(
        """
        INSERT INTO kb_chunks (
            chunk_id, doc_id, partition_id, seq, text, embedding,
            intent_phrases, intent_embedding,
            content_version, unit_type, heading_path, quality_flags
        ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, 1, 'paragraph', '', '[]')
        """,
        (
            chunk_id,
            doc_id,
            seq,
            text,
            embedding_to_json(embed_text(text)),
            phrases_json,
            intent_emb,
        ),
    )
    intent_fts = " ".join(intent_phrases)
    conn.execute(
        """
        INSERT INTO kb_chunks_fts (
            chunk_id, doc_id, partition_id, content_version, intent_phrases, text
        ) VALUES (?, ?, 1, 1, ?, ?)
        """,
        (chunk_id, doc_id, intent_fts, text),
    )


def test_intent_chunk_ranks_above_body_only(kb_env: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        conn.execute(
            """
            INSERT INTO kb_documents (doc_id, partition_id, file_path, display_name, content_md5, current_version, sliced_at)
            VALUES ('doc_intent', 1, 'intent.txt', 'intent.txt', 'md5i', 1, datetime('now'))
            """
        )
        _insert_chunk(
            conn,
            doc_id="doc_intent",
            chunk_id="chk_intent",
            seq=0,
            text="私有化版本提供两档授权方案，可按席位计费。",
            intent_phrases=["支持本地部署吗"],
        )
        _insert_chunk(
            conn,
            doc_id="doc_intent",
            chunk_id="chk_body",
            seq=1,
            text="支持本地部署吗需要专业版许可与本地引擎。",
            intent_phrases=[],
        )
        conn.commit()
    finally:
        conn.close()

    set_kb_retrieval({"mode": "vector_only", "min_score": 0.0}, data_dir=kb_env)
    hits = search_chunks("支持本地部署吗", limit=5, data_dir=kb_env)
    assert len(hits) >= 2
    assert hits[0]["chunk_id"] == "chk_intent"
    assert hits[0].get("matched_via") in {"intent", "hybrid"}


def test_empty_intent_falls_back_to_text_vector(kb_env: Path) -> None:
    ingest_text("plain.txt", "普通正文检索 marker-plain-body。", wait=True)
    hits = search_chunks("marker-plain-body", limit=1, data_dir=kb_env)
    assert hits
    assert hits[0].get("matched_via", "text") == "text"


def test_search_test_includes_matched_via(kb_env: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        conn.execute(
            """
            INSERT INTO kb_documents (doc_id, partition_id, file_path, display_name, content_md5, current_version, sliced_at)
            VALUES ('doc_st', 1, 'st.txt', 'st.txt', 'md5st', 1, datetime('now'))
            """
        )
        _insert_chunk(
            conn,
            doc_id="doc_st",
            chunk_id="chk_st",
            seq=0,
            text="无关正文 filler content here.",
            intent_phrases=["客户问价怎么回"],
        )
        conn.commit()
    finally:
        conn.close()

    result = search_test("客户问价怎么回", limit=3, data_dir=kb_env)
    assert result["items"]
    assert result["items"][0].get("matched_via") in {"intent", "hybrid", "text"}
    assert "sim_text" in result["items"][0]
    assert "sim_intent" in result["items"][0]


def test_enrich_search_debug_scores_fills_missing(kb_env: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        conn.execute(
            """
            INSERT INTO kb_documents (doc_id, partition_id, file_path, display_name, content_md5, current_version, sliced_at)
            VALUES ('doc_en', 1, 'en.txt', 'en.txt', 'md5en', 1, datetime('now'))
            """
        )
        _insert_chunk(
            conn,
            doc_id="doc_en",
            chunk_id="chk_en",
            seq=0,
            text="正文内容 local engine deployment",
            intent_phrases=["如何使用本地引擎"],
        )
        conn.commit()
    finally:
        conn.close()

    raw = [{"chunk_id": "chk_en", "score": 0.5, "score_source": "fts"}]
    enriched = enrich_search_debug_scores("本地引擎", raw, data_dir=kb_env)
    assert enriched[0]["sim_text"] is not None
    assert enriched[0]["sim_intent"] is not None
    assert enriched[0].get("intent_phrases") == ["如何使用本地引擎"]
