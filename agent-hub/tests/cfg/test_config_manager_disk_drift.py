"""ConfigManager：磁盘被他进程改写后，read 自动 heal，避免助理改配置面板仍旧."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.paths import agent_cfg_path
from plugins.mxai.cfg.store import atomic_write_yaml, read_yaml


@pytest.fixture
def setup_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    profiles = data_dir / "profiles"
    profiles.mkdir()
    (profiles / "main").mkdir()
    (profiles / "main" / "config.yaml").write_text("model: test\n", encoding="utf-8")
    ensure_runtime_bootstrap(data_dir)
    from plugins.mxai.cfg.domains import register_config_domains

    ConfigManager.reset()
    register_config_domains()
    ConfigManager.get().hydrate_all()
    yield data_dir
    ConfigManager.reset()


def test_read_heals_when_disk_mtime_changes(setup_env: Path) -> None:
    domain = "agent.xiaohongshu.workbench"
    cm = ConfigManager.get()
    before = cm.read(domain)
    cc = dict(before.get("comment_collect") or {})
    cc["run_window"] = {"start": "09:00", "end": "19:00"}
    cc["daily_start_at"] = "09:00"
    # 模拟「他进程」直写 yaml，不经过本进程 replace
    path = agent_cfg_path("xiaohongshu", "workbench.yaml")
    disk = read_yaml(path, {})
    disk["comment_collect"] = {
        **(disk.get("comment_collect") or {}),
        "run_window": {"start": "00:00", "end": "23:59"},
        "daily_start_at": "00:00",
        "interval_minutes": 40,
    }
    atomic_write_yaml(path, disk)
    # Windows 上 mtime 粒度可能较粗，显式拨快保证漂移可检测
    now = time.time() + 2
    os.utime(path, (now, now))

    # 内存仍可能是旧窗；read 应按 mtime heal
    healed = cm.read(domain)
    assert healed["comment_collect"]["run_window"] == {"start": "00:00", "end": "23:59"}
    assert healed["comment_collect"]["daily_start_at"] == "00:00"
