"""CR-97 module_status + bootstrap_public."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.api.run import run_agents_status
from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.lead_service import insert_comment_lead
from plugins.mxai.orchestrator.bootstrap_public import (
    bootstrap_comment_reply,
    bootstrap_dm_touch,
    bootstrap_first_comment,
    leads_eligible_for_dm,
)
from plugins.mxai.orchestrator.module_status import module_status_for_agent
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.orchestrator.run_orchestrator import RunOrchestrator


@pytest.fixture
def cr97_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    profiles = data_dir / "profiles" / "douyin"
    profiles.mkdir(parents=True)
    (profiles / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (profiles / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    (profiles / "comment_keywords.yaml").write_text(
        "search_keywords:\n  - marketing\nmatch_keywords:\n  - price\n",
        encoding="utf-8",
    )
    (profiles / "benchmarks.yaml").write_text("accounts:\n  - '@x'\n", encoding="utf-8")
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: data_dir / "profiles" / name,
    )
    QueueManager.reset()
    ConfigManager.reset()
    ensure_config_runtime()
    from plugins.mxai.worklog.storage.worklog_repo import init_worklog_schema

    init_worklog_schema(mxai_db_path("hub.db", data_dir))  # LT-033：work_logs 并入 hub.db
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "comment_collect": {
                "enabled": True,
                "daily_start_at": "09:00",
                "run_window": {"start": "00:00", "end": "23:59"},
            },
            "comment_reply": {
                "enabled": True,
                "auto_after_intent": True,
                "author_name": "测试号",
                "daily_start_at": "09:00",
                "run_window": {"start": "00:00", "end": "23:59"},
            },
            "scheduler": {
                "first_comment": {
                    "enabled": True,
                    "mode": "on_new_video",
                    "daily_at": "09:00",
                    "run_window": {"start": "00:00", "end": "23:59"},
                },
                "benchmark_monitor": {"enabled": True, "interval_minutes": 45},
            },
            "dm": {
                "auto_enabled": True,
                "message": "您好，欢迎咨询",
                "run_window": {"start": "00:00", "end": "23:59"},
            },
        },
    )
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    insert_comment_lead(
        profile_id="douyin", nickname="user_a", douyin_id="dy_a",
        comment="多少钱", intent="高", data_dir=data_dir,
    )
    insert_comment_lead(
        profile_id="douyin", nickname="user_b", douyin_id="dy_b",
        comment="看看", intent="低", data_dir=data_dir,
    )
    return data_dir


def test_module_status_public_four_blocks(cr97_env: Path) -> None:
    mods = module_status_for_agent(
        "douyin",
        work_armed=True,
        scheduler_active=True,
        agent_enabled=True,
    )
    # CR-169：抖音多一个「客户视频评论」模块（小红书/视频号仍四块）
    assert len(mods) == 5
    ids = [m["module_id"] for m in mods]
    assert ids == [
        "comment_collect",
        "comment_reply",
        "first_comment",
        "dm_touch",
        "video_comment",
    ]
    xhs_ids = [
        m["module_id"]
        for m in module_status_for_agent(
            "xiaohongshu", work_armed=True, scheduler_active=True, agent_enabled=True
        )
    ]
    assert xhs_ids == ["comment_collect", "comment_reply", "first_comment", "dm_touch"]
    collect = next(m for m in mods if m["module_id"] == "comment_collect")
    assert collect["init_status"] == "ready"
    assert collect["can_auto_run"] is True


def test_module_status_missing_keywords(cr97_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    p = cr97_env / "profiles" / "xiaohongshu"
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.yaml").write_text("model: t\n", encoding="utf-8")
    (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    (p / "comment_keywords.yaml").write_text("search_keywords: []\nmatch_keywords: []\n", encoding="utf-8")
    mods = module_status_for_agent(
        "xiaohongshu",
        work_armed=False,
        scheduler_active=False,
        agent_enabled=True,
    )
    collect = next(m for m in mods if m["module_id"] == "comment_collect")
    assert collect["init_status"] == "missing_config"
    assert "搜索词" in (collect["missing_hint"] or "")


def test_module_status_disabled_still_shows_missing_config(cr97_env: Path) -> None:
    """未开启但缺配置的模块仍应黄标，便于引导补全后再启用。"""
    ConfigManager.get().patch("agent.douyin.benchmarks", {"accounts": []})
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "first_comment": {"schedule_enabled": False},
            "scheduler": {"first_comment": {"enabled": False, "daily_at": "", "run_window": {"start": "", "end": ""}}},
            "dm": {"auto_enabled": False, "message": "", "run_window": {"start": "", "end": ""}},
        },
    )
    mods = module_status_for_agent(
        "douyin",
        work_armed=False,
        scheduler_active=False,
        agent_enabled=True,
    )
    first = next(m for m in mods if m["module_id"] == "first_comment")
    dm = next(m for m in mods if m["module_id"] == "dm_touch")
    assert first["enabled"] is False
    assert first["init_status"] == "missing_config"
    assert dm["enabled"] is False
    assert dm["init_status"] == "missing_config"
    assert dm["missing_hint"]


def test_module_status_scheduled_touch_time_hint(cr97_env: Path) -> None:
    p = cr97_env / "profiles" / "wechat"
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.yaml").write_text("model: t\n", encoding="utf-8")
    (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    ConfigManager.get().patch(
        "agent.wechat.workbench",
        {"scheduler": {"scheduled_touch": {"enabled": True, "time": "", "recipient": ""}}},
    )
    mods = module_status_for_agent(
        "wechat",
        work_armed=False,
        scheduler_active=False,
        agent_enabled=True,
    )
    touch = next(m for m in mods if m["module_id"] == "scheduled_touch")
    assert touch["init_status"] == "missing_config"
    assert touch["missing_hint"] == "请设置每日发送时间"


def test_module_status_missing_run_window(cr97_env: Path) -> None:
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "comment_collect": {
                "enabled": True,
                "daily_start_at": "",
                "run_window": {"start": "", "end": ""},
            },
        },
    )
    mods = module_status_for_agent(
        "douyin",
        work_armed=False,
        scheduler_active=False,
        agent_enabled=True,
    )
    collect = next(m for m in mods if m["module_id"] == "comment_collect")
    assert collect["init_status"] == "missing_config"
    assert "运行时段" in (collect["missing_hint"] or "")


def test_module_status_boss_missing_greet_window(cr97_env: Path) -> None:
    p = cr97_env / "profiles" / "boss"
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.yaml").write_text("model: t\n", encoding="utf-8")
    (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    ConfigManager.get().patch(
        "agent.boss.workbench",
        {"boss": {"greet": {"run_window": {"start": "", "end": ""}}, "proactive_dm": {"run_window": {"start": "09:00", "end": "18:00"}}}},
    )
    mods = module_status_for_agent(
        "boss",
        work_armed=False,
        scheduler_active=False,
        agent_enabled=True,
    )
    greet = next(m for m in mods if m["module_id"] == "greet")
    assert greet["init_status"] == "missing_config"
    assert "运行时段" in (greet["missing_hint"] or "")


def test_module_status_segmented_touch_subtasks_ready(cr97_env: Path) -> None:
    p = cr97_env / "profiles" / "qiyeweixin"
    p.mkdir(parents=True, exist_ok=True)
    (p / "config.yaml").write_text("model: t\n", encoding="utf-8")
    (p / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    ConfigManager.get().patch(
        "agent.qiyeweixin.workbench",
        {
            "scheduler": {
                "scheduled_touch": {
                    "enabled": True,
                    "mode": "segmented",
                    "interval_minutes": 30,
                    "run_window": {"start": "09:00", "end": "18:00"},
                    "segments": [],
                    "touch_subtasks": [
                        {
                            "id": "silence_5d",
                            "enabled": True,
                            "content_mode": "static",
                            "message": "您好{display_name}",
                            "threshold_sec": 432000,
                        },
                    ],
                }
            }
        },
    )
    mods = module_status_for_agent(
        "qiyeweixin",
        work_armed=False,
        scheduler_active=False,
        agent_enabled=True,
    )
    touch = next(m for m in mods if m["module_id"] == "scheduled_touch")
    assert touch["init_status"] == "ready"
    assert touch["missing_hint"] is None


def test_bootstrap_enqueues_first_comment_and_reply(cr97_env: Path) -> None:
    fc = bootstrap_first_comment("douyin")
    assert fc and len(fc) == 1 and fc[0]["task_type"] == "first_comment"
    cr = bootstrap_comment_reply("douyin")
    assert cr and cr["task_type"] == "comment_reply"
    qm = QueueManager.get()
    task = qm._tasks[cr["task_id"]]
    assert task.payload.get("search_keywords") == ["marketing"]


def test_bootstrap_dm_not_sent(cr97_env: Path) -> None:
    eligible = leads_eligible_for_dm("douyin", data_dir=cr97_env)
    assert len(eligible) == 2
    rows = bootstrap_dm_touch("douyin")
    assert len(rows) == 1
    assert rows[0]["task_type"] == "dm"
    qm = QueueManager.get()
    task = qm._tasks[rows[0]["task_id"]]
    assert task.payload["recipient"] == "dy_a"
    assert task.payload["message"] == "您好，欢迎咨询"


def test_run_agents_includes_modules(cr97_env: Path) -> None:
    body = run_agents_status()
    douyin = body["agents"]["douyin"]
    assert "modules" in douyin
    assert len(douyin["modules"]) == 5  # CR-169 抖音 +客户视频评论


def test_bootstrap_full_orchestrator(cr97_env: Path) -> None:
    result = RunOrchestrator.bootstrap(["douyin"])
    types = [e["task_type"] for e in result["profiles"]["douyin"]["enqueued"]]
    assert "comment_collect" in types
    assert "first_comment" in types
    assert "comment_reply" in types
    assert "dm" in types
