"""批量加好友 Cron：interval_minutes + tick fan-out 1 条."""

from __future__ import annotations

from plugins.mxai.cfg.config_sanitize import sanitize_workbench_fields
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.contacts.structured_parser import ContactRow
from plugins.mxai.crm.add_records import service as add_svc
from plugins.mxai.scheduler.add_friends_cron import run_add_friends_enqueue
from plugins.mxai.scheduler.cron import compute_mxai_job_enabled, sync_add_friends_job
from plugins.mxai.scheduler.cron_schedule_expr import (
    add_friends_schedule,
    resolve_add_interval_minutes,
)


def test_resolve_add_interval_minutes_prefers_minutes() -> None:
    assert resolve_add_interval_minutes({"interval_minutes": 12, "interval_sec": 3}) == 12


def test_resolve_add_interval_minutes_legacy_sec_as_minutes() -> None:
    """旧键 interval_sec 标签即「分」，按分钟读."""
    assert resolve_add_interval_minutes({"interval_sec": 8}) == 8
    assert resolve_add_interval_minutes({}) == 6


def test_sanitize_migrates_interval_sec_to_minutes() -> None:
    out = sanitize_workbench_fields(
        {"add_friends": {"interval_sec": 9, "run_window": {"start": "09:00", "end": "18:00"}}},
        strict=True,
    )
    assert out["add_friends"]["interval_minutes"] == 9
    assert "interval_sec" not in out["add_friends"]


def test_add_friends_schedule_window_and_interval() -> None:
    wb = {
        "add_friends": {
            "interval_minutes": 6,
            "run_window": {"start": "09:00", "end": "18:00"},
        }
    }
    assert add_friends_schedule(wb, profile_id="wechat") == "*/6 9-18 * * *"


def test_batch_add_schedule_qiyeweixin() -> None:
    wb = {
        "batch_add": {
            "interval_minutes": 10,
            "run_window": {"start": "00:00", "end": "23:59"},
        }
    }
    assert add_friends_schedule(wb, profile_id="qiyeweixin") == "*/10 * * * *"


def test_feature_gate_reads_section_enabled(monkeypatch) -> None:
    monkeypatch.setattr("plugins.mxai.scheduler.cron._g1_scheduler_active", lambda: True)
    monkeypatch.setattr("plugins.mxai.cfg.run_enabled.is_run_enabled", lambda _pid: True)
    wb_on = {"add_friends": {"enabled": True}}
    wb_off = {"add_friends": {"enabled": False}}
    assert compute_mxai_job_enabled("wechat", "add_friends", wb_on) is True
    assert compute_mxai_job_enabled("wechat", "add_friends", wb_off) is False
    assert compute_mxai_job_enabled(
        "qiyeweixin", "add_friends", {"batch_add": {"enabled": False}}
    ) is False


def test_sync_add_friends_job_payload(monkeypatch, mxai_env) -> None:
    captured: dict = {}

    def _fake_sync(profile_home, **kwargs):
        captured.update(kwargs)
        captured["profile_home"] = profile_home
        return {"id": kwargs["job_id"]}, True

    monkeypatch.setattr("plugins.mxai.scheduler.cron._sync_mxai_job", _fake_sync)
    monkeypatch.setattr("plugins.mxai.scheduler.cron._g1_scheduler_active", lambda: True)
    monkeypatch.setattr("plugins.mxai.cfg.run_enabled.is_run_enabled", lambda _pid: True)

    wb = {
        "add_friends": {
            "enabled": True,
            "interval_minutes": 6,
            "run_window": {"start": "09:00", "end": "18:00"},
        }
    }
    row = sync_add_friends_job("wechat", wb)
    assert row is not None
    assert row["job_id"] == "mxai-wechat-add_friends"
    assert row["schedule"] == "*/6 9-18 * * *"
    assert row["enabled"] is True
    assert captured["http"]["url"].endswith("/cron/run/add_friends/wechat")


def test_cron_tick_enqueues_one_pending(mxai_env, monkeypatch) -> None:
    add_svc.import_rows(
        "wechat",
        [
            ContactRow(display_name="A", contact_id="c1", row_num=1),
            ContactRow(display_name="B", contact_id="c2", row_num=2),
        ],
    )
    ConfigManager.get().patch(
        "agent.wechat.workbench",
        {
            "add_friends": {
                "enabled": True,
                "interval_minutes": 6,
                "greeting": "hi",
                "run_window": {"start": "00:00", "end": "23:59"},
            }
        },
    )
    monkeypatch.setattr("plugins.mxai.cfg.run_enabled.is_run_enabled", lambda _pid: True)
    from plugins.mxai.orchestrator.queue_manager import QueueManager

    QueueManager.get().arm_work()

    r1 = run_add_friends_enqueue("wechat", source="cron", operator="Cron")
    assert r1.get("ok") is True
    assert r1.get("queued") == 1
    assert len(r1.get("task_ids") or []) == 1

    r2 = run_add_friends_enqueue("wechat", source="cron", operator="Cron")
    assert r2.get("skipped") == "previous_still_running"

    task = QueueManager.get().get_task(r1["task_ids"][0])
    assert task is not None
    assert task.payload.get("source") == "cron"
    assert task.payload.get("greeting") == "hi"
