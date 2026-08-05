"""CR-151 延后模块：dm / first_comment / scheduled_touch run_window."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import core.timeutil as tu
import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.run_window import within_first_comment_run_window, within_touch_run_window
from plugins.mxai.crm.lead_service import insert_comment_lead
from plugins.mxai.orchestrator.bootstrap_public import bootstrap_dm_touch, bootstrap_first_comment
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.scheduler.benchmark_monitor import run_first_comment_daily, run_scheduled_touch_enqueue
from plugins.mxai.scheduler.cron_schedule_expr import first_comment_schedule, scheduled_touch_schedule

_BJ = timezone(timedelta(hours=8))


@pytest.fixture
def rw_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    for pid in ("douyin", "wechat"):
        p = data_dir / "profiles" / pid
        p.mkdir(parents=True)
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
        (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: data_dir)
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
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    q.set_agent_enabled("wechat", True)
    return data_dir


def test_bootstrap_dm_skips_outside_window(rw_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "dm": {
                "auto_enabled": True,
                "message": "hi",
                "run_window": {"start": "09:00", "end": "18:00"},
            }
        },
    )
    insert_comment_lead(
        profile_id="douyin",
        nickname="u",
        douyin_id="dy_1",
        comment="c",
        intent="高",
        data_dir=rw_env,
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 7, 20, 0, tzinfo=_BJ))
    assert bootstrap_dm_touch("douyin") == []


def test_bootstrap_dm_manual_bypasses_window(rw_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "dm": {
                "auto_enabled": True,
                "message": "hi",
                "run_window": {"start": "09:00", "end": "18:00"},
            }
        },
    )
    insert_comment_lead(
        profile_id="douyin",
        nickname="u",
        douyin_id="dy_2",
        comment="c",
        intent="高",
        data_dir=rw_env,
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 7, 20, 0, tzinfo=_BJ))
    rows = bootstrap_dm_touch("douyin", source="manual")
    assert len(rows) == 1


def test_first_comment_daily_skips_outside_window(rw_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from plugins.mxai.cfg.paths import agent_cfg_path

    wb_path = agent_cfg_path("douyin", "workbench.yaml")
    wb_path.parent.mkdir(parents=True, exist_ok=True)
    wb_path.write_text(
        "first_scripts:\n  - hi\nscheduler:\n  first_comment:\n    enabled: true\n"
        "    interval_minutes: 30\n    run_window:\n      start: '09:00'\n      end: '18:00'\n",
        encoding="utf-8",
    )
    bm_path = agent_cfg_path("douyin", "benchmarks.yaml")
    bm_path.write_text("accounts:\n  - '@b'\n", encoding="utf-8")
    ConfigManager.reset()
    ensure_config_runtime()
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 7, 20, 0, tzinfo=_BJ))
    result = run_first_comment_daily("douyin", source="cron", operator="Cron")
    assert result.get("skipped") == "outside_run_window"


def test_scheduled_touch_skips_outside_window(rw_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ConfigManager.get().patch(
        "agent.wechat.workbench",
        {
            "scheduler": {
                "scheduled_touch": {
                    "enabled": True,
                    "mode": "segmented",
                    "interval_minutes": 30,
                    "run_window": {"start": "09:00", "end": "18:00"},
                    "segments": [{"id": "s1", "enabled": True, "label": "A", "message": "hi"}],
                }
            }
        },
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 7, 20, 0, tzinfo=_BJ))
    result = run_scheduled_touch_enqueue("wechat", source="cron", operator="Cron")
    assert result.get("skipped") == "outside_run_window"


def test_scheduled_touch_run_now_bypasses_window(rw_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ConfigManager.get().patch(
        "agent.wechat.workbench",
        {
            "scheduler": {
                "scheduled_touch": {
                    "enabled": True,
                    "mode": "segmented",
                    "interval_minutes": 30,
                    "run_window": {"start": "09:00", "end": "18:00"},
                    "segments": [{"id": "s1", "enabled": True, "label": "A", "message": "hi"}],
                }
            }
        },
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 7, 20, 0, tzinfo=_BJ))
    result = run_scheduled_touch_enqueue("wechat", source="run_now", operator="Manual", force=True)
    assert result.get("skipped") != "outside_run_window"


def test_scheduled_touch_segmented_cron_with_window() -> None:
    wb = {
        "scheduler": {
            "scheduled_touch": {
                "mode": "segmented",
                "interval_minutes": 30,
                "run_window": {"start": "09:00", "end": "21:00"},
            }
        }
    }
    assert scheduled_touch_schedule(wb) == "*/30 9-21 * * *"


def test_first_comment_schedule_from_interval_window() -> None:
    wb = {
        "scheduler": {
            "first_comment": {
                "interval_minutes": 30,
                "run_window": {"start": "09:00", "end": "18:00"},
            }
        }
    }
    assert first_comment_schedule(wb) == "*/30 9-18 * * *"


def test_within_first_comment_run_window() -> None:
    wb = {"scheduler": {"first_comment": {"run_window": {"start": "09:00", "end": "18:00"}}}}
    ok, start, end = within_first_comment_run_window(wb, now_hm="10:00")
    assert ok is True and start == "09:00" and end == "18:00"
    ok2, _, _ = within_first_comment_run_window(wb, now_hm="20:00")
    assert ok2 is False


def test_within_touch_run_window() -> None:
    wb = {"scheduler": {"scheduled_touch": {"run_window": {"start": "08:00", "end": "22:00"}}}}
    ok, _, _ = within_touch_run_window(wb, now_hm="12:00")
    assert ok is True
    ok2, _, _ = within_touch_run_window(wb, now_hm="23:00")
    assert ok2 is False
