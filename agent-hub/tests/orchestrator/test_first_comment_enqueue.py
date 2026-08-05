"""抢首评逐账号入队单测."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.orchestrator.first_comment_enqueue import enqueue_first_comment_per_benchmark
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.rpa_worker import automan_bridge as ab


@pytest.fixture
def fc_queue_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    p = data_dir / "profiles" / "douyin"
    p.mkdir(parents=True)
    (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
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


def test_enqueue_one_task_per_benchmark(fc_queue_env: Path) -> None:
    rows = enqueue_first_comment_per_benchmark(
        "douyin",
        ["@a", "@b", "@c"],
        source="test",
        operator="Test",
    )
    assert len(rows) == 3
    qm = QueueManager.get()
    for row in rows:
        task = qm._tasks[row["task_id"]]
        assert task.task_type == "first_comment"
        assert len(task.payload["benchmarks"]) == 1


def test_bridge_first_comment_key_words_single_benchmark() -> None:
    task = SimpleNamespace(
        task_id="t-fc",
        task_type="first_comment",
        profile_id="douyin",
        operator="Test",
        payload={"benchmarks": ["@demo"]},
        name="t",
        priority=3,
    )
    frame = ab.to_execute(task)
    assert frame["slug"] == "douyin_first_comment"
    assert frame["inputs"] == {"key_words": "@demo"}
