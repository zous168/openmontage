"""队列 / 开工状态不持久化 — Hub 进程内默认未开工."""

from __future__ import annotations

from pathlib import Path

import yaml

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_queue_starts_idle_and_ignores_disk_run_state(mxai_env: Path) -> None:
    douyin_dir = mxai_env / "profiles" / "douyin"
    (douyin_dir / "run_enabled.yaml").write_text(
        yaml.dump({"enabled": True}),
        encoding="utf-8",
    )
    (mxai_env / "queue_state.yaml").write_text(
        yaml.dump({"global_paused": False}),
        encoding="utf-8",
    )

    QueueManager.reset()
    ensure_config_runtime()
    q = QueueManager.get()
    assert q.is_agent_enabled("douyin") is False
    assert q.summary()["paused"] is True
