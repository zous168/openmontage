"""LT-018.01.02 scheduler_state 幂等游标."""

from __future__ import annotations

import json
from pathlib import Path

from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.scheduler.benchmark_monitor import run_benchmark_round, run_scheduled_touch_enqueue
from plugins.mxai.scheduler.state import (
    get_last_monitored_video,
    get_last_sent_date,
    load_scheduler_state,
    set_last_monitored_video,
    set_last_sent_date,
)


def test_same_video_idempotent(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    QueueManager.reset()
    profile = "douyin"
    handle = "@bench1"
    set_last_monitored_video(profile, handle, "mock-video-bench1", data_dir=tmp_path)
    assert get_last_monitored_video(profile, handle, data_dir=tmp_path) == "mock-video-bench1"


def test_t6_same_day_skips(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    set_last_sent_date("wechat", "2026-06-25", data_dir=tmp_path)
    assert get_last_sent_date("wechat", data_dir=tmp_path) == "2026-06-25"


def test_corrupt_state_degrades(tmp_path: Path) -> None:
    path = tmp_path / "scheduler_state.json"
    path.write_text("{not json", encoding="utf-8")
    state = load_scheduler_state(tmp_path)
    assert state == {"agents": {}}  # 仅幂等游标桶；jobs 桶已废弃（执行记录改 Hermes 原生）


def test_benchmark_round_idempotent(tmp_path: Path, monkeypatch) -> None:
    from plugins.mxai.cfg.domains import ensure_config_runtime
    from plugins.mxai.cfg.manager import ConfigManager

    data_dir = tmp_path / "hub"
    profiles = data_dir / "profiles" / "douyin"
    profiles.mkdir(parents=True)
    (profiles / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (profiles / "benchmarks.yaml").write_text("accounts:\n  - '@a'\n", encoding="utf-8")
    (profiles / "workbench.yaml").write_text(
        "scheduler:\n  benchmark_monitor:\n    enabled: true\n    interval_minutes: 45\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: data_dir / "profiles" / name,
    )
    QueueManager.reset()
    ConfigManager.reset()
    ensure_config_runtime()
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)

    r1 = run_benchmark_round("douyin", source="cron")
    assert r1["ok"] is True
    assert len(r1.get("enqueued") or []) >= 1

    before = len(q.list_tasks()["items"])
    r2 = run_benchmark_round("douyin", source="cron")
    assert r2["ok"] is True
    assert len(r2.get("enqueued") or []) == 0
    assert len(q.list_tasks()["items"]) == before
