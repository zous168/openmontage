"""CR-168 阶段 3 · slug/inputs、重试 once、终态推进."""

from __future__ import annotations

from datetime import datetime, timedelta
from types import SimpleNamespace

from core.timeutil import BEIJING
from plugins.mxai.rpa_worker import automan_bridge as ab
from plugins.mxai.scheduler.moments_cron import (
    MOMENTS_MAX_ATTEMPTS,
    apply_item_fields,
    effective_publish_at,
    finalize_moments_publish,
    moments_once_schedule_iso,
    recover_orphaned_inflight,
)


def test_slug_and_inputs_moments_publish() -> None:
    assert ab.TASK_ACTION["moments_publish"] == "moments_post"
    assert ab.slug_for("moments_publish", "wechat") == "weixin_moments_post"
    out = ab._inputs_for(
        "moments_publish",
        {
            "content": "你好",
            "mode": "image",
            "visibility": "friends",
            "moments_id": "m1",
            "date": "2026-08-02",
            "time": "10:00",
            "image_paths": ["/tmp/a.jpg", "/tmp/b.jpg"],
            "material_ids": ["11", "12"],
            "retry_index": 2,
        },
    )
    assert out["visibility"] == "friends"
    assert out["content"] == "你好"
    assert out["image_paths"] == ["/tmp/a.jpg", "/tmp/b.jpg"]
    assert out["material_ids"] == ["11", "12"]
    assert out["retry_index"] == 2
    assert out["moments_id"] == "m1"


def test_next_attempt_at_drives_once_iso() -> None:
    moments = {
        "enabled": True,
        "days": {
            "2026-08-01": [
                {
                    "id": "m1",
                    "time": "08:00",
                    "status": "scheduled",
                    "mode": "text",
                    "content": "x",
                    "retry_count": 1,
                    "next_attempt_at": "2026-08-02T12:05:00",
                }
            ]
        },
    }
    iso = moments_once_schedule_iso(moments)
    assert iso == "2026-08-02T12:05:00"
    pub = effective_publish_at("2026-08-01", moments["days"]["2026-08-01"][0])
    assert pub is not None
    assert pub.hour == 12 and pub.minute == 5


def test_recover_orphaned_queued() -> None:
    moments = {
        "days": {
            "2026-08-01": [
                {"id": "stuck", "status": "queued", "time": "10:00", "retry_count": 2},
                {"id": "alive", "status": "queued", "time": "11:00"},
            ]
        }
    }
    n = recover_orphaned_inflight(moments, active_moments_ids={"alive"})
    assert n == 1
    assert moments["days"]["2026-08-01"][0]["status"] == "scheduled"
    assert moments["days"]["2026-08-01"][0]["retry_count"] == 0
    assert moments["days"]["2026-08-01"][1]["status"] == "queued"


def test_mark_moments_queued_and_revert(monkeypatch) -> None:
    from plugins.mxai.scheduler.moments_cron import (
        mark_moments_queued,
        revert_moments_to_scheduled,
    )

    store = {
        "moments": {
            "enabled": True,
            "days": {
                "2026-08-06": [
                    {
                        "id": "m1",
                        "status": "running",
                        "time": "10:00",
                        "mode": "text",
                        "content": "x",
                    }
                ]
            },
        }
    }

    class FakeCM:
        @staticmethod
        def get():
            return FakeCM()

        def read(self, _domain):
            return store

        def patch(self, _domain, data):
            if "moments" in data:
                store["moments"] = data["moments"]

    monkeypatch.setattr("plugins.mxai.cfg.manager.ConfigManager.get", FakeCM.get)
    monkeypatch.setattr(
        "plugins.mxai.scheduler.moments_cron._resync",
        lambda *_a, **_k: None,
    )
    task = SimpleNamespace(
        task_type="moments_publish",
        payload={"moments_id": "m1", "date": "2026-08-06"},
    )
    mark_moments_queued(task)
    assert store["moments"]["days"]["2026-08-06"][0]["status"] == "queued"
    store["moments"]["days"]["2026-08-06"][0]["status"] = "running"
    revert_moments_to_scheduled(task)
    item = store["moments"]["days"]["2026-08-06"][0]
    assert item["status"] == "scheduled"
    assert item.get("retry_count") == 0


