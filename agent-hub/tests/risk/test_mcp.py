"""LT-004.06.01：风控 MCP 工具面 + enqueue/execute 双检."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.risk.engine import check_enqueue, check_execute
from plugins.mxai.risk.mcp_tools import call_tool, list_tools
from plugins.mxai.worklog.service import append_worklog


@pytest.fixture(autouse=True)
def _reset_cfg_manager() -> None:
    from plugins.mxai.cfg.manager import ConfigManager

    ConfigManager.reset()
    yield
    ConfigManager.reset()


@pytest.fixture
def risk_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    profiles = data_dir / "profiles"
    profiles.mkdir()
    p = profiles / "douyin"
    p.mkdir()
    (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (p / "faq.yaml").write_text("entries: []\n", encoding="utf-8")
    (p / "sensitive_words.yaml").write_text("words: []\n", encoding="utf-8")
    QueueManager.reset()
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profiles / name,
    )
    from plugins.mxai.cfg.domains import ensure_config_runtime
    from plugins.mxai.cfg.manager import ConfigManager

    ensure_runtime_bootstrap(data_dir)
    ensure_config_runtime()
    (p / "risk.yaml").write_text("daily_dm_limit: 1\nenabled: true\n", encoding="utf-8")
    mgr = ConfigManager.get()
    mgr._snapshots.pop("agent.douyin.risk", None)
    mgr.patch("agent.douyin.risk", {"daily_dm_limit": 1, "enabled": True})
    return data_dir


def test_mcp_tool_catalog() -> None:
    names = {t["name"] for t in list_tools()}
    assert "mxai_risk_check" in names
    assert "mxai_risk_get_limits" in names


def test_mcp_get_limits(risk_env: Path) -> None:
    out = call_tool("mxai_risk_get_limits", {"profile_id": "douyin"})
    assert out["limits"]["daily_dm_limit"] == 1


def test_enqueue_and_execute_dual_check(risk_env: Path) -> None:
    append_worklog(
        profile_id="douyin",
        op_type="dm",
        exec_status="成功",
        data_dir=risk_env,
    )
    enq = check_enqueue("douyin", "dm", data_dir=risk_env)
    exe = check_execute("douyin", "dm", data_dir=risk_env)
    assert enq.allowed is False
    assert exe.allowed is False


def test_mcp_check_execute_phase(risk_env: Path) -> None:
    out = call_tool(
        "mxai_risk_check",
        {"profile_id": "douyin", "task_type": "dm", "phase": "execute"},
    )
    assert out["allowed"] is True


def test_execute_blocked_at_enqueue(risk_env: Path) -> None:
    append_worklog(
        profile_id="douyin",
        op_type="inbound_reply",
        exec_status="成功",
        data_dir=risk_env,
    )
    q = QueueManager.get()
    with pytest.raises(ValueError, match="daily_dm_limit"):
        q.enqueue(
            profile_id="douyin",
            name="超限私信",
            task_type="dm",
            payload={"recipient": "u1", "message": "hi"},
            bypass_work_armed=True,
        )
