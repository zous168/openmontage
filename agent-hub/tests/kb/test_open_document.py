"""KB document open-file API."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.kb.service import resolve_document_file_path
from plugins.mxai.kb.storage.kb_repo import init_kb_schema
from plugins.mxai.kb.worker import KbWorker

MD = "# Title\n\nBody text.\n"


@pytest.fixture
def kb_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    init_kb_schema(mxai_db_path("kb.db", data_dir))
    KbWorker.reset()
    KbWorker.get().start()
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    return TestClient(app)


def _upload(client: TestClient, name: str, content: str) -> dict:
    files = {"file": (name, content.encode("utf-8"), "text/markdown")}
    resp = client.post("/api/plugins/mxai/kb/upload?partition_id=1", files=files)
    assert resp.status_code == 200
    return resp.json()


def test_resolve_document_file_path(kb_client: TestClient, tmp_path: Path) -> None:
    data_dir = tmp_path / "hub"
    ing = _upload(kb_client, "note.md", MD)
    path = resolve_document_file_path(ing["doc_id"], data_dir)
    assert path.is_file()
    assert path.name == "note.md"


def test_open_document(kb_client: TestClient) -> None:
    ing = _upload(kb_client, "open-me.md", MD)
    with patch("os.startfile") as mocked:
        resp = kb_client.post(f"/api/plugins/mxai/kb/documents/{ing['doc_id']}/open")
    assert resp.status_code == 200
    assert resp.json()["item"]["name"] == "open-me.md"
    mocked.assert_called_once()
