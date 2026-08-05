"""LT-018.03 Cron T2 对标监控（CR-132：业务函数直调，无 CronScheduler）."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.run_enabled import set_run_enabled
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.scheduler.benchmark_monitor import run_benchmark_round


@pytest.fixture
def bm_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    p = data_dir / "profiles" / "douyin"
    p.mkdir(parents=True)
    (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    (p / "benchmarks.yaml").write_text("accounts:\n  - '@对标A'\n", encoding="utf-8")
    (p / "workbench.yaml").write_text(
        "scheduler:\n  benchmark_monitor:\n    enabled: true\n    interval_minutes: 45\n",
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
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    return data_dir


def test_run_reads_benchmarks(bm_env: Path) -> None:
    result = run_benchmark_round("douyin", source="cron", operator="Cron")
    assert result["ok"] is True
    assert result.get("enqueued")


def test_run_disabled_skips(bm_env: Path) -> None:
    """未开工/未启用由 run_enabled + 队列 409 兜底（取代旧 scheduler_active guard）."""
    set_run_enabled("douyin", False)
    result = run_benchmark_round("douyin", source="cron", operator="Cron")
    assert result.get("skipped") == "run_disabled"


def test_benchmark_job_ensured_in_hermes(bm_env: Path) -> None:
    """CR-132 / LT-038.03：对标 job 首次由 Hermes sync 建一次（create-if-absent）。"""
    from plugins.mxai.scheduler.cron import benchmark_job_id, sync_benchmark_job

    row = sync_benchmark_job("douyin")
    assert row is not None
    assert row["ensured"] is True
    assert row["job_id"] == benchmark_job_id("douyin") == "mxai-douyin-benchmark_monitor"


def test_comment_collect_disabled_skips(bm_env: Path) -> None:
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {"comment_collect": {"enabled": False}},
    )
    result = run_benchmark_round("douyin", source="cron", operator="Cron")
    assert result.get("skipped") == "comment_collect_disabled"
    assert not result.get("enqueued")
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {"comment_collect": {"enabled": True}},
    )


def test_derives_comment_collect(bm_env: Path) -> None:
    result = run_benchmark_round("douyin", source="cron", operator="Cron")
    task_id = result["enqueued"][0]["task_id"]
    task = QueueManager.get().get_task(task_id)
    assert task is not None
    assert task.task_type == "comment_collect"
    assert task.payload.get("source") == "cron"
    assert task.payload.get("benchmark_ids")
    assert task.payload.get("match_keywords") is not None

    second = run_benchmark_round("douyin", source="cron", operator="Cron")
    assert len(second.get("enqueued") or []) == 0


def test_benchmark_payload_has_match_keywords(bm_env: Path) -> None:
    from plugins.mxai.cfg.paths import agent_cfg_path

    # CR-145：comment_keywords 收口 cfg/{module}/；迁移已 run-once，直写新位置。
    ck_path = agent_cfg_path("douyin", "comment_keywords.yaml")
    ck_path.parent.mkdir(parents=True, exist_ok=True)
    ck_path.write_text(
        "match_keywords:\n  - 多少钱\n  - 怎么联系\n",
        encoding="utf-8",
    )
    ConfigManager.reset()
    ensure_config_runtime()
    QueueManager.get().arm_work()
    result = run_benchmark_round("douyin", source="cron", operator="Cron")
    task = QueueManager.get().get_task(result["enqueued"][0]["task_id"])
    assert task.payload["match_keywords"] == ["多少钱", "怎么联系"]
    assert not task.payload.get("search_keywords")

    second = run_benchmark_round("douyin", source="cron", operator="Cron")
    assert len(second.get("enqueued") or []) == 0
