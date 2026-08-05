"""CR-163：Boss inbound_listen Cron + enqueue 短时 listen + 终态不恢复听."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from plugins.mxai.cfg.agent_bindings import agent_profile_for_channel
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.scheduler.cron import (
    compute_mxai_job_enabled,
    inbound_listen_job_id,
    inbound_listen_stop_job_id,
    sync_inbound_listen_job,
    sync_inbound_listen_stop_job,
)
from plugins.mxai.scheduler.cron_schedule_expr import (
    inbound_listen_schedule,
    inbound_listen_stop_schedule,
)
from plugins.mxai.scheduler.inbound_listen_cron import (
    reconcile_boss_listen,
    run_inbound_listen_stop,
)
from plugins.mxai.orchestrator.inbound_listen_coord import (
    mark_channel_replying,
    maybe_resume_listen,
)
from plugins.mxai.rpa_worker import automan_bridge as ab


@pytest.fixture
def sync_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: data_dir)
    monkeypatch.setattr("plugins.mxai.scheduler.state.resolve_hub_data_dir_path", lambda: data_dir)
    profiles = data_dir / "profiles"
    for name in sorted({agent_profile_for_channel("boss")} | {"boss_dm", "boss_resume"}):
        p = profiles / name
        p.mkdir(parents=True, exist_ok=True)
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
    ConfigManager.reset()
    monkeypatch.setattr("hermes_cli.profiles.get_profile_dir", lambda name: profiles / name)
    ensure_runtime_bootstrap(data_dir)
    ensure_config_runtime()
    monkeypatch.setattr("plugins.mxai.scheduler.cron._g1_scheduler_active", lambda: True)
    monkeypatch.setattr("plugins.mxai.cfg.run_enabled.is_run_enabled", lambda _pid: True)
    return data_dir


def _boss_wb(*, start="09:00", end="18:00", interval=30, enabled=True) -> dict:
    return {
        "boss": {
            "inbound_reply_enabled": enabled,
            "inbound_reply": {
                "interval_minutes": interval,
                "run_window": {"start": start, "end": end},
            },
        },
        "agent_bindings": {
            "default": "boss_dm",
            "modules": {"inbound_reply": "boss_dm"},
        },
    }


def test_inbound_listen_slug_maps_to_boss_listen() -> None:
    assert ab.TASK_ACTION["inbound_listen"] == "listen"
    assert ab.slug_for("inbound_listen", "boss") == "boss_listen"
    assert "inbound_listen" in ab.CHANNEL_RPA_TASK_TYPES["boss"]


def test_inbound_listen_schedules() -> None:
    wb = _boss_wb(start="09:30", end="18:15", interval=20)
    assert inbound_listen_schedule(wb) == "*/20 9-18 * * *"
    assert inbound_listen_stop_schedule(wb) == "15 18 * * *"


def test_empty_window_disables_jobs(monkeypatch) -> None:
    monkeypatch.setattr("plugins.mxai.scheduler.cron._g1_scheduler_active", lambda: True)
    monkeypatch.setattr("plugins.mxai.cfg.run_enabled.is_run_enabled", lambda _pid: True)
    empty = _boss_wb(start="", end="")
    ok = _boss_wb()
    assert compute_mxai_job_enabled("boss", "inbound_listen", empty) is False
    assert compute_mxai_job_enabled("boss", "inbound_listen_stop", empty) is False
    assert compute_mxai_job_enabled("boss", "inbound_listen", ok) is True
    assert compute_mxai_job_enabled("wechat", "inbound_listen", ok) is False


def test_sync_inbound_listen_jobs(sync_env: Path) -> None:
    wb = _boss_wb(start="08:05", end="19:40", interval=15)
    start_row = sync_inbound_listen_job("boss", wb)
    stop_row = sync_inbound_listen_stop_job("boss", wb)
    assert start_row is not None and start_row["enabled"] is True
    assert stop_row is not None and stop_row["enabled"] is True
    assert start_row["job_id"] == inbound_listen_job_id("boss")
    assert stop_row["job_id"] == inbound_listen_stop_job_id("boss")


def _patch_reconcile_deps(monkeypatch, *, scheduler_active: bool = True) -> MagicMock:
    """返回 Fake QueueManager（含 enqueue / count_inflight）。"""
    enqueued: list[dict] = []

    class _FakeTask:
        def __init__(self) -> None:
            self.task_id = "tsk_listen_1"

    class _FakeQ:
        @staticmethod
        def is_work_armed() -> bool:
            return True

        @staticmethod
        def is_scheduler_active() -> bool:
            return scheduler_active

        @staticmethod
        def count_inflight_tasks(_pid: str, _types: set) -> int:
            return 0

        @staticmethod
        def enqueue(**kwargs):
            enqueued.append(kwargs)
            return _FakeTask()

    fake_q = _FakeQ()
    fake_q.enqueued = enqueued  # type: ignore[attr-defined]

    monkeypatch.setattr(
        "plugins.mxai.cfg.manager.ConfigManager.get",
        lambda: type(
            "CM",
            (),
            {"read": staticmethod(lambda _k: _boss_wb())},
        )(),
    )
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.queue_manager.QueueManager.get",
        lambda: fake_q,
    )
    monkeypatch.setattr("plugins.mxai.cfg.run_enabled.is_run_enabled", lambda _pid: True)
    monkeypatch.setattr(
        "plugins.mxai.cfg.module_enabled.read_module_enabled",
        lambda _pid, _mid: True,
    )
    return fake_q


def test_reconcile_outside_window_stops(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, list(monitor_slugs or [])))
            return True

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge",
        lambda: _FakeBridge(),
    )
    fake_q = _patch_reconcile_deps(monkeypatch)

    out = reconcile_boss_listen(now_hm="20:00")
    assert out["action"] == "stop"
    assert out["should_start"] is False
    assert calls[-1] == ("stop", ["boss_listen"])
    assert fake_q.enqueued == []

    calls.clear()
    out2 = reconcile_boss_listen(now_hm="12:00")
    assert out2["action"] == "enqueue"
    assert out2["should_start"] is True
    assert out2["enqueued"] == 1
    assert out2["task_id"] == "tsk_listen_1"
    assert calls == []
    assert fake_q.enqueued[-1]["task_type"] == "inbound_listen"
    assert fake_q.enqueued[-1]["name"] == "监听"


def test_reconcile_global_pause_stops(monkeypatch) -> None:
    """全局暂停时即使已开工、在窗内，也只能 stop，不得入队."""
    calls: list[tuple[str, list[str]]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, list(monitor_slugs or [])))
            return True

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge",
        lambda: _FakeBridge(),
    )
    fake_q = _patch_reconcile_deps(monkeypatch, scheduler_active=False)

    out = reconcile_boss_listen(now_hm="12:00")
    assert out["should_start"] is False
    assert out["action"] == "stop"
    assert calls[-1] == ("stop", ["boss_listen"])
    assert fake_q.enqueued == []


def test_reconcile_skips_when_already_inflight(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge",
        lambda: type("B", (), {"send_monitor": staticmethod(lambda *_a, **_k: True)})(),
    )
    fake_q = _patch_reconcile_deps(monkeypatch)

    def _inflight(_pid: str, _types: set) -> int:
        return 1

    monkeypatch.setattr(
        fake_q,
        "count_inflight_tasks",
        staticmethod(_inflight),
    )
    # replace QueueManager.get to return same fake with patched method
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.queue_manager.QueueManager.get",
        lambda: fake_q,
    )
    fake_q.count_inflight_tasks = staticmethod(lambda _p, _t: 1)  # type: ignore[method-assign]

    out = reconcile_boss_listen(now_hm="12:00")
    assert out["action"] == "enqueue"
    assert out.get("skipped") == "already_inflight"
    assert out["enqueued"] == 0
    assert fake_q.enqueued == []


def test_boss_maybe_resume_listen_skipped(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, list(monitor_slugs or [])))
            return True

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: _FakeBridge(),
    )
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.inbound_listen_coord.listen_three_gates_open",
        lambda *_a, **_k: True,
    )
    mark_channel_replying("boss")
    assert maybe_resume_listen("boss", in_flight_count=0) is False
    assert calls == []

    mark_channel_replying("wechat")
    assert maybe_resume_listen("wechat", in_flight_count=0) is True
    assert calls[-1][0] == "start"


def test_wechat_maybe_resume_requires_three_gates(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, list(monitor_slugs or [])))
            return True

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: _FakeBridge(),
    )
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.inbound_listen_coord.listen_three_gates_open",
        lambda *_a, **_k: False,
    )
    mark_channel_replying("wechat")
    assert maybe_resume_listen("wechat", in_flight_count=0) is False
    assert calls == []


def test_run_inbound_listen_stop(monkeypatch) -> None:
    calls: list[tuple[str, list[str]]] = []

    class _FakeBridge:
        def send_monitor(self, action: str, monitor_slugs=None) -> bool:
            calls.append((action, list(monitor_slugs or [])))
            return True

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.monitor_control.get_rpa_worker_bridge",
        lambda: _FakeBridge(),
    )
    out = run_inbound_listen_stop("boss")
    assert out["ok"] is True
    assert calls == [("stop", ["boss_listen"])]
