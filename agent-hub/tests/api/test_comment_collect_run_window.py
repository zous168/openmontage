"""comment_collect 运行时段门闸 — CR-133."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import core.timeutil as tu
import pytest
from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.orchestrator.models import TaskStatus
from plugins.mxai.orchestrator.queue_manager import QueueManager


@pytest.fixture
def cc_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "hub"
    p = data_dir / "profiles" / "douyin"
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    (p / "comment_keywords.yaml").write_text("search_keywords:\n  - 智能客服\n", encoding="utf-8")
    (p / "workbench.yaml").write_text(
        "comment_collect:\n  enabled: true\n  run_window:\n    start: '12:00'\n    end: '23:00'\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.state.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    monkeypatch.setattr("hermes_cli.profiles.get_profile_dir", lambda n: data_dir / "profiles" / n)
    QueueManager.reset()
    ConfigManager.reset()
    ensure_config_runtime()
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    monkeypatch.setattr(
        tu,
        "beijing_now",
        lambda: datetime(2026, 7, 7, 11, 58, tzinfo=timezone(timedelta(hours=8))),
    )
    return data_dir


def test_manual_comment_collect_allowed_outside_window(mxai_client, cc_env) -> None:
    r = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"search_keywords": ["智能客服"]},
    )
    assert r.status_code == 200
    assert r.json().get("task_id")


def test_bootstrap_enqueue_skipped_before_daily_start(cc_env) -> None:
    from plugins.mxai.orchestrator.run_orchestrator import RunOrchestrator

    row = RunOrchestrator._enqueue_comment_collect(
        "douyin", ["智能客服"], source="bootstrap"
    )
    assert row is not None
    assert row.get("skipped") == "before_daily_start"
    assert QueueManager.get().list_tasks(agent="douyin")["total"] == 0


def test_auto_task_drained_without_run_window_gate(cc_env, monkeypatch) -> None:
    """CR-143：队列 drain 不再用 run_window 拦 comment_collect（调度在入队口）."""
    q = QueueManager.get()
    task = q.enqueue(
        profile_id="douyin",
        name="auto collect",
        task_type="comment_collect",
        operator="Bootstrap",
        payload={"keywords": ["智能客服"], "source": "bootstrap"},
        skip_risk=True,
    )
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.queue_manager.get_rpa_worker_bridge",
        lambda: type(
            "B",
            (),
            {
                "is_connected": lambda _self: True,
                "execute_via_worker": lambda _self, _t: {"ok": True},
            },
        )(),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.client_settings.read_client_settings",
        lambda: {"rpa_integrate_mode": "ws"},
    )
    q._drain_rpa()
    import time

    time.sleep(0.05)
    refreshed = q.get_task(task.task_id)
    assert refreshed is not None
    assert refreshed.status != TaskStatus.QUEUED
