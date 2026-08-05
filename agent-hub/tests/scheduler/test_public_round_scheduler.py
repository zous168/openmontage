"""CR-143 方案 B：public_round_scheduler 单测."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.scheduler.public_round_scheduler import (
    maybe_schedule_comment_collect,
    maybe_schedule_comment_reply,
)
from plugins.mxai.scheduler.state import set_last_collect_finished_at


@pytest.fixture
def sched_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    p = data_dir / "profiles" / "douyin"
    p.mkdir(parents=True)
    (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (p / "risk.yaml").write_text("enabled: true\ndaily_collect_limit: 0\ndaily_reply_limit: 0\n", encoding="utf-8")
    (p / "faq.yaml").write_text("entries: []\n", encoding="utf-8")
    (p / "sensitive_words.yaml").write_text("words: []\n", encoding="utf-8")
    (p / "comment_keywords.yaml").write_text(
        "search_keywords:\n  - AI\nmatch_keywords:\n  - 多少钱\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.state.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: data_dir / "profiles" / name,
    )
    QueueManager.reset()
    ConfigManager.reset()
    ensure_config_runtime()
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "comment_collect": {
                "enabled": True,
                "daily_start_at": "00:00",
                "interval_minutes": 60,
                "max_videos_per_run": 5,
                "max_customers_per_run": 8,
            },
            "comment_reply": {
                "enabled": True,
                "author_name": "测试号",
                "daily_start_at": "00:00",
                "interval_minutes": 60,
            },
        },
    )
    q = QueueManager.get()
    q.arm_work()
    q.set_agent_enabled("douyin", True)
    from plugins.mxai.scheduler import schedule_skip

    schedule_skip._last_logged.clear()
    state_path = data_dir / "scheduler_state.json"
    if state_path.is_file():
        state_path.unlink()
    return data_dir


def test_schedule_collect_includes_per_run_limits(sched_env: Path) -> None:
    out = maybe_schedule_comment_collect("douyin", source="cron", benchmark_ids=["@A"])
    assert out.get("task_id")
    task = QueueManager.get().get_task(out["task_id"])
    assert task.payload["max_videos_per_run"] == 5
    assert task.payload["max_customers_per_run"] == 8


def test_schedule_collect_skips_outside_run_window(sched_env: Path, monkeypatch) -> None:
    import core.timeutil as tu
    from datetime import datetime, timedelta, timezone

    _BJ = timezone(timedelta(hours=8))
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "comment_collect": {
                "enabled": True,
                "run_window": {"start": "09:00", "end": "18:00"},
                "interval_minutes": 60,
            },
        },
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 7, 20, 0, tzinfo=_BJ))
    out = maybe_schedule_comment_collect("douyin", source="cron", benchmark_ids=["@A"])
    assert out.get("skipped") in {"outside_run_window", "before_daily_start"}


def test_schedule_collect_skips_interval(sched_env: Path) -> None:
    set_last_collect_finished_at("douyin", time.time())
    out = maybe_schedule_comment_collect("douyin", source="cron", benchmark_ids=["@A"])
    assert out.get("skipped") == "interval_not_elapsed"


def test_schedule_skip_writes_worklog(sched_env: Path) -> None:
    from plugins.mxai.worklog.service import list_worklogs

    set_last_collect_finished_at("douyin", time.time())
    maybe_schedule_comment_collect("douyin", source="cron", benchmark_ids=["@A"])
    rows = list_worklogs(profile_id="douyin", data_dir=sched_env)
    assert any(r.get("exec_status") == "调度跳过" and r.get("fail_reason") == "interval_not_elapsed" for r in rows)


def test_manual_collect_bypasses_interval(sched_env: Path) -> None:
    set_last_collect_finished_at("douyin", time.time())
    out = maybe_schedule_comment_collect("douyin", source="manual", search_keywords=["AI"])
    assert out.get("task_id")


def test_schedule_reply_allows_empty_author(sched_env: Path) -> None:
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {"comment_reply": {"enabled": True, "author_name": ""}},
    )
    ConfigManager.get().patch(
        "agent.douyin.comment_keywords",
        {"search_keywords": ["AI"], "match_keywords": []},
    )
    out = maybe_schedule_comment_reply("douyin", source="cron")
    assert out.get("task_id")
    task = QueueManager.get().get_task(out["task_id"])
    assert task is not None
    assert "author_name" not in (task.payload or {})
