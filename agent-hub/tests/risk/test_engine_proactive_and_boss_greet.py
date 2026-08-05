"""日上限口径：主动触达 / Boss 打招呼人数（方案 B）."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.crm.boss_greet_leads import register_greet_lead
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.risk.engine import check_enqueue
from plugins.mxai.worklog.service import append_worklog


@pytest.fixture(autouse=True)
def _reset_cfg_manager() -> None:
    from plugins.mxai.cfg.manager import ConfigManager

    ConfigManager.reset()
    yield
    ConfigManager.reset()


def _prep_channel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    channel: str,
    risk: dict,
) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    profiles = data_dir / "profiles"
    profiles.mkdir(exist_ok=True)
    p = profiles / channel
    p.mkdir(exist_ok=True)
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
    from plugins.mxai.cfg.paths import agent_cfg_path
    from plugins.mxai.cfg.store import atomic_write_yaml

    ensure_runtime_bootstrap(data_dir)
    ensure_config_runtime()
    atomic_write_yaml(agent_cfg_path(channel, "risk.yaml"), {"enabled": True, **risk})
    ConfigManager.get().reload_domain(f"agent.{channel}.risk")
    ConfigManager.get().patch(f"agent.{channel}.risk", {"enabled": True, **risk})
    return data_dir


def test_proactive_dm_includes_follow_up_excludes_inbound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _prep_channel(
        tmp_path, monkeypatch, "wechat", {"daily_dm_limit": 1}
    )
    append_worklog(
        profile_id="wechat",
        op_type="follow_up",
        exec_status="成功",
        data_dir=data_dir,
    )
    assert check_enqueue("wechat", "follow_up", data_dir=data_dir).allowed is False
    assert check_enqueue("wechat", "dm", data_dir=data_dir).allowed is False
    # 自动应答不计入主动触达日上限
    assert check_enqueue("wechat", "inbound_reply", data_dir=data_dir).allowed is True


def test_inbound_reply_worklogs_do_not_consume_proactive_quota(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _prep_channel(
        tmp_path, monkeypatch, "wechat", {"daily_dm_limit": 1}
    )
    for _ in range(5):
        append_worklog(
            profile_id="wechat",
            op_type="inbound_reply",
            exec_status="成功",
            data_dir=data_dir,
        )
    assert check_enqueue("wechat", "dm", data_dir=data_dir).allowed is True


def test_boss_greet_limit_by_registered_people(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = _prep_channel(
        tmp_path, monkeypatch, "boss", {"daily_dm_limit": 2}
    )
    register_greet_lead(
        "boss", name="甲", reason="匹配", position="岗A", data_dir=data_dir
    )
    register_greet_lead(
        "boss", name="乙", reason="匹配", position="岗A", data_dir=data_dir
    )
    # 多跑 greet 工作流不计入；按登记人数拦
    for _ in range(5):
        append_worklog(
            profile_id="boss",
            op_type="greet",
            exec_status="成功",
            data_dir=data_dir,
        )
    blocked = check_enqueue("boss", "greet", data_dir=data_dir)
    assert blocked.allowed is False
    assert "daily_dm_limit" in blocked.reason
    # Boss 主动发消息不受「打招呼上限」约束
    assert check_enqueue("boss", "dm", data_dir=data_dir).allowed is True
    assert check_enqueue("boss", "follow_up", data_dir=data_dir).allowed is True


def test_boss_greet_register_api_respects_daily_limit(
    mxai_client, mxai_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.cfg.paths import agent_cfg_path
    from plugins.mxai.cfg.store import atomic_write_yaml

    del monkeypatch
    atomic_write_yaml(
        agent_cfg_path("boss", "risk.yaml"),
        {"enabled": True, "daily_dm_limit": 1},
    )
    ConfigManager.get().reload_domain("agent.boss.risk")
    ConfigManager.get().patch(
        "agent.boss.risk", {"enabled": True, "daily_dm_limit": 1}
    )
    register_greet_lead(
        "boss", name="先登记", reason="ok", position="岗", data_dir=mxai_env
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/boss/greet-register",
        json={"name": "再登记", "reason": "ok"},
    )
    assert res.status_code == 422
    assert "daily_dm_limit" in (res.json().get("detail") or "")
