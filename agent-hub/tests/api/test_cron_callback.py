"""Hermes cron 通用回调端点（POST /api/cron/jobs/{id}/callback）：用 job 自己的 deliver
通道投 message + mark_job_run 更新状态。http job 每次执行后由 _run_http_job 打这里。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest


def test_cron_callback_delivers_message_and_marks_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    from cron.jobs import create_job
    from hermes_cli.web_routes import cron as cron_routes

    create_job(
        prompt="x",
        schedule="every 30m",
        id="mxai-test-cb",
        deliver="clawbot",
        http={"url": "http://x", "callback": "http://cb"},
    )

    delivered: dict = {}
    marked: dict = {}

    def _fake_deliver(job, content, **kwargs):  # noqa: ANN001
        delivered["content"] = content
        return None

    def _fake_mark(job_id, success, error=None, delivery_error=None):  # noqa: ANN001
        marked.update({"job_id": job_id, "success": success, "delivery_error": delivery_error})

    monkeypatch.setattr("cron.scheduler._deliver_result", _fake_deliver)
    monkeypatch.setattr("cron.jobs.mark_job_run", _fake_mark)
    monkeypatch.setattr(cron_routes, "_find_cron_job_profile", lambda jid: "default")
    monkeypatch.setattr(cron_routes, "_cron_profile_home", lambda p: ("default", tmp_path))

    body = cron_routes.CronCallbackBody(success=True, message="已发送 3 条回访")
    res = asyncio.run(cron_routes.cron_job_callback("mxai-test-cb", body, profile="default"))

    assert res["ok"] is True
    assert delivered["content"] == "已发送 3 条回访"  # 用 job.deliver 通道投 message
    assert marked["success"] is True  # 更新执行状态
