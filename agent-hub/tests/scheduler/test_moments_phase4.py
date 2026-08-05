"""CR-168 阶段 4 · force / 日上限 / Dashboard 模块块."""

from __future__ import annotations

from datetime import datetime

import pytest

from core.timeutil import BEIJING
from plugins.mxai.orchestrator import module_status as ms
from plugins.mxai.risk.engine import check_enqueue
from plugins.mxai.scheduler.moments_cron import plan_skip_and_pick, run_moments_enqueue


def test_wechat_modules_include_moments() -> None:
    ids = [m[0] for m in ms._WECHAT_MODULES]
    assert ids == ["add_friend", "inbound_reply", "scheduled_touch", "moments"]
    assert ms._TASK_TYPE_BY_MODULE["moments"] == "moments_publish"
    init, hint = ms._private_init(
        "wechat",
        "moments",
        {
            "moments": {
                "enabled": True,
                "days": {
                    "2026-08-10": [
                        {"id": "m1", "time": "10:00", "status": "scheduled", "mode": "text", "content": "hi"}
                    ]
                },
            }
        },
        {},
    )
    assert init == "ready"
    assert hint is None
    init2, hint2 = ms._private_init("wechat", "moments", {"moments": {"enabled": True, "days": {}}}, {})
    assert init2 == "missing_config"
    assert hint2 and "排期" in hint2


def test_check_enqueue_moments_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.risk.engine._load_risk",
        lambda _pid: {"enabled": True, "daily_moments_limit": 1},
    )
    monkeypatch.setattr(
        "plugins.mxai.risk.engine.count_success_today",
        lambda *_a, **_k: 1,
    )
    r = check_enqueue("wechat", "moments_publish")
    assert not r.allowed
    assert "daily_moments_limit" in r.reason


def test_run_moments_force_enqueues_early(monkeypatch: pytest.MonkeyPatch) -> None:
    now = datetime(2026, 8, 1, 7, 0, 0, tzinfo=BEIJING)
    store = {
        "moments": {
            "enabled": True,
            "days": {
                "2026-08-01": [
                    {
                        "id": "f1",
                        "time": "18:00",
                        "status": "scheduled",
                        "mode": "text",
                        "content": "evening",
                        "visibility": "public",
                        "retry_count": 0,
                    }
                ]
            },
        }
    }
    plan = plan_skip_and_pick(store["moments"], now=now)
    assert plan["action"] == "not_due"

    class FakeCM:
        @staticmethod
        def get():
            return FakeCM()

        def read(self, _d):
            return store

        def patch(self, _d, data):
            if "moments" in data:
                store["moments"] = data["moments"]

    enqueued = {}

    class FakeQueue:
        @staticmethod
        def get():
            return FakeQueue()

        def enqueue(self, **kwargs):
            enqueued.update(kwargs)
            return type("T", (), {"task_id": "t1"})()

    monkeypatch.setattr("plugins.mxai.cfg.manager.ConfigManager.get", FakeCM.get)
    monkeypatch.setattr(
        "plugins.mxai.cfg.run_enabled.is_run_enabled",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.module_enabled.read_module_enabled",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.queue_manager.QueueManager.get",
        FakeQueue.get,
    )
    monkeypatch.setattr(
        "plugins.mxai.agents.pipeline._match_sensitive",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.moments_cron._resync",
        lambda *_a, **_k: None,
    )

    res = run_moments_enqueue(
        "wechat",
        source="run_now",
        operator="Manual",
        now=now,
        force=True,
    )
    assert res.get("enqueued") == 1
    assert res.get("forced") is True
    assert enqueued.get("task_type") == "moments_publish"
    assert store["moments"]["days"]["2026-08-01"][0]["status"] == "queued"
