"""LT-004.01.01：知识库切片向量化 + worker + 应答链."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentRegistry
from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.kb.chunking import split_text
from plugins.mxai.kb.embeddings import cosine_similarity, embed_text
from plugins.mxai.kb.engine.search import search_chunks
from plugins.mxai.kb.service import ingest_text
from plugins.mxai.kb.worker import KbWorker
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.agents.pipeline import resolve_reply


@pytest.fixture
def kb_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    profiles = data_dir / "profiles"
    profiles.mkdir()
    main = profiles / "main"
    main.mkdir()
    (main / "config.yaml").write_text("model: test\n", encoding="utf-8")
    douyin = profiles / "douyin"
    douyin.mkdir()
    (douyin / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (douyin / "faq.yaml").write_text("entries: []\n", encoding="utf-8")
    (douyin / "sensitive_words.yaml").write_text("words: []\n", encoding="utf-8")

    AgentRegistry.clear()
    QueueManager.reset()
    KbWorker.reset()
    from plugins.mxai._bootstrap_imports import load_registries
    from plugins.mxai.agents._register import register_channel_agents

    load_registries()
    register_channel_agents()

    def fake_create(name: str, **kwargs: object) -> Path:
        d = profiles / name
        d.mkdir(parents=True, exist_ok=True)
        if not (d / "config.yaml").exists():
            (d / "config.yaml").write_text("model: test\n", encoding="utf-8")
        return d

    monkeypatch.setattr("hermes_cli.profiles.create_profile", fake_create)
    monkeypatch.setattr(
        "hermes_cli.profiles.profile_exists",
        lambda name: (profiles / name).is_dir(),
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profiles / name,
    )
    ensure_runtime_bootstrap(data_dir)
    KbWorker.get().start()
    return data_dir


def test_chunking_splits_long_text() -> None:
    text = "段落一内容。\n\n段落二有更多营销自动化相关说明。"
    chunks = split_text(text, max_chars=20)
    assert len(chunks) >= 2
    assert sum(len(c) for c in chunks) >= len(text.replace("\n\n", "")) - 5


def test_embedding_similarity() -> None:
    a = embed_text("MxAI 营销自动化平台")
    b = embed_text("营销自动化解决方案")
    c = embed_text("完全无关的天气预报")
    assert cosine_similarity(a, b) > cosine_similarity(a, c)


def test_ingest_worker_vector_search(kb_env: Path) -> None:
    result = ingest_text(
        "产品手册",
        "MxAI 是营销自动化平台，支持抖音评论采集与企微自动回复。",
        data_dir=kb_env,
    )
    assert result["status"] == "done"
    assert result["chunks"] >= 1

    hits = search_chunks("营销自动化", limit=3, data_dir=kb_env)
    assert hits
    assert hits[0]["score"] > 0
    assert "营销" in hits[0]["text"] or "自动化" in hits[0]["text"]


def test_reply_pipeline_injects_kb_chunk(kb_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-125：知识库**不直接回复**——命中切片注入 LLM 上下文（RAG），回复由大模型生成。"""
    monkeypatch.setenv("MXAI_MOCK", "1")  # LLM 走 mock stub（带「已参考知识库」标记）
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: kb_env / "profiles" / name,
    )
    ingest_text(
        "FAQ备查",
        "价格咨询请回复：我们提供企业版营销自动化套餐。",
        data_dir=kb_env,
    )
    reply = resolve_reply("douyin", "企业版营销自动化套餐价格")
    # 命中 KB → 注入上下文 → 回复来自大模型（source=llm），且确证已注入 KB
    assert reply["source"] == "llm"          # 不再直接回 KB 原文
    assert "已参考知识库" in reply["text"]    # mock LLM 标记：KB 命中并注入


def test_kb_api_vector_mode(kb_env: Path) -> None:
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)

    ing = client.post(
        "/api/plugins/mxai/kb/ingest",
        json={"title": "手册", "content": "MxAI 营销自动化产品说明"},
    )
    assert ing.status_code == 200
    assert ing.json()["status"] == "done"
    assert ing.json()["chunks"] >= 1

    search = client.get(
        "/api/plugins/mxai/kb/search", params={"q": "营销自动化"}
    ).json()
    assert search["mode"] == "vector"
    assert len(search["items"]) >= 1
    assert search["items"][0].get("chunk_id")
