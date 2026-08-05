"""LT-021.06.01 · 语义段落切片."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.chunking import split_semantic, split_text
from plugins.mxai.kb.service import ingest_text
from plugins.mxai.kb.storage.kb_repo import init_kb_schema
from plugins.mxai.kb.worker import KbWorker


MD_SAMPLE = """# 产品概述

第一段说明。

## 功能细节

- 列表项 A
- 列表项 B

第二段落收尾。
"""


@pytest.fixture
def kb_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    # 与 mxai_env / test_chunking_api 一致：隔离数据根，避免读本机 kb_plugin.yaml 偏好。
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.kb.config_store.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    init_kb_schema(mxai_db_path("kb.db", data_dir))
    KbWorker.reset()
    KbWorker.get().start()
    return data_dir


def test_markdown_headings_not_merged_across_sections() -> None:
    chunks = split_semantic(MD_SAMPLE, config={"strategy": "semantic_paragraph", "max_chunk_chars": 1200})
    paths = {c.heading_path for c in chunks if c.heading_path}
    assert "产品概述" in " ".join(paths)
    assert any(c.unit_type in {"heading", "paragraph", "list_item"} for c in chunks)


def test_long_field_sentence_split_not_mid_char() -> None:
    long_para = "这是一句很长的话。" * 400
    chunks = split_semantic(
        long_para,
        config={
            "strategy": "semantic_paragraph",
            "max_chunk_chars": 1200,
            "sentence_split_fallback": True,
        },
    )
    assert len(chunks) > 1
    for ch in chunks:
        assert not ch.text.startswith("话。这")  # 避免定长 mid-char


def test_no_fixed_400_step_boundaries(kb_env: Path) -> None:
    del kb_env
    body = "X" * 2000 + "。" + "Y" * 2000
    result = ingest_text("long.txt", body, wait=True)
    from plugins.mxai.kb.service import list_document_chunks

    listed = list_document_chunks(result["doc_id"])
    lengths = [it["chars"] for it in listed["items"]]
    assert not any(l == 400 for l in lengths)


def test_default_max_chunk_chars_500(kb_env: Path) -> None:
    del kb_env  # 仅需夹具隔离数据根；断言文档默认 500（DEFAULT_CHUNKING）
    medium = "段落。" * 300
    chunks = split_text(medium)
    assert all(len(c) <= 500 for c in chunks)
