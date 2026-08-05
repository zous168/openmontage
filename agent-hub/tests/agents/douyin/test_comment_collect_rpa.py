"""LT-004.02.01：抖音评论采集 RPA → Lead + WorkLog."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentRegistry
from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.crm.lead_service import count_leads, list_leads
from plugins.mxai.kb.worker import KbWorker
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.rpa.douyin.comment_collect import run_comment_collect
from plugins.mxai.worklog.service import list_worklogs


@pytest.fixture
def douyin_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    from tests.conftest import stub_rpa_bridge_for_tests, write_test_client_settings

    # 禁止默认 http 出站打本机 Automan（与 mxai_env 同策）。
    write_test_client_settings(data_dir)
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.state.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    profiles = data_dir / "profiles"
    profiles.mkdir()
    for name in ("main", "douyin"):
        p = profiles / name
        p.mkdir()
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
        (p / "risk.yaml").write_text("daily_dm_limit: 9999\n", encoding="utf-8")

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
    from plugins.mxai.cfg.domains import ensure_config_runtime
    from plugins.mxai.cfg.manager import ConfigManager

    ConfigManager.reset()
    ensure_config_runtime()
    from tests.conftest import arm_test_queue

    arm_test_queue()
    stub_rpa_bridge_for_tests()
    QueueManager.get().set_agent_enabled("douyin", True)
    KbWorker.get().start()
    return data_dir


def test_mock_rpa_returns_comments() -> None:
    comments = run_comment_collect("douyin", ["AI", "营销"], mode="mock")
    assert len(comments) == 2
    assert all(c.keyword in {"AI", "营销"} for c in comments)


def test_comment_collect_api_writes_leads_and_worklog(douyin_env: Path) -> None:
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)
    QueueManager.get().set_agent_enabled("douyin", True)

    resp = client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"search_keywords": ["AI", "营销"]},
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]
    time.sleep(0.5)

    leads = list_leads(profile_id="douyin", task_id=task_id, data_dir=douyin_env)
    assert len(leads) == 2
    assert leads[0]["source_channel"] == "douyin"
    assert {leads[0]["keyword"], leads[1]["keyword"]} == {"AI", "营销"}

    logs = list_worklogs(profile_id="douyin", limit=5, data_dir=douyin_env)
    assert any(
        log["op_type"] == "comment_collect" and log["exec_status"] == "成功"
        for log in logs
    )
    assert all(l["task_id"] == task_id for l in leads)

    steps = client.get(f"/api/plugins/mxai/queue/tasks/{task_id}/steps").json()
    step_ids = {s["step_id"] for s in steps["steps"]}
    assert {"search", "collect", "persist"}.issubset(step_ids)


def test_comment_collect_match_keywords_filter(douyin_env: Path) -> None:
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)
    QueueManager.get().arm_work()

    client.put(
        "/api/plugins/mxai/agents/douyin/comment-keywords",
        json={"search_keywords": ["AI"], "match_keywords": ["不存在词"]},
    )
    blocked = client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"search_keywords": ["AI"]},
    )
    assert blocked.status_code == 200
    blocked_id = blocked.json()["task_id"]
    time.sleep(0.5)
    assert len(list_leads(profile_id="douyin", task_id=blocked_id, data_dir=douyin_env)) == 0

    client.put(
        "/api/plugins/mxai/agents/douyin/comment-keywords",
        json={"search_keywords": ["AI"], "match_keywords": ["怎么联系"]},
    )
    allowed = client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"search_keywords": ["AI"]},
    )
    allowed_id = allowed.json()["task_id"]
    time.sleep(0.5)
    assert len(list_leads(profile_id="douyin", task_id=allowed_id, data_dir=douyin_env)) == 1


@pytest.mark.skipif(
    os.environ.get("MXAI_RUN_PLAYWRIGHT") != "1",
    reason="set MXAI_RUN_PLAYWRIGHT=1 to run real browser fixture test",
)
def test_playwright_fixture_collect(douyin_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fixture = (
        Path(__file__).resolve().parents[2] / "fixtures" / "douyin_comments.html"
    )
    monkeypatch.setenv("MXAI_RPA_FIXTURE", str(fixture))
    comments = run_comment_collect("douyin", ["AI"], mode="playwright")
    assert len(comments) >= 1
    assert any("营销" in c.text or "AI" in c.text for c in comments)
