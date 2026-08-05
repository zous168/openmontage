"""LT-021.05.03 · 检索 SSOT 仅当前 content_version."""

from __future__ import annotations

import sqlite3
import uuid
from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.engine.search import search_chunks
from plugins.mxai.kb.service import ingest_text
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


def _db(data_dir: Path) -> Path:
    return mxai_db_path("kb.db", data_dir)


def test_stale_content_version_not_searchable(kb_env: Path) -> None:
    result = ingest_text("search.txt", "旧版唯一关键词 alpha-beta。", wait=True, data_dir=kb_env)
    doc_id = result["doc_id"]
    ingest_text(
        "search.txt",
        "新版唯一关键词 gamma-delta。",
        file_path="inline:search.txt",
        wait=True,
        data_dir=kb_env,
    )
    conn = sqlite3.connect(_db(kb_env))
    try:
        conn.execute(
            """
            INSERT INTO kb_chunks (
                chunk_id, doc_id, partition_id, seq, text, embedding,
                content_version, unit_type, heading_path, quality_flags
            ) VALUES (?, ?, 1, 99, ?, '[]', 1, 'paragraph', '', '[]')
            """,
            (f"chk_{uuid.uuid4().hex[:8]}", doc_id, "旧版唯一关键词 alpha-beta。"),
        )
        conn.commit()
    finally:
        conn.close()

    hits = search_chunks("alpha-beta", limit=5, data_dir=kb_env)
    texts = [h["text"] for h in hits]
    assert not any("alpha-beta" in t for t in texts)

    hits_new = search_chunks("gamma-delta", limit=5, data_dir=kb_env)
    assert hits_new
