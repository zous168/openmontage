"""LT-038.03：全局维护 job（default HERMES_HOME）+ 业务 job 用 http 执行类型（方案 A）."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def default_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "hub"
    home.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(home))
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: home if name == "default" else home / "profiles" / name,
    )
    return home


def test_sync_maintenance_job_creates_http_job(default_home: Path) -> None:
    from agent.profile_scope import hermes_profile_scope
    from cron.jobs import resolve_job_ref
    from plugins.mxai.scheduler.cron import (
        MAINTENANCE_JOB_ID,
        MAINTENANCE_JOB_NAME,
        sync_maintenance_job,
    )

    row = sync_maintenance_job()
    assert row is not None
    assert row["ensured"] is True
    assert row["job_id"] == MAINTENANCE_JOB_ID == "mxai-maintenance-daily_report"
    assert row["job_name"] == MAINTENANCE_JOB_NAME
    assert row["schedule"] == "every 1440m"

    with hermes_profile_scope(default_home):
        job = resolve_job_ref(MAINTENANCE_JOB_ID)
    assert job is not None
    assert job["id"] == MAINTENANCE_JOB_ID
    assert job["name"] == MAINTENANCE_JOB_NAME
    # http 执行类型（非脚本）：url 指向 gateway 内 cron-run 端点
    http = job.get("http")
    assert http and "/api/plugins/mxai/cron/run/maintenance/default" in http["url"]
    assert job.get("script") is None


def test_business_job_uses_http_not_script(default_home: Path) -> None:
    """业务 job 用 http 执行类型（打 gateway cron-run 端点），不再生成/依赖脚本."""
    from agent.profile_scope import hermes_profile_scope
    from cron.jobs import resolve_job_ref
    from plugins.mxai.scheduler.cron import scheduled_touch_job_id, sync_scheduled_touch_job

    wb = {"scheduler": {"scheduled_touch": {"enabled": True, "mode": "segmented", "interval_minutes": 30}}}
    row = sync_scheduled_touch_job("wechat", wb)
    assert row and row.get("ensured")

    with hermes_profile_scope(default_home / "profiles" / "wechat"):
        job = resolve_job_ref(scheduled_touch_job_id("wechat"))
    http = job.get("http")
    assert http and "/api/plugins/mxai/cron/run/scheduled_touch/wechat" in http["url"]
    assert http["method"] == "POST"
    assert job.get("script") is None


def test_sync_maintenance_job_idempotent(default_home: Path) -> None:
    from agent.profile_scope import hermes_profile_scope
    from cron.jobs import list_jobs
    from plugins.mxai.scheduler.cron import MAINTENANCE_JOB_ID, sync_maintenance_job

    sync_maintenance_job()
    sync_maintenance_job()  # create-if-absent：二次不重复建

    with hermes_profile_scope(default_home):
        jobs = [j for j in list_jobs(include_disabled=True) if j.get("id") == MAINTENANCE_JOB_ID]
    assert len(jobs) == 1
