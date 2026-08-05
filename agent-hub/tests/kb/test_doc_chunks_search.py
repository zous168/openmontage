"""FR-KB-18 · 切片分页与单文档检索."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.service import ingest_text, list_document_chunks
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


def _many_chunks_body() -> str:
    sections = []
    for i in range(12):
        sections.append(f"## 章节 {i}\n\n" + ("段落内容。" * 80))
    sections.append("## 唯一关键词 zeta-marker\n\n这是包含 zeta-marker 的特殊段落。")
    return "\n\n".join(sections)


def test_chunks_default_page_size_and_total_chunks(kb_env: Path) -> None:
    del kb_env
    result = ingest_text("big.txt", _many_chunks_body(), wait=True)
    doc_id = result["doc_id"]
    page1 = list_document_chunks(doc_id, page=1, page_size=20)
    assert page1["page_size"] == 20
    assert page1["total_chunks"] >= 10
    assert page1["total"] == page1["total_chunks"]
    assert len(page1["items"]) <= 20


def test_chunks_pagination_no_overlap(kb_env: Path) -> None:
    del kb_env
    result = ingest_text("pages.txt", _many_chunks_body(), wait=True)
    doc_id = result["doc_id"]
    p1 = list_document_chunks(doc_id, page=1, page_size=5)
    p2 = list_document_chunks(doc_id, page=2, page_size=5)
    assert len(p1["items"]) == 5
    assert p1["items"][0]["seq"] != p2["items"][0]["seq"]


def test_chunks_query_scoped_to_doc(kb_env: Path) -> None:
    del kb_env
    a = ingest_text("a.txt", _many_chunks_body(), wait=True)
    ingest_text("b.txt", "另一文档也含有 zeta-marker 但不应被搜到。", wait=True)
    hits = list_document_chunks(a["doc_id"], query="zeta-marker")
    assert hits["total"] >= 1
    assert all("zeta-marker" in it["text"] for it in hits["items"])
    assert hits["query"] == "zeta-marker"
    assert hits["total_chunks"] >= hits["total"]


def test_chunks_query_empty(kb_env: Path) -> None:
    del kb_env
    result = ingest_text("empty-q.txt", "普通内容无特殊词。", wait=True)
    hits = list_document_chunks(result["doc_id"], query="not-exists-xyz")
    assert hits["total"] == 0
    assert hits["items"] == []
