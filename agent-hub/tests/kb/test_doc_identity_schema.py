"""LT-021.05.01 · kb schema v4."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.storage.kb_repo import init_kb_schema


@pytest.fixture
def kb_schema_env(tmp_path: Path) -> Path:
    db_path = mxai_db_path("kb.db", tmp_path)
    init_kb_schema(db_path)
    return db_path


def test_documents_have_content_md5(kb_schema_env: Path) -> None:
    conn = sqlite3.connect(kb_schema_env)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(kb_documents)").fetchall()}
        assert "content_md5" in cols
        assert "display_name" in cols
        assert "chunking_strategy_version" in cols
    finally:
        conn.close()


def test_chunks_have_content_version(kb_schema_env: Path) -> None:
    conn = sqlite3.connect(kb_schema_env)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(kb_chunks)").fetchall()}
        assert "content_version" in cols
        assert "unit_type" in cols
    finally:
        conn.close()


def test_unique_md5_per_partition(kb_schema_env: Path) -> None:
    conn = sqlite3.connect(kb_schema_env)
    try:
        conn.execute("INSERT INTO kb_partitions (partition_id, name) VALUES (1, 'default')")
        conn.execute(
            """
            INSERT INTO kb_documents (doc_id, partition_id, file_path, display_name, content_md5, current_version)
            VALUES ('doc_a', 1, 'a.txt', 'a.txt', 'abc123', 1)
            """
        )
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO kb_documents (doc_id, partition_id, file_path, display_name, content_md5, current_version)
                VALUES ('doc_b', 1, 'b.txt', 'b.txt', 'abc123', 1)
                """
            )
    finally:
        conn.close()
