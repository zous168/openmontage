"""方案 C：profile 异步 reconcile 合并与串行."""

from __future__ import annotations

import threading
import time

from plugins.mxai.scheduler import profile_reconcile as pr


def test_schedule_coalesces_to_latest(monkeypatch) -> None:
    pr.reset_profile_reconcile_state()
    calls: list[tuple] = []
    gate = threading.Event()
    entered = threading.Event()

    def fake_sync(profile_id, workbench=None):
        entered.set()
        gate.wait(timeout=2)
        calls.append((profile_id, (workbench or {}).get("n")))

    monkeypatch.setattr(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        fake_sync,
    )
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.monitor_control.dispatch_monitor_for_module",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.inbound_listen_cron.reconcile_boss_listen",
        lambda *a, **k: None,
    )

    pr.schedule_profile_reconcile("douyin", workbench={"n": 1})
    assert entered.wait(timeout=2)
    pr.schedule_profile_reconcile("douyin", workbench={"n": 2})
    pr.schedule_profile_reconcile("douyin", workbench={"n": 3})
    gate.set()
    pr.flush_profile_reconcile("douyin")

    assert calls[0] == ("douyin", 1)
    assert calls[-1] == ("douyin", 3)
    assert len(calls) <= 3


def test_flush_waits_until_idle(monkeypatch) -> None:
    pr.reset_profile_reconcile_state()
    done = []

    def slow_sync(profile_id, workbench=None):
        time.sleep(0.05)
        done.append(profile_id)

    monkeypatch.setattr(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        slow_sync,
    )
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.monitor_control.dispatch_monitor_for_module",
        lambda *a, **k: None,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.inbound_listen_cron.reconcile_boss_listen",
        lambda *a, **k: None,
    )

    pr.schedule_profile_reconcile("wechat", workbench={})
    pr.flush_profile_reconcile("wechat")
    assert done == ["wechat"]
