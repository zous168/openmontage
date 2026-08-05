"""常驻监听 REST 三级粒度控制."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.cfg.run_enabled import set_run_enabled
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.scheduler.profile_reconcile import flush_profile_reconcile


def _flush(*profiles: str) -> None:
    if profiles:
        for pid in profiles:
            flush_profile_reconcile(pid)
    else:
        flush_profile_reconcile()


def _enable_channels(mxai_client: TestClient, *channels: str) -> None:
    for ch in channels:
        mxai_client.post(f"/api/plugins/mxai/run/agents/{ch}/start")
    _flush(*channels)


def _patch_inbound(mxai_client: TestClient, channel: str, *, enabled: bool) -> None:
    mxai_client.patch(
        f"/api/plugins/mxai/agents/{channel}/modules/inbound_reply",
        json={"enabled": enabled},
    )
    _flush(channel)


def _set_boss_listen_window(
    mxai_client: TestClient,
    *,
    start: str = "00:00",
    end: str = "23:59",
    interval: int = 30,
) -> None:
    """CR-163：Boss 监听须配齐窗，否则 reconcile/start 不会拉起 boss_listen."""
    res = mxai_client.put(
        "/api/plugins/mxai/agents/boss/workbench",
        json={
            "data": {
                "boss": {
                    "inbound_reply": {
                        "interval_minutes": interval,
                        "run_window": {"start": start, "end": end},
                    }
                }
            }
        },
    )
    assert res.status_code == 200
    _flush("boss")


def test_list_monitors_catalog(mxai_client: TestClient) -> None:
    res = mxai_client.get("/api/plugins/mxai/run/monitors")
    assert res.status_code == 200
    items = res.json()["items"]
    slugs = {it["slug"] for it in items}
    assert "weixin_listen" in slugs
    assert "boss_listen" in slugs


def test_list_monitors_filter_channel(mxai_client: TestClient) -> None:
    res = mxai_client.get("/api/plugins/mxai/run/monitors", params={"channel": "wechat"})
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["slug"] == "weixin_listen"


def test_control_monitor_single_slug(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())

    res = mxai_client.post(
        "/api/plugins/mxai/run/monitors/stop",
        json={"slugs": ["weixin_listen"]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["sent"] is True
    assert body["monitor_slugs"] == ["weixin_listen"]
    assert calls == [("stop", ["weixin_listen"])]


def test_control_monitor_channel_all(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())

    _enable_channels(mxai_client, "wechat", "boss")
    _set_boss_listen_window(mxai_client)
    _patch_inbound(mxai_client, "wechat", enabled=True)
    _patch_inbound(mxai_client, "boss", enabled=True)
    QueueManager.get().arm_work()

    res = mxai_client.post(
        "/api/plugins/mxai/run/monitors/start",
        json={"channels": ["wechat", "boss"]},
    )
    assert res.status_code == 200
    # CR-163：Boss listen 禁止 monitor.start，仅 weixin 常驻
    assert set(res.json()["monitor_slugs"]) == {"weixin_listen"}


def test_control_monitor_channel_task_type(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())

    res = mxai_client.post(
        "/api/plugins/mxai/run/monitors/stop",
        json={"channels": ["wechat"], "task_types": ["inbound_reply"]},
    )
    assert res.status_code == 200
    assert res.json()["monitor_slugs"] == ["weixin_listen"]


def test_control_monitor_scope_all(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())

    res = mxai_client.post(
        "/api/plugins/mxai/run/monitors/stop",
        json={"scope": "all"},
    )
    assert res.status_code == 200
    slugs = set(res.json()["monitor_slugs"])
    assert "weixin_listen" in slugs
    assert "qiwei_listen" in slugs
    assert "boss_listen" in slugs


def test_control_monitor_via_agent_alias(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())

    _enable_channels(mxai_client, "wechat")
    _patch_inbound(mxai_client, "wechat", enabled=True)
    QueueManager.get().arm_work()

    res = mxai_client.post(
        "/api/plugins/mxai/run/monitors/start",
        json={"agents": ["wechat"]},
    )
    assert res.status_code == 200
    assert res.json()["monitor_slugs"] == ["weixin_listen"]


def test_control_monitor_task_types_across_channels(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())

    res = mxai_client.post(
        "/api/plugins/mxai/run/monitors/stop",
        json={"task_types": ["inbound_reply"]},
    )
    assert res.status_code == 200
    slugs = set(res.json()["monitor_slugs"])
    assert slugs == {"weixin_listen", "qiwei_listen", "boss_listen"}


def test_control_monitor_empty_targets_400(mxai_client: TestClient) -> None:
    res = mxai_client.post(
        "/api/plugins/mxai/run/monitors/start",
        json={"channels": ["douyin"]},
    )
    assert res.status_code == 400


def test_control_monitor_explicit_empty_slugs_400(mxai_client: TestClient) -> None:
    """显式 slugs=[] 或全空白不得回落为 scope=all。"""
    res = mxai_client.post(
        "/api/plugins/mxai/run/monitors/stop",
        json={"slugs": []},
    )
    assert res.status_code == 400

    res2 = mxai_client.post(
        "/api/plugins/mxai/run/monitors/stop",
        json={"slugs": ["", "  "]},
    )
    assert res2.status_code == 400


def test_start_work_skips_disabled_inbound_module(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()

    _enable_channels(mxai_client, "wechat", "boss")
    _set_boss_listen_window(mxai_client)
    _patch_inbound(mxai_client, "wechat", enabled=False)
    _patch_inbound(mxai_client, "boss", enabled=True)
    mxai_client.post("/api/plugins/mxai/run/all/start")

    start_calls = [c for c in calls if c[0] == "start"]
    for _, slugs in start_calls:
        assert slugs is not None
        assert "weixin_listen" not in (slugs or [])
        assert "boss_listen" not in (slugs or [])
    # Boss 走队列入队，非 monitor.start
    q = QueueManager.get()
    listed = q.list_tasks(agent="boss", page_size=50)
    listen_tasks = [t for t in listed["items"] if t.get("task_type") == "inbound_listen"]
    assert len(listen_tasks) >= 1
    assert listen_tasks[0].get("name") == "监听"


def test_module_disable_stops_without_work_armed(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()

    _enable_channels(mxai_client, "wechat")
    mxai_client.post("/api/plugins/mxai/run/agents/wechat/start")
    mxai_client.post("/api/plugins/mxai/run/all/stop")

    off = mxai_client.patch(
        "/api/plugins/mxai/agents/wechat/modules/inbound_reply",
        json={"enabled": False},
    )
    assert off.status_code == 200
    assert "reconcile_rev" in off.json()
    _flush("wechat")
    assert calls[-1] == ("stop", ["weixin_listen"])


def test_module_toggle_sends_single_monitor(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()
    _enable_channels(mxai_client, "wechat")
    _patch_inbound(mxai_client, "wechat", enabled=True)
    mxai_client.post("/api/plugins/mxai/run/all/start")

    off = mxai_client.patch(
        "/api/plugins/mxai/agents/wechat/modules/inbound_reply",
        json={"enabled": False},
    )
    assert off.status_code == 200
    _flush("wechat")
    assert calls[-1] == ("stop", ["weixin_listen"])

    on = mxai_client.patch(
        "/api/plugins/mxai/agents/wechat/modules/inbound_reply",
        json={"enabled": True},
    )
    assert on.status_code == 200
    _flush("wechat")
    assert calls[-1] == ("start", ["weixin_listen"])


def test_start_work_skips_boss_when_channel_run_disabled(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()

    set_run_enabled("boss", False)
    _enable_channels(mxai_client, "wechat")
    _set_boss_listen_window(mxai_client)
    _patch_inbound(mxai_client, "wechat", enabled=True)
    _patch_inbound(mxai_client, "boss", enabled=True)
    mxai_client.post("/api/plugins/mxai/run/all/start")

    start_calls = [c for c in calls if c[0] == "start"]
    assert start_calls
    for _, slugs in start_calls:
        assert slugs is not None
        assert "boss_listen" not in (slugs or [])


def test_workbench_inbound_toggle_starts_listen_when_armed(
    mxai_client: TestClient, monkeypatch
) -> None:
    """页面开关走 PUT workbench：开工后再开模块须补发 monitor.start（三渠道）。"""
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()
    _enable_channels(mxai_client, "wechat")
    _patch_inbound(mxai_client, "wechat", enabled=False)
    mxai_client.post("/api/plugins/mxai/run/all/start")
    calls.clear()

    res = mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={"data": {"inbound_reply": {"enabled": True}}},
    )
    assert res.status_code == 200
    assert "reconcile_rev" in res.json()
    assert "monitor" not in res.json()
    _flush("wechat")
    assert calls[-1] == ("start", ["weixin_listen"])


def test_workbench_inbound_toggle_stops_listen(mxai_client: TestClient, monkeypatch) -> None:
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()
    _enable_channels(mxai_client, "qiyeweixin")
    _patch_inbound(mxai_client, "qiyeweixin", enabled=True)
    mxai_client.post("/api/plugins/mxai/run/all/start")
    calls.clear()

    res = mxai_client.put(
        "/api/plugins/mxai/agents/qiyeweixin/workbench",
        json={"data": {"inbound_reply": {"enabled": False}}},
    )
    assert res.status_code == 200
    assert "monitor" not in res.json()
    _flush("qiyeweixin")
    assert calls[-1] == ("stop", ["qiwei_listen"])


def test_workbench_boss_inbound_toggle_starts_listen(
    mxai_client: TestClient, monkeypatch
) -> None:
    """Boss 开模块 → reconcile 入队 inbound_listen，禁止 monitor.start."""
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()
    set_run_enabled("boss", True)
    # 先开工再开渠道，否则 agent/start 时 work 未 armed，reconcile 只会 stop
    mxai_client.post("/api/plugins/mxai/run/all/start")
    calls.clear()

    res = mxai_client.put(
        "/api/plugins/mxai/agents/boss/workbench",
        json={
            "data": {
                "boss": {
                    "inbound_reply_enabled": True,
                    "inbound_reply": {
                        "interval_minutes": 30,
                        "run_window": {"start": "00:00", "end": "23:59"},
                    },
                }
            }
        },
    )
    assert res.status_code == 200
    assert "monitor" not in res.json()
    _flush("boss")
    assert not any(c[0] == "start" and "boss_listen" in (c[1] or []) for c in calls)
    listed = QueueManager.get().list_tasks(agent="boss", page_size=50)
    listen_tasks = [t for t in listed["items"] if t.get("task_type") == "inbound_listen"]
    assert len(listen_tasks) >= 1


def test_workbench_inbound_unchanged_skips_monitor(mxai_client: TestClient, monkeypatch) -> None:
    """仅改其它字段时不重复发 monitor。"""
    calls: list[tuple[str, list[str] | None]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, monitor_slugs))
            return True

    monkeypatch.setattr("plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge", lambda: _FakeBridge())
    QueueManager.reset()
    _enable_channels(mxai_client, "wechat")
    _patch_inbound(mxai_client, "wechat", enabled=True)
    mxai_client.post("/api/plugins/mxai/run/all/start")
    calls.clear()

    res = mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={"data": {"inbound_reply": {"enabled": True}}},
    )
    assert res.status_code == 200
    assert "monitor" not in res.json()
    _flush("wechat")
    assert calls == []
