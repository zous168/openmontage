"""LT-009 REST 扫尾 API 测试."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentRegistry
from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.conversations.service import list_conversations
from plugins.mxai.orchestrator.queue_manager import QueueManager
from runtime_paths import resolve_hub_data_dir_path


@pytest.fixture
def mxai_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    profiles = data_dir / "profiles"
    profiles.mkdir()
    for agent in ("douyin", "boss", "wechat", "qiyeweixin"):
        p = profiles / agent
        p.mkdir()
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
        if agent in ("douyin", "qiyeweixin"):
            (p / "risk.yaml").write_text("daily_dm_limit: 9999\n", encoding="utf-8")

    AgentRegistry.clear()
    QueueManager.reset()
    from plugins.mxai.kb.worker import KbWorker

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
    from plugins.mxai.cfg.domains import ensure_config_runtime
    from plugins.mxai.cfg.manager import ConfigManager

    ConfigManager.reset()
    ensure_config_runtime()
    KbWorker.get().start()

    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    from tests.conftest import arm_test_queue

    arm_test_queue()
    return TestClient(app)


def test_lt009_stats(mxai_client: TestClient) -> None:
    summary = mxai_client.get("/api/plugins/mxai/stats/summary").json()
    assert "acquire_total" in summary
    realtime = mxai_client.get("/api/plugins/mxai/stats/realtime").json()
    assert "running_agents" in realtime
    alerts = mxai_client.get("/api/plugins/mxai/stats/alerts").json()
    assert "items" in alerts


def test_lt009_benchmarks(mxai_client: TestClient) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/benchmarks",
        json={"accounts": ["@demo", "@test"]},
    )
    assert put.status_code == 200
    body = put.json()
    assert body["accounts"] == ["@demo", "@test"]
    get = mxai_client.get("/api/plugins/mxai/agents/douyin/benchmarks").json()
    assert get["accounts"] == ["@demo", "@test"]


def test_lt009_comment_keywords(mxai_client: TestClient) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/comment-keywords",
        json={
            "search_keywords": ["工程机械", "挖掘机培训"],
            "match_keywords": ["多少钱", "怎么联系"],
        },
    )
    assert put.status_code == 200
    body = put.json()
    assert body["search_keywords"] == ["工程机械", "挖掘机培训"]
    assert body["match_keywords"] == ["多少钱", "怎么联系"]
    assert body["keywords"] == ["工程机械", "挖掘机培训"]
    get = mxai_client.get("/api/plugins/mxai/agents/douyin/comment-keywords").json()
    assert get["search_keywords"] == ["工程机械", "挖掘机培训"]
    assert get["match_keywords"] == ["多少钱", "怎么联系"]

    collect = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"search_keywords": []},
    )
    assert collect.status_code == 200
    assert collect.json()["search_keywords"] == ["工程机械", "挖掘机培训"]
    assert collect.json()["match_keywords"] == ["多少钱", "怎么联系"]

    legacy = mxai_client.put(
        "/api/plugins/mxai/agents/xiaohongshu/comment-keywords",
        json={"keywords": ["小红书词"]},
    )
    assert legacy.status_code == 200
    assert legacy.json()["search_keywords"] == ["小红书词"]

    empty = mxai_client.post(
        "/api/plugins/mxai/agents/xiaohongshu/tasks/comment-collect",
        json={"search_keywords": []},
    )
    assert empty.status_code == 200
    assert empty.json()["search_keywords"] == ["小红书词"]

    mxai_client.put(
        "/api/plugins/mxai/agents/shipinhao/comment-keywords",
        json={"search_keywords": [], "match_keywords": []},
    )
    no_kw = mxai_client.post(
        "/api/plugins/mxai/agents/shipinhao/tasks/comment-collect",
        json={"search_keywords": []},
    )
    assert no_kw.status_code == 422


def test_lt009_workbench(mxai_client: TestClient) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench",
        json={
            "data": {
                "first_scripts": ["首评话术A"],  # 废弃字段：落盘时剔除
                "first_comment": {"schedule_enabled": True},
                "dm": {"auto_enabled": False, "interval_minutes": 30},
            },
        },
    )
    assert put.status_code == 200
    body = put.json()
    assert "first_scripts" not in body["data"]
    assert body["data"]["first_comment"]["schedule_enabled"] is True

    get = mxai_client.get("/api/plugins/mxai/agents/douyin/workbench").json()
    assert "first_scripts" not in get["data"]
    assert get["data"]["dm"]["auto_enabled"] is False

    boss_put = mxai_client.put(
        "/api/plugins/mxai/agents/boss/workbench",
        json={
            "data": {
                "boss": {
                    "greet_scripts": [{"id": "g1", "text": "您好", "enabled": True}],
                    "expand_script": "拓聊内容",
                    "greet_rotate": True,
                },
            },
        },
    )
    assert boss_put.status_code == 200
    boss_get = mxai_client.get("/api/plugins/mxai/agents/boss/workbench").json()
    assert boss_get["data"]["boss"]["expand_script"] == "拓聊内容"
    assert boss_get["data"]["boss"]["greet_rotate"] is True


def test_lt009_candidates(mxai_client: TestClient) -> None:
    resp = mxai_client.get("/api/plugins/mxai/agents/boss/candidates")
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_id"] == "boss"
    assert "items" in body


def test_lt009_follow_up(mxai_client: TestClient) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/boss/tasks/follow-up",
        json={"recipient": "张三", "message": "跟进一下"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] in ("queued", "已完成", "执行中")


def test_lt009_channel_stats(mxai_client: TestClient) -> None:
    body = mxai_client.get("/api/plugins/mxai/agents/qiyeweixin/channel-stats").json()
    assert body["profile_id"] == "qiyeweixin"
    assert "today_reception" in body


def test_lt009_takeover(mxai_client: TestClient) -> None:
    mxai_client.post(
        "/api/plugins/mxai/agents/wechat/inbound",
        json={"message_id": "m1", "sender": "客户A", "message": "你好"},
    )
    conv_id = "C-客户A"
    on = mxai_client.post(
        f"/api/plugins/mxai/agents/wechat/conversations/{conv_id}/takeover",
        json={"takeover": True},
    )
    assert on.status_code == 200
    assert on.json()["mode"] == "takeover"
    convs = list_conversations("wechat")
    assert any(c["id"] == conv_id and c["mode"] == "takeover" for c in convs)


def test_lt009_kb_upload(mxai_client: TestClient) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/kb/upload",
        files={"file": ("readme.txt", b"MxAI knowledge upload test", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    dest = resolve_hub_data_dir_path() / "shared" / "knowledge" / "readme.txt"
    assert dest.is_file()


def test_lt009_chat(mxai_client: TestClient) -> None:
    body = mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "生成报表", "agent": "main"},
    ).json()
    assert "reply" in body
    assert body["reply"]["text"]
    assert body.get("session_id")
    hist = mxai_client.get("/api/plugins/mxai/chat/commands/history").json()
    assert "items" in hist
    cleared = mxai_client.delete("/api/plugins/mxai/chat/commands/history").json()
    assert "cleared" in cleared


def test_lt009_import_contacts_csv(mxai_client: TestClient) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/tasks/import-contacts",
        files={"file": ("contacts.csv", b"13800000001\n13800000002", "text/csv")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["parsed"] == 2
    assert body["status"] == "queued"


def test_lt009_kb_reorder(mxai_client: TestClient) -> None:
    mxai_client.post("/api/plugins/mxai/kb/ingest", json={"title": "t", "content": "c"})
    parts = mxai_client.get("/api/plugins/mxai/kb/partitions").json()["items"]
    ids = [p["id"] for p in parts]
    if len(ids) >= 2:
        rev = list(reversed(ids))
    else:
        rev = ids
    resp = mxai_client.post(
        "/api/plugins/mxai/kb/partitions/reorder",
        json={"partition_ids": rev},
    )
    assert resp.status_code == 200
    assert resp.json()["total"] == len(ids)


def test_lt009_reports_schedule_funnel(mxai_client: TestClient) -> None:
    sched = mxai_client.put(
        "/api/plugins/mxai/reports/schedule",
        json={"weekly": {"enabled": True, "weekday": 2, "hour": 10}},
    )
    assert sched.status_code == 200
    assert sched.json()["weekly"]["enabled"] is True
    funnel = mxai_client.get("/api/plugins/mxai/reports/funnel").json()
    assert len(funnel["stages"]) == 5
    gen = mxai_client.post(
        "/api/plugins/mxai/reports/generate",
        json={"report_type": "weekly"},
    ).json()
    snaps = mxai_client.get(
        f"/api/plugins/mxai/reports/{gen['report_id']}/snapshots"
    ).json()
    assert snaps["total"] >= 1
