"""CR-64：统计周期只读 + 执行日志监控."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.reports.service import put_report_schedule
from plugins.mxai.scheduler import maintenance
from plugins.mxai.worklog.service import append_worklog


@pytest.fixture
def cron_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
    QueueManager.reset()
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profiles / name,
    )
    ensure_runtime_bootstrap(data_dir)
    return data_dir


def test_stats_period_readonly(mxai_client: TestClient) -> None:
    res = mxai_client.get("/api/plugins/mxai/stats/period")
    assert res.status_code == 200
    body = res.json()
    assert body.get("readonly") is True
    assert body.get("summary_range_days") == 7
    assert len(body.get("report_periods") or []) == 3
    assert body.get("cron_mode") in ("mock", "real")
    assert "scheduler_active" in body


def test_stats_period_scheduler_jobs(mxai_client: TestClient) -> None:
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench",
        json={"data": {"scheduler": {"benchmark_monitor": {"enabled": True, "interval_minutes": 45}}}},
    )
    body = mxai_client.get("/api/plugins/mxai/stats/period").json()
    job_ids = [j["job_id"] for j in body.get("cron_jobs") or []]
    assert "mxai-douyin-benchmark_monitor" in job_ids
    dy = next(j for j in body["cron_jobs"] if j["job_id"] == "mxai-douyin-benchmark_monitor")
    assert "45" in dy["schedule_text"]
    assert "scheduler_active" in body
    assert isinstance(body["scheduler_active"], bool)
    report = next(j for j in body["cron_jobs"] if j["job_id"] == "mxai-maintenance-daily_report")
    assert "real 模式" not in report["schedule_text"]
    if body.get("cron_mode") == "mock":
        assert report["schedule_text"] == "联调 · 手动触发"
    else:
        assert report["schedule_text"] == "每 24 小时"


def test_worklog_monitor(mxai_client: TestClient) -> None:
    append_worklog(
        profile_id="douyin",
        op_type="评论采集",
        exec_status="成功",
        op_object="用户A",
    )
    res = mxai_client.get("/api/plugins/mxai/worklogs/monitor?limit=5")
    assert res.status_code == 200
    body = res.json()
    assert body.get("items")
    assert "today_total" in body.get("counters", {})
    assert body.get("polled_at")


def test_cron_generates_report_when_daily_enabled(cron_env: Path) -> None:
    put_report_schedule({"daily": {"enabled": True, "hour": 8}}, data_dir=cron_env)
    result = maintenance.run_minimal_report()
    assert result["ok"] is True
    assert result.get("reports")
    assert any(r.get("ok") for r in result["reports"])
    cleanup = result.get("cleanup") or {}
    assert cleanup.get("ok") is True
    assert "keep_days" in cleanup


def test_cron_worklog_cleanup_deletes_old(cron_env: Path) -> None:
    import sqlite3

    from plugins.mxai.worklog.service import _db_path

    db = _db_path(cron_env)
    conn = sqlite3.connect(db)
    conn.execute(
        """
        INSERT INTO work_logs (
            log_id, op_time, profile_id, op_type, op_object,
            exec_status, fail_reason, elapsed_ms, task_id
        ) VALUES ('log_cron_old', datetime('now', '-45 days'), 'douyin', 'stale', '', '成功', NULL, NULL, NULL)
        """
    )
    conn.commit()
    conn.close()

    result = maintenance.run_minimal_report()
    assert result["ok"] is True
    assert result.get("cleanup", {}).get("deleted", 0) >= 1

    conn = sqlite3.connect(db)
    row = conn.execute("SELECT COUNT(*) FROM work_logs WHERE log_id = 'log_cron_old'").fetchone()
    conn.close()
    assert int(row[0]) == 0
