"""LT-018.01.01 workbench.scheduler 配置域."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.workbench_scheduler import extract_scheduler


def test_extract_scheduler_respects_disabled_when_legacy_has_time() -> None:
    wb = {
        "scheduler": {"scheduled_touch": {"enabled": False, "time": "09:00"}},
        "scheduled_touch": {"time": "09:00", "message": "hi"},
    }
    sched = extract_scheduler(wb)
    assert sched["scheduled_touch"]["enabled"] is False


def test_extract_scheduler_infers_enabled_from_legacy_without_scheduler_flag() -> None:
    wb = {"scheduled_touch": {"time": "09:00", "message": "hi"}}
    sched = extract_scheduler(wb)
    assert sched["scheduled_touch"]["enabled"] is True


def test_put_workbench_scheduler_persists(mxai_client: TestClient) -> None:
    res = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench",
        json={"data": {"scheduler": {"benchmark_monitor": {"interval_minutes": 60}}}},
    )
    assert res.status_code == 200
    sched = res.json()["data"]["scheduler"]["benchmark_monitor"]
    assert sched["interval_minutes"] == 60

    get = mxai_client.get("/api/plugins/mxai/agents/douyin/workbench")
    assert get.json()["data"]["scheduler"]["benchmark_monitor"]["interval_minutes"] == 60


def test_hydrate_reads_scheduler(mxai_client: TestClient) -> None:
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench",
        json={"data": {"scheduler": {"benchmark_monitor": {"enabled": True, "interval_minutes": 30}}}},
    )
    ConfigManager.reset()
    from plugins.mxai.cfg.domains import ensure_config_runtime

    ensure_config_runtime()
    data = ConfigManager.get().read("agent.douyin.workbench")
    assert data["scheduler"]["benchmark_monitor"]["interval_minutes"] == 30


def test_invalid_interval_returns_422(mxai_client: TestClient) -> None:
    bad = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench",
        json={"data": {"scheduler": {"benchmark_monitor": {"interval_minutes": 5}}}},
    )
    assert bad.status_code == 422
    high = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench",
        json={"data": {"scheduler": {"benchmark_monitor": {"interval_minutes": 200}}}},
    )
    assert high.status_code == 422
