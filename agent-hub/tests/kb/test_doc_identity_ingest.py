"""LT-021.05.02 · ingest 升版 + reslice/rollback 固定 doc_id."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.errors import DuplicateContentError
from plugins.mxai.kb.service import ingest_text, reslice_document, rollback_document
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


def test_first_upload_is_v1(kb_env: Path) -> None:
    del kb_env
    result = ingest_text("first.txt", "首版内容。\n\n第二段。", wait=True)
    assert result["status"] == "done"
    assert result["current_version"] == 1


def test_duplicate_upload_raises(kb_env: Path) -> None:
    del kb_env
    content = "重复内容测试。"
    ingest_text("dup.txt", content, wait=True)
    with pytest.raises(DuplicateContentError) as exc:
        ingest_text("dup2.txt", content, wait=True)
    assert exc.value.doc_id


def test_same_name_new_content_keeps_doc_id(kb_env: Path) -> None:
    del kb_env
    first = ingest_text("same.txt", "版本一内容。", file_path="inline:same.txt", wait=True)
    second = ingest_text("same.txt", "版本二内容已变更。", file_path="inline:same.txt", wait=True)
    assert first["doc_id"] == second["doc_id"]
    assert second["current_version"] == 2


def test_reslice_keeps_doc_id_and_version(kb_env: Path) -> None:
    del kb_env
    first = ingest_text("reslice.txt", "可重切片文档。", wait=True)
    doc_id = first["doc_id"]
    version = first["current_version"]
    again = reslice_document(doc_id)
    assert again["doc_id"] == doc_id
    assert again["current_version"] == version


def test_rollback_bumps_version(kb_env: Path) -> None:
    del kb_env
    first = ingest_text("roll.txt", "第一版。", file_path="inline:roll.txt", wait=True)
    doc_id = first["doc_id"]
    ingest_text("roll.txt", "第二版。", file_path="inline:roll.txt", wait=True)
    rollback_document(doc_id, 1)
    from plugins.mxai.kb.service import _doc_current_version

    assert _doc_current_version(doc_id) >= 2


def test_upload_409_api(kb_env: Path) -> None:
    del kb_env
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)
    content = b"409 \xe6\xb5\x8b\xe8\xaf\x95"
    files = {"file": ("api-dup.txt", content, "text/plain")}
    assert client.post("/api/plugins/mxai/kb/upload", files=files).status_code == 200
    resp = client.post("/api/plugins/mxai/kb/upload", files=files)
    assert resp.status_code == 409
    body = resp.json()["detail"]
    assert body["code"] == "KB_DUPLICATE_CONTENT"
    assert body["doc_id"]
