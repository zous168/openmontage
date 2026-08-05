"""LT-004.05.01：RPA 操作队列为内存态，不持久化."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.storage.hub_repo import init_hub_schema
from plugins.mxai.orchestrator.models import Task, TaskStatus, new_task_id
from plugins.mxai.orchestrator.queue_manager import QueueManager


@pytest.fixture
def queue_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    profiles = data_dir / "profiles"
    profiles.mkdir()
    for name in ("main", "qiyeweixin"):
        p = profiles / name
        p.mkdir()
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
        (p / "risk.yaml").write_text("daily_dm_limit: 9999\n", encoding="utf-8")
        (p / "faq.yaml").write_text("entries: []\n", encoding="utf-8")
        (p / "sensitive_words.yaml").write_text("words: []\n", encoding="utf-8")
    init_hub_schema(mxai_db_path("hub.db", data_dir))
    ensure_runtime_bootstrap(data_dir)
    QueueManager.reset()
    return data_dir


def test_seed_in_memory_only(queue_env: Path) -> None:
    del queue_env
    q = QueueManager.get()
    task = Task(
        task_id=new_task_id(),
        name="内存任务",
        profile_id="douyin",
        task_type="comment_collect",
        status=TaskStatus.QUEUED,
    )
    assert q.seed_in_memory([task]) == 1
    assert q.get_task(task.task_id) is not None
    assert q.get_task(task.task_id).status == TaskStatus.QUEUED


def test_enqueue_rejects_non_rpa_task_type(queue_env: Path) -> None:
    del queue_env
    q = QueueManager.get()
    with pytest.raises(ValueError, match="not an RPA queue operation"):
        q.enqueue(
            profile_id="douyin",
            name="报表",
            task_type="report",
            skip_risk=True,
        )


def test_restart_clears_memory_queue(queue_env: Path) -> None:
    del queue_env
    q1 = QueueManager.get()
    task = Task(
        task_id=new_task_id(),
        name="重启前",
        profile_id="douyin",
        task_type="comment_collect",
        status=TaskStatus.DONE,
        progress=100,
    )
    q1.seed_in_memory([task])
    assert q1.get_task(task.task_id) is not None
    QueueManager.reset()
    q2 = QueueManager.get()
    assert q2.get_task(task.task_id) is None
