"""知识库文档切片列表 API."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.service import (
    ingest_text,
    list_document_chunks,
    list_documents,
)
from plugins.mxai.kb.storage.kb_repo import init_kb_schema


@pytest.fixture
def kb_chunks_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir(parents=True)
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    init_kb_schema(mxai_db_path("kb.db", data_dir))
    return data_dir


def test_list_document_chunks(kb_chunks_env: Path) -> None:
    del kb_chunks_env
    result = ingest_text(
        "demo.txt",
        "第一段内容。\n\n第二段内容用于切片测试。",
        wait=True,
    )
    doc_id = result["doc_id"]
    listed = list_document_chunks(doc_id)
    assert listed["total"] >= 1
    assert listed["total_chunks"] == listed["total"]
    assert listed["items"][0]["seq"] == 0
    assert listed["items"][0]["text"]
    seqs = [it["seq"] for it in listed["items"]]
    assert seqs == sorted(seqs)


def test_list_document_chunks_pagination(kb_chunks_env: Path) -> None:
    del kb_chunks_env
    sections = []
    for i in range(8):
        sections.append(f"## 章节 {i}\n\n" + ("独立段落内容。" * 120))
    body = "\n\n".join(sections)
    result = ingest_text("paginate.txt", body, wait=True)
    doc_id = result["doc_id"]
    full = list_document_chunks(doc_id, page=1, page_size=2)
    assert full["total"] >= 2, f"expected >=2 chunks, got {full['total']}"
    assert full["total_chunks"] >= 2
    assert len(full["items"]) == 2
    page2 = list_document_chunks(doc_id, page=2, page_size=2)
    assert page2["page"] == 2
    assert len(page2["items"]) >= 1
    assert full["items"][0]["seq"] != page2["items"][0]["seq"]


def test_list_document_chunks_not_found(kb_chunks_env: Path) -> None:
    del kb_chunks_env
    with pytest.raises(ValueError, match="document not found"):
        list_document_chunks("missing-doc-id")


def test_list_documents_includes_chunk_count(kb_chunks_env: Path) -> None:
    del kb_chunks_env
    result = ingest_text("count.txt", "用于计数切片。\n\n第二段。", wait=True)
    doc_id = result["doc_id"]
    docs = list_documents()
    row = next(d for d in docs if d["doc_id"] == doc_id)
    assert row["chunk_count"] >= 1
    assert row["name"] == "count.txt"
