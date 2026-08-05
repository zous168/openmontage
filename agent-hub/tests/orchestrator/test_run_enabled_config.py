"""run_enabled 未开工时可写、开工后联动 runtime."""

from pathlib import Path

from plugins.mxai.cfg.run_enabled import (
    ensure_run_enabled_default,
    is_run_enabled,
    set_run_enabled,
)
from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_run_enabled_missing_file_defaults_false(mxai_env: Path) -> None:
    del mxai_env
    assert is_run_enabled("douyin") is False
    assert is_run_enabled("boss") is False


def test_ensure_run_enabled_default_keeps_true(mxai_env: Path) -> None:
    """bootstrap 不得把已开启的 run_enabled 刷回 false（FR-RUN-07）."""
    del mxai_env
    set_run_enabled("douyin", True)
    assert ensure_run_enabled_default("douyin") == "kept"
    assert is_run_enabled("douyin") is True


def test_ensure_run_enabled_default_writes_when_missing(mxai_env: Path) -> None:
    del mxai_env
    from plugins.mxai.cfg.paths import agent_cfg_path

    path = agent_cfg_path("xiaohongshu", "run_enabled.yaml")
    if path.is_file():
        path.unlink()
    assert ensure_run_enabled_default("xiaohongshu") == "written"
    assert is_run_enabled("xiaohongshu") is False
    assert ensure_run_enabled_default("xiaohongshu") == "kept"


def test_run_agent_start_while_idle_persists_yaml_only(mxai_env: Path) -> None:
    del mxai_env
    QueueManager.reset()
    q = QueueManager.get()
    assert q.is_work_armed() is False

    set_run_enabled("douyin", False)
    from plugins.mxai.api.run import run_agent

    out = run_agent("douyin", "start")
    assert out["run_enabled"] is True
    assert out["enabled"] is False
    assert is_run_enabled("douyin") is True
    assert q.is_agent_enabled("douyin") is False


def test_agents_status_includes_run_enabled(mxai_env: Path) -> None:
    del mxai_env
    QueueManager.reset()
    set_run_enabled("douyin", True)
    set_run_enabled("wechat", False)
    q = QueueManager.get()
    agents = q.agents_status()["agents"]
    assert agents["douyin"]["run_enabled"] is True
    assert agents["douyin"]["enabled"] is False
    assert agents["wechat"]["run_enabled"] is False
