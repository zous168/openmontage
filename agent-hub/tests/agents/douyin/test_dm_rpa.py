"""LT-004.03.01：抖音私信多轮 + FAQ/KB/LLM + DM RPA."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentRegistry
from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.kb.worker import KbWorker
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.agents.hermes_agent import set_llm_override
from plugins.mxai.agents.pipeline import resolve_reply


def _session_message_count(profile_id: str, recipient: str) -> int:
    """读 Hermes SessionDB 中该客户会话的消息条数（ADR-06 v2）。

    LT-031：渠道会话物理隔离，读 ``profiles/{profile_id}/state.db``（与写侧同库）。
    """
    from plugins.mxai.agents.hermes_agent import _profile_session_db, inbound_session_id

    sid = inbound_session_id(profile_id, recipient)
    db = _profile_session_db(profile_id)
    try:
        resolved = db.resolve_session_id(sid) or sid
        return len(db.get_messages(resolved))
    finally:
        db.close()


@pytest.fixture
def dm_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    profiles = data_dir / "profiles"
    profiles.mkdir()
    for name in ("main", "douyin"):
        p = profiles / name
        p.mkdir()
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
        (p / "risk.yaml").write_text("daily_dm_limit: 9999\n", encoding="utf-8")
        (p / "faq.yaml").write_text("entries: []\n", encoding="utf-8")
        (p / "sensitive_words.yaml").write_text("words: []\n", encoding="utf-8")

    AgentRegistry.clear()
    QueueManager.reset()
    KbWorker.reset()
    set_llm_override(None)
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


def test_dm_llm_mock_multi_turn(dm_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: dm_env / "profiles" / name,
    )
    r1 = resolve_reply("douyin", "你好", recipient="user_99")
    assert r1["source"] == "llm"
    r2 = resolve_reply("douyin", "价格多少", recipient="user_99")
    assert r2["source"] == "llm"
    assert "已对话" in r2["text"] or "感谢" in r2["text"]
    # 历史落 Hermes SessionDB（ADR-06 v2），非自建 dm_session
    assert _session_message_count("douyin", "user_99") == 4


def test_dm_faq_beats_llm(dm_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    faq = dm_env / "profiles" / "douyin" / "faq.yaml"
    faq.write_text(
        "entries:\n  - question: 价格多少\n    answer: 请联系顾问获取报价\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: dm_env / "profiles" / name,
    )
    reply = resolve_reply("douyin", "价格多少", recipient="user_1")
    assert reply["source"] == "faq"


def test_dm_sensitive_block(dm_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sw = dm_env / "profiles" / "douyin" / "sensitive_words.yaml"
    sw.write_text("words:\n  - 违禁词\n", encoding="utf-8")
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: dm_env / "profiles" / name,
    )
    reply = resolve_reply("douyin", "这是违禁词测试", recipient="u1")
    assert reply["source"] == "sensitive_blocked"


def test_dm_api_send_mock(dm_env: Path) -> None:
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)

    resp = client.post(
        "/api/plugins/mxai/agents/douyin/tasks/dm",
        json={"recipient": "lead_user_1", "message": "想了解一下产品"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "已完成"
    assert body["reply"]["source"] == "llm"
    task_id = body["task_id"]
    steps = client.get(f"/api/plugins/mxai/queue/tasks/{task_id}/steps").json()
    step_ids = {s["step_id"] for s in steps["steps"]}
    assert {"reply", "send"}.issubset(step_ids)


def test_custom_llm_override(dm_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: dm_env / "profiles" / name,
    )

    def fake_llm(profile_id: str, message: str, history: list) -> dict:
        return {"source": "llm", "text": f"OVERRIDE:{message}"}

    set_llm_override(fake_llm)
    reply = resolve_reply("douyin", "测试", recipient="u2")
    assert reply["text"] == "OVERRIDE:测试"
