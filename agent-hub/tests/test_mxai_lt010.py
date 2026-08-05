"""LT-010 consistency §5 余项 API 测试."""

from __future__ import annotations

import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentRegistry
from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.orchestrator.queue_manager import QueueManager


@pytest.fixture
def mxai_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    profiles = data_dir / "profiles"
    profiles.mkdir()
    for agent in ("douyin", "wechat"):
        p = profiles / agent
        p.mkdir()
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")

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


def test_lt010_chat_favorites_export(mxai_client: TestClient) -> None:
    mxai_client.post(
        "/api/plugins/mxai/chat/completions",
        json={"message": "测试指令", "agent": "main"},
    )
    fav = mxai_client.post(
        "/api/plugins/mxai/chat/commands/favorites",
        json={"text": "启动抖音评论抓取"},
    )
    assert fav.status_code == 200
    item = fav.json()["item"]
    assert item["text"] == "启动抖音评论抓取"

    listed = mxai_client.get("/api/plugins/mxai/chat/commands/favorites").json()
    assert listed["total"] >= 1

    deleted = mxai_client.delete(
        f"/api/plugins/mxai/chat/commands/favorites/{item['id']}"
    )
    assert deleted.status_code == 200

    export = mxai_client.get("/api/plugins/mxai/chat/commands/export")
    assert export.status_code == 200
    assert "application/json" in export.headers.get("content-type", "")
    assert "items" in export.json()


def test_lt010_auth(mxai_client: TestClient) -> None:
    session = mxai_client.get("/api/plugins/mxai/auth/session").json()
    assert session["authenticated"] is True
    assert session["user"]["login_name"] == "admin"

    login = mxai_client.post("/api/plugins/mxai/auth/login").json()
    assert login["ok"] is True
    assert login["token"].startswith("stub-")
    assert login["user"]["user_id"] == "local-operator"
    assert login["expires_at"] > time.time()


def test_lt010_clawbot_bind(messaging_client: TestClient) -> None:
    start = messaging_client.post("/api/messaging/clawbot/onboarding/start").json()
    token = start["bind_token"]
    assert token
    assert "qr_hint" in start

    pending = messaging_client.get(
        f"/api/messaging/clawbot/onboarding/status?token={token}"
    ).json()
    assert pending["status"] in ("pending", "confirmed")

    time.sleep(1.3)
    confirmed = messaging_client.get(
        f"/api/messaging/clawbot/onboarding/status?token={token}"
    ).json()
    assert confirmed["status"] == "confirmed"
    assert confirmed["bound"] is True

    listed = messaging_client.get("/api/messaging/platforms").json()
    claw = next(p for p in listed["platforms"] if p["id"] == "clawbot")
    assert claw["platform_extra"]["bind_status"] is True
    assert claw["platform_extra"]["bound_wxid"]
