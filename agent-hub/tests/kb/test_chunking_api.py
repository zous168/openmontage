"""LT-021.06.02 · chunking API."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.service import ingest_text, list_document_chunks
from plugins.mxai.kb.storage.kb_repo import init_kb_schema
from plugins.mxai.kb.worker import KbWorker

MD = """# 标题

段落内容。
"""


@pytest.fixture
def kb_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    # CR-145：resolve_hub_data_dir_path 不读 HUB_DATA_DIR；须显式指向 tmp，
    # 否则 GET chunking 会读到本机 .data/shared/knowledge/kb_plugin.yaml（用户偏好可≠文档默认 500）。
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
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    return TestClient(app)


def test_get_chunking(kb_client: TestClient) -> None:
    resp = kb_client.get("/api/plugins/mxai/kb/chunking")
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["max_chunk_chars"] == 500
    assert item["strategy"] == "semantic_paragraph"


def test_chunks_include_unit_type(kb_client: TestClient) -> None:
    ing = ingest_text("md.md", MD, wait=True)
    listed = list_document_chunks(ing["doc_id"])
    assert listed["items"]
    assert any(it.get("unit_type") for it in listed["items"])


def test_put_max_chunk_chars_out_of_range(kb_client: TestClient) -> None:
    for bad in (100, 2000):
        resp = kb_client.put(
            "/api/plugins/mxai/kb/chunking",
            json={"max_chunk_chars": bad},
        )
        assert resp.status_code == 422


def test_put_max_chunk_chars_does_not_bump_strategy_version(kb_client: TestClient) -> None:
    before = kb_client.get("/api/plugins/mxai/kb/chunking").json()["item"]
    resp = kb_client.put(
        "/api/plugins/mxai/kb/chunking",
        json={"max_chunk_chars": 600},
    )
    assert resp.status_code == 200
    item = resp.json()["item"]
    assert item["max_chunk_chars"] == 600
    assert item["strategy_version"] == before["strategy_version"]


def test_put_same_chunking_does_not_bump_version(kb_client: TestClient) -> None:
    kb_client.put("/api/plugins/mxai/kb/chunking", json={"max_chunk_chars": 600})
    before = kb_client.get("/api/plugins/mxai/kb/chunking").json()["item"]
    resp = kb_client.put("/api/plugins/mxai/kb/chunking", json={"max_chunk_chars": 600})
    assert resp.status_code == 200
    assert resp.json()["item"]["strategy_version"] == before["strategy_version"]


def test_put_fixed_char_rejected(kb_client: TestClient) -> None:
    resp = kb_client.put(
        "/api/plugins/mxai/kb/chunking",
        json={"strategy": "fixed_char"},
    )
    assert resp.status_code == 422
