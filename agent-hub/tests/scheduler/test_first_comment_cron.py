"""自动首评：interval 巡检（新视频入队）；不再挂 T2 链式 / daily_cron."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.scheduler.benchmark_monitor import (
    run_benchmark_round,
    run_first_comment_daily,
)


@pytest.fixture
def fc_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    p = data_dir / "profiles" / "douyin"
    p.mkdir(parents=True)
    (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    (p / "benchmarks.yaml").write_text("accounts:\n  - '@b'\n", encoding="utf-8")
    (p / "comment_keywords.yaml").write_text(
        "search_keywords:\n  - test\nmatch_keywords:\n  - buy\n",
        encoding="utf-8",
    )
    (p / "workbench.yaml").write_text(
        "first_scripts:\n  - hi\nscheduler:\n  benchmark_monitor:\n    enabled: true\n"
        "    interval_minutes: 45\n  first_comment:\n    enabled: true\n"
        "    interval_minutes: 30\n    run_window:\n      start: '00:00'\n      end: '23:59'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
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
    from plugins.mxai.scheduler.state import _save_state

    _save_state({"agents": {}}, data_dir=data_dir)
    monkeypatch.setattr(
        "plugins.mxai.scheduler.benchmark_monitor.get_last_monitored_video",
        lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.benchmark_monitor.get_last_first_comment_video",
        lambda *_a, **_k: None,
    )
    return data_dir


def test_benchmark_round_no_longer_chains_first_comment(fc_env: Path) -> None:
    result = run_benchmark_round("douyin", source="cron", operator="Cron")
    types = [e["task_type"] for e in result.get("enqueued") or []]
    assert "first_comment" not in types


def test_interval_patrol_enqueues_new_videos(fc_env: Path) -> None:
    from plugins.mxai.cfg.paths import agent_cfg_path

    wb_path = agent_cfg_path("douyin", "workbench.yaml")
    wb_path.parent.mkdir(parents=True, exist_ok=True)
    wb_path.write_text(
        "first_scripts:\n  - hi\nscheduler:\n  first_comment:\n    enabled: true\n"
        "    interval_minutes: 30\n    run_window:\n      start: '00:00'\n      end: '23:59'\n",
        encoding="utf-8",
    )
    bm_path = agent_cfg_path("douyin", "benchmarks.yaml")
    bm_path.parent.mkdir(parents=True, exist_ok=True)
    bm_path.write_text(
        "accounts:\n  - '@b1'\n  - '@b2'\n",
        encoding="utf-8",
    )
    ConfigManager.reset()
    ensure_config_runtime()
    result = run_first_comment_daily("douyin", source="cron", operator="Cron")
    assert result.get("task_ids") and len(result["task_ids"]) == 2
