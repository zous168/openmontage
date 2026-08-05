"""LT-018.02.01 RunOrchestrator.bootstrap."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.orchestrator.run_orchestrator import RunOrchestrator


@pytest.fixture
def orch_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    profiles = data_dir / "profiles"
    for name in ("douyin", "wechat"):
        p = profiles / name
        p.mkdir(parents=True)
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
        (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    (profiles / "douyin" / "comment_keywords.yaml").write_text(
        "keywords:\n  - 营销\n", encoding="utf-8"
    )
    (profiles / "douyin" / "benchmarks.yaml").write_text("accounts:\n  - '@x'\n", encoding="utf-8")
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
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
        lambda name: profiles / name,
    )
    QueueManager.reset()
    ConfigManager.reset()
    ensure_config_runtime()
    from plugins.mxai.worklog.storage.worklog_repo import init_worklog_schema

    init_worklog_schema(mxai_db_path("hub.db", data_dir))  # LT-033：work_logs 并入 hub.db
    from plugins.mxai.crm.storage.hub_repo import init_hub_schema

    init_hub_schema(mxai_db_path("hub.db", data_dir))
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    q.set_agent_enabled("wechat", False)
    return data_dir


def test_bootstrap_keywords_enqueue(orch_env: Path) -> None:
    result = RunOrchestrator.bootstrap(["douyin"])
    prof = result["profiles"]["douyin"]
    types = [e["task_type"] for e in prof["enqueued"]]
    assert "comment_collect" in types
    assert result["total_enqueued"] >= 1


def test_bootstrap_comment_collect_skipped_before_daily_start(
    orch_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timedelta, timezone

    import core.timeutil as tu

    from plugins.mxai.cfg.paths import agent_cfg_path

    # CR-145：workbench 收口 cfg/{module}/。
    wb_path = agent_cfg_path("douyin", "workbench.yaml")
    wb_path.parent.mkdir(parents=True, exist_ok=True)
    wb_path.write_text(
        "comment_collect:\n  enabled: true\n  run_window:\n    start: '12:00'\n    end: '23:00'\n",
        encoding="utf-8",
    )
    ConfigManager.reset()
    ensure_config_runtime()
    QueueManager.get().arm_work()
    QueueManager.get().set_agent_enabled("douyin", True)
    monkeypatch.setattr(
        tu,
        "beijing_now",
        lambda: datetime(2026, 7, 7, 11, 58, tzinfo=timezone(timedelta(hours=8))),
    )
    result = RunOrchestrator.bootstrap(["douyin"])
    prof = result["profiles"]["douyin"]
    types = [e["task_type"] for e in prof["enqueued"]]
    assert "comment_collect" not in types
    cc = prof.get("comment_collect") or {}
    assert cc.get("skipped") == "before_daily_start"


def test_bootstrap_no_new_video_only_first_round(orch_env: Path) -> None:
    first = RunOrchestrator.bootstrap(["douyin"])
    assert len(first["profiles"]["douyin"].get("benchmark", {}).get("enqueued") or []) >= 1
    second = RunOrchestrator.bootstrap(["douyin"])
    bm = second["profiles"]["douyin"].get("benchmark", {})
    assert len(bm.get("enqueued") or []) == 0


def test_run_disabled_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_dir = tmp_path / "hub"
    p = data_dir / "profiles" / "douyin"
    p.mkdir(parents=True)
    (p / "config.yaml").write_text("model: t\n", encoding="utf-8")
    (p / "run_enabled.yaml").write_text("enabled: false\n", encoding="utf-8")
    (p / "comment_keywords.yaml").write_text("keywords:\n  - k\n", encoding="utf-8")
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr("hermes_cli.profiles.get_profile_dir", lambda n: data_dir / "profiles" / n)
    QueueManager.reset()
    ConfigManager.reset()
    ensure_config_runtime()
    QueueManager.get().set_agent_enabled("douyin", True)
    result = RunOrchestrator.bootstrap(["douyin"])
    assert result["profiles"]["douyin"]["skipped"] == "run_disabled"
