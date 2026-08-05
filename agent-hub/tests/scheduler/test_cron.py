"""LT-004.08.01 + LT-018：Cron 对标监控 + 最小报表."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.scheduler.benchmark_monitor import run_benchmark_round


@pytest.fixture
def cron_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    profiles = data_dir / "profiles"
    profiles.mkdir()
    for name in ("main", "douyin"):
        p = profiles / name
        p.mkdir()
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
        (p / "risk.yaml").write_text("daily_dm_limit: 9999\n", encoding="utf-8")
        (p / "faq.yaml").write_text("entries: []\n", encoding="utf-8")
        (p / "sensitive_words.yaml").write_text("words: []\n", encoding="utf-8")
    douyin = profiles / "douyin"
    (douyin / "benchmarks.yaml").write_text("accounts:\n  - '@cron_bench'\n", encoding="utf-8")
    (douyin / "workbench.yaml").write_text(
        "scheduler:\n  benchmark_monitor:\n    enabled: true\n    interval_minutes: 45\n",
        encoding="utf-8",
    )
    QueueManager.reset()
    ConfigManager.reset()
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profiles / name,
    )
    ensure_runtime_bootstrap(data_dir)
    ensure_config_runtime()
    from plugins.mxai.cfg.run_enabled import set_run_enabled

    # 写 cfg 分区 run_enabled（非 profiles/）；跳过 sync 副作用用 patch
    monkeypatch.setattr(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        lambda *_a, **_k: [],
    )
    set_run_enabled("douyin", True)
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    return data_dir


def test_cron_douyin_monitor_enqueues(cron_env: Path) -> None:
    QueueManager.get().set_agent_enabled("douyin", True)
    result = run_benchmark_round("douyin", source="cron", operator="Cron")
    assert result["ok"] is True
    assert result.get("enqueued")
    # 安全缺省可能同时入队 first_comment；本测断言采集任务一定存在
    collect = next(e for e in result["enqueued"] if e.get("task_type") == "comment_collect")
    task = QueueManager.get().get_task(collect["task_id"])
    assert task is not None
    assert task.task_type == "comment_collect"


def test_cron_minimal_report(cron_env: Path) -> None:
    from plugins.mxai.scheduler import maintenance

    result = maintenance.run_minimal_report()
    assert result["ok"] is True
    assert "summary" in result
    assert "reports" in result
    assert "cleanup" in result


def test_maintenance_run_returns_result_no_self_record(cron_env: Path) -> None:
    """维护体只返回结果 dict（脚本打印 → Hermes 存 output）；执行记录由 Hermes 原生记，不自写 scheduler_state."""
    from plugins.mxai.scheduler import maintenance

    result = maintenance.run_minimal_report()
    assert result["ok"] is True
    assert "summary" in result and "reports" in result and "cleanup" in result and "retention" in result
