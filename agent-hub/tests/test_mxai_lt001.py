"""LT-001 Epic A 贯通测试."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentRegistry
from plugins.mxai.api.deps import get_queue
from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.worklog.service import list_worklogs


@pytest.fixture
def mxai_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    profiles = data_dir / "profiles"
    profiles.mkdir()
    main = profiles / "main"
    main.mkdir()
    (main / "config.yaml").write_text("model: test\n", encoding="utf-8")
    for agent in ("douyin", "qiyeweixin"):
        p = profiles / agent
        p.mkdir()
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
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
    KbWorker.get().start()

    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    from tests.conftest import arm_test_queue

    arm_test_queue()
    return TestClient(app)


def test_lt001_a2_comment_collect(mxai_client: TestClient) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"keywords": ["AI", "营销"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "queued"
    summary = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary["done"] >= 1
    logs = list_worklogs(profile_id="douyin", limit=5)
    assert any(log["op_type"] == "comment_collect" for log in logs)


def test_lt001_a6_wecom_inbound(mxai_client: TestClient) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/inbound",
        json={"message_id": "m1", "sender": "user1", "message": "你好"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "replied"
    assert body["task_id"] is None
    assert body["send_status"] == "not_enqueued"
    assert body["reply"]["source"] == "llm"


def test_lt001_a7_wizard(mxai_client: TestClient) -> None:
    state = mxai_client.get("/api/plugins/mxai/wizard/state").json()
    assert state["forced"] is True
    mxai_client.put(
        "/api/plugins/mxai/wizard/state",
        json={"enterprise": {"name": "Acme"}, "product": {"name": "MxAI"}},
    )
    check = mxai_client.post("/api/plugins/mxai/wizard/self-check").json()
    assert check["ok"] is True


def test_lt001_a4_kb(mxai_client: TestClient) -> None:
    ing = mxai_client.post(
        "/api/plugins/mxai/kb/ingest",
        json={"title": "产品手册", "content": "MxAI 营销自动化"},
    )
    assert ing.status_code == 200
    body = ing.json()
    assert body["status"] == "done"
    assert body.get("chunks", 0) >= 1
    search = mxai_client.get("/api/plugins/mxai/kb/search", params={"q": "营销"}).json()
    assert len(search["items"]) >= 1


def test_lt001_agent_leads(mxai_client: TestClient) -> None:
    resp = mxai_client.get("/api/plugins/mxai/agents/douyin/leads")
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_id"] == "douyin"
    assert "items" in body


def test_lt001_first_comment(mxai_client: TestClient) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/first-comment",
        json={"scripts": ["你好"], "benchmarks": ["@demo"]},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_lt001_run_preflight(mxai_client: TestClient) -> None:
    pre = mxai_client.post("/api/plugins/mxai/run/preflight").json()
    assert pre["ok"] is True


def test_lt001_workflow_readonly(mxai_client: TestClient) -> None:
    wf = mxai_client.get("/api/plugins/mxai/agents/douyin/workflow").json()
    assert wf["profile_id"] == "douyin"
    assert len(wf["workflows"]) >= 1


def test_lt001_a3_inbound_no_longer_enqueues_under_dm_limit(mxai_client: TestClient) -> None:
    """/inbound 不入队，故不受 daily_dm_limit 入队门闸；仍可连续取文案。"""
    from runtime_paths import resolve_hub_data_dir_path

    risk = resolve_hub_data_dir_path() / "profiles" / "qiyeweixin" / "risk.yaml"
    risk.write_text("daily_dm_limit: 1\nmin_interval_sec: 0\n", encoding="utf-8")
    r1 = mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/inbound",
        json={"message_id": "m1", "sender": "u1", "message": "你好"},
    )
    assert r1.status_code == 200
    assert r1.json().get("send_status") == "not_enqueued"
    r2 = mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/inbound",
        json={"message_id": "m2", "sender": "u2", "message": "再问"},
    )
    assert r2.status_code == 200
    assert r2.json().get("task_id") is None
    assert r2.json().get("send_status") == "not_enqueued"


def test_lt001_a5_dm_faq(mxai_client: TestClient) -> None:
    from runtime_paths import resolve_hub_data_dir_path

    faq = resolve_hub_data_dir_path() / "profiles" / "douyin" / "faq.yaml"
    faq.write_text(
        "entries:\n  - question: 价格多少\n    answer: 请联系顾问获取报价\n",
        encoding="utf-8",
    )
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/dm",
        json={"recipient": "user99", "message": "价格多少"},
    )
    assert resp.status_code == 200
    assert resp.json()["reply"]["source"] == "faq"


def test_lt001_a2_queue_controls(mxai_client: TestClient) -> None:
    get_queue().set_global_pause(True)
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"keywords": ["queued"]},
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]
    task = get_queue().get_task(task_id)
    assert task is not None
    assert task.status.value == "排队中"
    mxai_client.post("/api/plugins/mxai/queue/pause")
    get_queue().set_agent_enabled("douyin", True)
    mxai_client.post("/api/plugins/mxai/queue/resume")
    time.sleep(0.3)
    summary = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary["done"] >= 1


def test_lt007_platform_wecom(messaging_client: TestClient) -> None:
    put = messaging_client.put(
        "/api/messaging/platforms/wecom",
        json={
            "enabled": True,
            "env": {
                "WECOM_BOT_ID": "bot_test",
                "WECOM_SECRET": "sec",
            },
        },
    )
    assert put.status_code == 200
    test = messaging_client.post("/api/messaging/platforms/wecom/test")
    assert test.status_code == 200
    assert test.json()["ok"] in (True, False)


def test_lt007_platform_clawbot(messaging_client: TestClient) -> None:
    bind = messaging_client.post("/api/messaging/clawbot/onboarding/start")
    assert bind.status_code == 200
    token = bind.json()["bind_token"]
    time.sleep(1.3)
    st = messaging_client.get(
        f"/api/messaging/clawbot/onboarding/status?token={token}"
    ).json()
    assert st["bound"] is True
    listed = messaging_client.get("/api/messaging/platforms").json()
    claw = next(p for p in listed["platforms"] if p["id"] == "clawbot")
    assert claw["platform_extra"]["bind_status"] is True
    assert claw["platform_extra"]["bound_wxid"]


def test_lt007_kb_partitions_docs(mxai_client: TestClient) -> None:
    parts = mxai_client.get("/api/plugins/mxai/kb/partitions").json()
    assert parts["total"] >= 1
    docs = mxai_client.get("/api/plugins/mxai/kb/docs").json()
    assert "items" in docs


def test_lt007_agent_memory(mxai_client: TestClient) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/memory",
        json={"rounds": 25, "expire": "7d", "enabled": True},
    )
    assert put.status_code == 200
    mem = mxai_client.get("/api/plugins/mxai/agents/douyin/memory").json()
    assert mem["memory"]["rounds"] == 25


def test_lt007_agent_kb_partitions(mxai_client: TestClient) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/kb-partitions",
        json={"partition_ids": [1]},
    )
    assert put.status_code == 200
    got = mxai_client.get("/api/plugins/mxai/agents/douyin/kb-partitions").json()
    assert got["partition_ids"] == [1]


def test_lt007_conversations(mxai_client: TestClient) -> None:
    from runtime_paths import resolve_hub_data_dir_path

    risk = resolve_hub_data_dir_path() / "profiles" / "qiyeweixin" / "risk.yaml"
    risk.write_text("daily_dm_limit: 9999\n", encoding="utf-8")
    mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/inbound",
        json={"message_id": "cm1", "sender": "客户A", "message": "咨询"},
    )
    convs = mxai_client.get("/api/plugins/mxai/agents/qiyeweixin/conversations").json()
    assert convs["total"] >= 1
    conv_id = convs["items"][0]["id"]
    msgs = mxai_client.get(
        f"/api/plugins/mxai/agents/qiyeweixin/conversations/{conv_id}/messages"
    ).json()
    assert len(msgs["items"]) >= 1


def test_lt008_kb_partition_crud(mxai_client: TestClient) -> None:
    created = mxai_client.post(
        "/api/plugins/mxai/kb/partitions",
        json={"name": "产品业务分区"},
    )
    assert created.status_code == 200
    pid = created.json()["item"]["partition_id"]
    patched = mxai_client.patch(
        f"/api/plugins/mxai/kb/partitions/{pid}",
        json={"enabled": False, "name": "产品分区"},
    )
    assert patched.status_code == 200
    assert patched.json()["item"]["enabled"] is False
    deleted = mxai_client.delete(f"/api/plugins/mxai/kb/partitions/{pid}")
    assert deleted.status_code == 200


def test_lt008_kb_document_ops(mxai_client: TestClient) -> None:
    ing = mxai_client.post(
        "/api/plugins/mxai/kb/ingest",
        json={"title": "手册", "content": "MxAI 知识库 CRUD 测试内容"},
    )
    assert ing.status_code == 200
    doc_id = ing.json()["doc_id"]
    prev = mxai_client.get(f"/api/plugins/mxai/kb/documents/{doc_id}/preview")
    assert prev.status_code == 200
    assert prev.json().get("preview")
    vers = mxai_client.get(f"/api/plugins/mxai/kb/documents/{doc_id}/versions")
    assert vers.status_code == 200
    reslice = mxai_client.post(f"/api/plugins/mxai/kb/documents/{doc_id}/reslice")
    assert reslice.status_code == 200
    deleted = mxai_client.delete(f"/api/plugins/mxai/kb/documents/{doc_id}")
    assert deleted.status_code == 200


def test_lt008_kb_plugin(mxai_client: TestClient) -> None:
    st = mxai_client.get("/api/plugins/mxai/kb/plugin/status").json()
    assert st["running"] is True
    mxai_client.post("/api/plugins/mxai/kb/plugin/stop")
    ing = mxai_client.post(
        "/api/plugins/mxai/kb/ingest",
        json={"title": "x", "content": "y"},
    )
    assert ing.status_code == 503
    mxai_client.post("/api/plugins/mxai/kb/plugin/start")
    search = mxai_client.post(
        "/api/plugins/mxai/kb/search-test",
        json={"query": "营销", "limit": 5},
    )
    assert search.status_code == 200
