"""FR-KB-16 · 切片策略过期计数（排除无 chunk 的占位文档）."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.config_store import count_stale_documents
from plugins.mxai.kb.service import ingest_text
from plugins.mxai.kb.storage.kb_repo import init_kb_schema
from plugins.mxai.kb.worker import KbWorker
from plugins.mxai.storage.schema import write_schema_version

MD = """# A

段落一。

# B

段落二。
"""


@pytest.fixture
def kb_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    init_kb_schema(mxai_db_path("kb.db", data_dir))
    KbWorker.reset()
    KbWorker.get().start()
    return data_dir


def _seed_ghost_doc(data_dir: Path) -> None:
    conn = sqlite3.connect(mxai_db_path("kb.db", data_dir))
    try:
        conn.execute(
            """
            INSERT INTO kb_documents (
                doc_id, partition_id, file_path, current_version, sliced_at, chunking_strategy_version
            ) VALUES ('ghost', 1, 'demo/ghost.md', 1, datetime('now'), 0)
            """
        )
        conn.commit()
    finally:
        conn.close()


def test_ghost_doc_without_chunks_not_stale(kb_env: Path) -> None:
    _seed_ghost_doc(kb_env)
    assert count_stale_documents(kb_env) == 0


def test_fresh_ingest_not_stale(kb_env: Path) -> None:
    ingest_text("fresh.md", MD, wait=True, data_dir=kb_env)
    assert count_stale_documents(kb_env) == 0


def test_v6_syncs_false_stale_from_max_chars_bump(kb_env: Path) -> None:
    """CR-102：仅改长度误升 strategy_version 时，v6 对齐 doc 标记、无需 re-slice."""
    ingest_text("sync.md", MD, wait=True, data_dir=kb_env)
    conn = sqlite3.connect(mxai_db_path("kb.db", kb_env))
    try:
        conn.execute(
            "INSERT INTO kb_settings (key, value) VALUES ('chunking', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (
                '{"strategy":"semantic_paragraph","max_chunk_chars":600,'
                '"strategy_version":2}',
            ),
        )
        conn.execute(
            "UPDATE kb_documents SET chunking_strategy_version = 1 WHERE doc_id IS NOT NULL"
        )
        write_schema_version(conn, 5)
        conn.commit()
    finally:
        conn.close()
    assert count_stale_documents(kb_env) == 1
    init_kb_schema(mxai_db_path("kb.db", kb_env))
    assert count_stale_documents(kb_env) == 0
