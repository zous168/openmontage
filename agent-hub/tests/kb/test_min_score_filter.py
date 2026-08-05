"""KB min_score 阈值：弱相关不注入 / 达阈值保留."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.agents.pipeline import _kb_filter_hits_for_inject
from plugins.mxai.kb.config_store import DEFAULT_RETRIEVAL
from plugins.mxai.kb.engine.search import _items_passing_min_score, search_chunks
from plugins.mxai.kb.service import ingest_text, set_kb_retrieval
from plugins.mxai.kb.storage.kb_repo import init_kb_schema
from plugins.mxai.cfg.paths import mxai_db_path
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


def test_default_retrieval_min_score() -> None:
    assert DEFAULT_RETRIEVAL["min_score"] == 0.2


def test_items_passing_min_score() -> None:
    items = [{"score": 0.05}, {"score": 0.25}, {"score": 0.21}]
    out = _items_passing_min_score(items, 0.2, limit=3)
    assert len(out) == 2
    assert out[0]["score"] == 0.25
    assert out[1]["score"] == 0.21


def test_pipeline_kb_filter_hits_for_inject() -> None:
    hits = [{"score": 0.03, "text": "weak"}, {"score": 0.82, "text": "strong"}]
    out = _kb_filter_hits_for_inject(hits, {"min_score": 0.2})
    assert len(out) == 1
    assert out[0]["text"] == "strong"


def test_search_chunks_respects_min_score(kb_env: Path) -> None:
    ingest_text("product.txt", "unique-marker-xyz 本地部署方案详细说明", wait=True)
    set_kb_retrieval({"mode": "hybrid", "min_score": 0.5}, data_dir=kb_env)
    assert search_chunks("你好", limit=5, data_dir=kb_env) == []

    set_kb_retrieval({"mode": "hybrid", "min_score": 0.2}, data_dir=kb_env)
    hits = search_chunks("unique-marker-xyz", limit=5, data_dir=kb_env)
    assert hits
    for h in hits:
        assert float(h["score"]) >= 0.2