def test_finalize_retry_then_failed(monkeypatch) -> None:
    store = {
        "moments": {
            "enabled": True,
            "days": {
                "2026-08-02": [
                    {
                        "id": "m-retry",
                        "status": "running",
                        "time": "10:00",
                        "mode": "text",
                        "content": "hi",
                        "retry_count": 0,
                        "visibility": "public",
                    }
                ]
            },
        }
    }
    patches: list[dict] = []

    class FakeCM:
        @staticmethod
        def get():
            return FakeCM()

        def read(self, _domain):
            return store

        def patch(self, _domain, data):
            patches.append(data)
            if "moments" in data:
                store["moments"] = data["moments"]

    monkeypatch.setattr("plugins.mxai.cfg.manager.ConfigManager.get", FakeCM.get)
    monkeypatch.setattr(
        "plugins.mxai.scheduler.moments_cron._resync",
        lambda *_a, **_k: None,
    )

    task = SimpleNamespace(
        task_type="moments_publish",
        payload={"moments_id": "m-retry", "date": "2026-08-02"},
    )
    r1 = finalize_moments_publish(task, success=False, fail_reason="boom")
    assert r1["status"] == "retry_scheduled"
    item = store["moments"]["days"]["2026-08-02"][0]
    assert item["status"] == "scheduled"
    assert item["retry_count"] == 1
    assert item.get("next_attempt_at")

    # 再失败到上限前
    item["status"] = "running"
    item["retry_count"] = MOMENTS_MAX_ATTEMPTS - 1
    r2 = finalize_moments_publish(task, success=False, fail_reason="boom2")
    assert r2["status"] == "failed"
    assert item["status"] == "failed"
    assert item["retry_count"] == MOMENTS_MAX_ATTEMPTS
    assert "next_attempt_at" not in item


def test_finalize_success(monkeypatch) -> None:
    store = {
        "moments": {
            "enabled": True,
            "days": {
                "2026-08-02": [
                    {
                        "id": "m-ok",
                        "status": "running",
                        "time": "10:00",
                        "mode": "text",
                        "content": "ok",
                        "retry_count": 1,
                        "next_attempt_at": "2026-08-02T10:05:00",
                    }
                ]
            },
        }
    }

    class FakeCM:
        @staticmethod
        def get():
            return FakeCM()

        def read(self, _domain):
            return store

        def patch(self, _domain, data):
            if "moments" in data:
                store["moments"] = data["moments"]

    monkeypatch.setattr("plugins.mxai.cfg.manager.ConfigManager.get", FakeCM.get)
    monkeypatch.setattr(
        "plugins.mxai.scheduler.moments_cron._resync",
        lambda *_a, **_k: None,
    )
    task = SimpleNamespace(
        task_type="moments_publish",
        payload={"moments_id": "m-ok", "date": "2026-08-02"},
    )
    r = finalize_moments_publish(task, success=True)
    assert r["status"] == "done"
    item = store["moments"]["days"]["2026-08-02"][0]
    assert item["status"] == "done"
    assert "next_attempt_at" not in item


def test_force_overrides_not_due() -> None:
    now = datetime(2026, 8, 1, 7, 0, 0, tzinfo=BEIJING)
    moments = {
        "enabled": True,
        "days": {
            "2026-08-01": [
                {
                    "id": "future",
                    "time": "18:00",
                    "status": "scheduled",
                    "mode": "text",
                    "content": "later",
                }
            ]
        },
    }
    from plugins.mxai.scheduler.moments_cron import plan_skip_and_pick

    plan = plan_skip_and_pick(moments, now=now)
    assert plan["action"] == "not_due"
    # force 语义：run_moments_enqueue 在 not_due 时改 enqueue（单测此处只验 plan 仍 not_due）
    assert plan["target"]["id"] == "future"


def test_apply_item_fields_clear() -> None:
    moments = {
        "days": {
            "2026-08-01": [
                {"id": "a", "status": "queued", "next_attempt_at": "x", "retry_count": 1}
            ]
        }
    }
    assert apply_item_fields(
        moments,
        date_key="2026-08-01",
        item_id="a",
        fields={"status": "scheduled"},
        clear_keys=["next_attempt_at"],
    )
    assert moments["days"]["2026-08-01"][0]["status"] == "scheduled"
    assert "next_attempt_at" not in moments["days"]["2026-08-01"][0]
