"""向导分步配置与渠道默认种子."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.cfg.comment_keywords import read_comment_keywords
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.run_enabled import is_run_enabled
from plugins.mxai.wizard.persist import save_enterprise
from plugins.mxai.wizard.setup_guide import get_setup_plan, run_apply_defaults


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

    register_config_domains()
    ConfigManager.reset()
    return data_dir


def test_setup_plan_starts_at_industry(setup_env: Path) -> None:
    plan = get_setup_plan(data_dir=setup_env)
    assert plan["step"] == "industry"
    assert plan["prompt"]["field"] == "industry"


def test_apply_defaults_requires_product(setup_env: Path) -> None:
    save_enterprise({"enterprise_name": "Acme", "industry": "retail"}, data_dir=setup_env)
    with pytest.raises(ValueError, match="产品"):
        run_apply_defaults(data_dir=setup_env)


def test_repair_fills_empty_dm_message(setup_env: Path) -> None:
    from plugins.mxai.wizard.channel_defaults import _repair_empty_placeholders
    from plugins.mxai.wizard.setup_guide import repair_channel_config

    repair = repair_channel_config(data_dir=setup_env)
    assert repair["ok"] is True
    assert _repair_empty_placeholders("douyin") == {}

    from plugins.mxai.cfg.store import read_yaml
    from plugins.mxai.cfg.paths import agent_cfg_read_path

    wb = read_yaml(agent_cfg_read_path("douyin", "workbench.yaml"), {})
    assert str((wb.get("dm") or {}).get("message") or "").strip()


def test_full_channel_init_modules_ready(setup_env: Path) -> None:
    from plugins.mxai.orchestrator.module_status import module_status_for_agent
    from plugins.mxai.wizard.channel_defaults import apply_full_channel_init
    from plugins.mxai.wizard.persist import save_enterprise

    save_enterprise(
        {
            "enterprise_name": "测试商户",
            "short_name": "测试号",
            "industry": "education",
            "product_desc": "少儿编程培训",
        },
        data_dir=setup_env,
    )
    ent = {"enterprise_name": "测试商户", "short_name": "测试号", "product_desc": "少儿编程培训"}
    apply_full_channel_init("education", ent, force=True)

    for pid in ("douyin", "xiaohongshu", "shipinhao", "wechat", "qiyeweixin", "boss"):
        mods = module_status_for_agent(pid, work_armed=False, scheduler_active=False, agent_enabled=False)
        missing = [m for m in mods if m.get("init_status") == "missing_config"]
        assert not missing, f"{pid} still missing: {missing}"


def test_wizard_setup_flow_api(setup_env: Path) -> None:
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    client = TestClient(app)

    plan = client.get("/api/plugins/mxai/wizard/setup-guide").json()
    assert plan["step"] == "industry"

    saved = client.put(
        "/api/plugins/mxai/wizard/setup-profile",
        json={"industry": "education", "product": {"product_desc": "少儿编程培训"}},
    ).json()
    assert saved["step"] == "apply_defaults"

    applied = client.post("/api/plugins/mxai/wizard/apply-defaults").json()
    assert applied["ok"] is True
    assert applied["industry"] == "education"
    assert not is_run_enabled("douyin")

    ConfigManager.reset()
    kw = read_comment_keywords("douyin")
    assert "课程" in kw["search_keywords"]

    wb = ConfigManager.get().read("agent.douyin.workbench")
    assert wb["comment_reply"]["enabled"] is True
    assert wb["dm"]["auto_enabled"] is True


def test_full_channel_init_schedule_times(setup_env: Path) -> None:
    from plugins.mxai.wizard.channel_defaults import apply_full_channel_init
    from plugins.mxai.wizard.persist import save_enterprise

    save_enterprise(
        {
            "enterprise_name": "测试商户",
            "short_name": "测试号",
            "industry": "catering",
            "product_desc": "餐饮加盟",
        },
        data_dir=setup_env,
    )
    ent = {"enterprise_name": "测试商户", "short_name": "测试号", "product_desc": "餐饮加盟"}
    apply_full_channel_init("catering", ent, force=True)

    from plugins.mxai.cfg.store import read_yaml
    from plugins.mxai.cfg.paths import agent_cfg_read_path

    dy = read_yaml(agent_cfg_read_path("douyin", "workbench.yaml"), {})
    assert dy["comment_reply"]["run_window"] == {"start": "09:00", "end": "18:00"}
    assert dy["comment_reply"]["daily_start_at"] == "09:00"
    assert dy["comment_collect"]["run_window"] == {"start": "09:00", "end": "19:00"}
    assert dy["dm"]["run_window"] == {"start": "09:00", "end": "21:00"}
    assert dy["scheduler"]["first_comment"]["daily_at"] == "09:00"
    assert dy["scheduler"]["first_comment"]["run_window"] == {"start": "09:00", "end": "18:00"}

    wx = read_yaml(agent_cfg_read_path("wechat", "workbench.yaml"), {})
    touch = (wx.get("scheduler") or {}).get("scheduled_touch") or {}
    assert touch.get("time") == "09:00"
    assert touch.get("run_window") == {"start": "09:00", "end": "18:00"}
    assert wx["add_friends"]["run_window"] == {"start": "09:00", "end": "18:00"}

    qy = read_yaml(agent_cfg_read_path("qiyeweixin", "workbench.yaml"), {})
    assert qy["batch_add"]["run_window"] == {"start": "09:00", "end": "18:00"}

    boss = read_yaml(agent_cfg_read_path("boss", "workbench.yaml"), {})
    assert boss["boss"]["greet"]["run_window"] == {"start": "09:00", "end": "18:00"}
    assert boss["boss"]["proactive_dm"]["run_window"] == {"start": "09:00", "end": "18:00"}


def test_repair_fills_missing_schedule_times(setup_env: Path) -> None:
    """空时段补默认；显式全天 00:00–23:59 不得被 repair 改回 09–19."""
    from plugins.mxai.cfg.store import atomic_write_yaml, read_yaml
    from plugins.mxai.cfg.paths import agent_cfg_path
    from plugins.mxai.wizard.channel_defaults import _repair_empty_placeholders
    from plugins.mxai.wizard.setup_guide import repair_channel_config

    atomic_write_yaml(
        agent_cfg_path("douyin", "workbench.yaml"),
        {
            "comment_reply": {"enabled": False, "run_window": {"start": "", "end": ""}, "daily_start_at": ""},
            "comment_collect": {"enabled": True, "run_window": {"start": "", "end": ""}},
            "dm": {"auto_enabled": False, "message": "hi", "run_window": {"start": "", "end": ""}},
            "scheduler": {"first_comment": {"enabled": False, "run_window": {"start": "", "end": ""}}},
        },
    )
    _repair_empty_placeholders("douyin")
    wb = read_yaml(agent_cfg_path("douyin", "workbench.yaml"), {})
    assert wb["comment_reply"]["run_window"]["start"] == "09:00"
    assert wb["comment_reply"]["run_window"]["end"] == "18:00"
    assert wb["comment_collect"]["run_window"]["end"] == "19:00"

    # 显式全天：不得被 repair 改回 09–19
    atomic_write_yaml(
        agent_cfg_path("xiaohongshu", "workbench.yaml"),
        {
            "comment_collect": {
                "enabled": True,
                "daily_start_at": "00:00",
                "run_window": {"start": "00:00", "end": "23:59"},
                "interval_minutes": 40,
            },
        },
    )
    _repair_empty_placeholders("xiaohongshu")
    xhs = read_yaml(agent_cfg_path("xiaohongshu", "workbench.yaml"), {})
    assert xhs["comment_collect"]["run_window"] == {"start": "00:00", "end": "23:59"}
    assert xhs["comment_collect"]["daily_start_at"] == "00:00"

    repair = repair_channel_config(data_dir=setup_env)
    assert repair["ok"] is True


def test_repair_refreshes_config_manager_snapshots(setup_env: Path) -> None:
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.cfg.module_enabled import read_module_enabled
    from plugins.mxai.wizard.setup_guide import repair_channel_config

    save_enterprise(
        {
            "enterprise_name": "测试商户",
            "short_name": "测试号",
            "industry": "catering",
            "product_desc": "餐饮加盟",
        },
        data_dir=setup_env,
    )
    ConfigManager.get().hydrate_all()
    stale = ConfigManager.get().read("agent.douyin.workbench")
    stale = dict(stale)
    stale.setdefault("comment_reply", {})["enabled"] = False
    stale.setdefault("dm", {})["auto_enabled"] = False
    with ConfigManager.get()._mutex:
        ConfigManager.get()._snapshots["agent.douyin.workbench"] = stale

    assert read_module_enabled("douyin", "comment_reply") is False
    assert read_module_enabled("douyin", "dm_touch") is False

    repair = repair_channel_config(data_dir=setup_env)
    assert repair["ok"] is True
    assert read_module_enabled("douyin", "comment_reply") is True
    assert read_module_enabled("douyin", "dm_touch") is True


def test_save_channel_benchmarks_merges_append(setup_env: Path) -> None:
    """添加对标应合并，不覆盖行业模板账号."""
    from plugins.mxai.scheduler.benchmark_monitor import _read_benchmarks
    from plugins.mxai.wizard.channel_defaults import _patch_domain
    from plugins.mxai.wizard.setup_guide import save_channel_setup

    _patch_domain(
        "douyin",
        "benchmarks",
        {"accounts": ["@餐饮创业", "@美食探店"]},
        merge_mode="replace",
    )
    ConfigManager.get().hydrate_all()

    result = save_channel_setup("douyin", benchmarks=["人民日报"], data_dir=setup_env)
    assert result["ok"] is True
    assert _read_benchmarks("douyin") == ["@餐饮创业", "@美食探店", "人民日报"]


def test_save_channel_benchmarks_remove(setup_env: Path) -> None:
    """删除对标须 benchmarks_mode=remove，且忽略 @ 前缀差异."""
    from plugins.mxai.scheduler.benchmark_monitor import _read_benchmarks
    from plugins.mxai.wizard.channel_defaults import _patch_domain
    from plugins.mxai.wizard.setup_guide import save_channel_setup

    _patch_domain(
        "douyin",
        "benchmarks",
        {"accounts": ["@餐饮创业", "@美食探店", "人民日报"]},
        merge_mode="replace",
    )
    ConfigManager.get().hydrate_all()

    result = save_channel_setup(
        "douyin",
        benchmarks=["人民日报"],
        benchmarks_mode="remove",
        data_dir=setup_env,
    )
    assert result["ok"] is True
    assert result["benchmarks"] == ["@餐饮创业", "@美食探店"]
    assert _read_benchmarks("douyin") == ["@餐饮创业", "@美食探店"]


def test_save_channel_boss_positions(setup_env: Path) -> None:
    """助理可增删 Boss 招聘岗位（greet_plans.zhiwei），get_channel 可读."""
    from plugins.mxai.wizard.channel_defaults import _patch_domain
    from plugins.mxai.wizard.setup_guide import get_channel_config, save_channel_setup

    _patch_domain(
        "boss",
        "workbench",
        {
            "boss": {
                "greet_plans": [
                    {
                        "id": "gp1",
                        "enqueue_at": "",
                        "new_number": 10,
                        "zhiwei": "后端工程师",
                        "zhize": "",
                    }
                ]
            }
        },
        merge_mode="replace",
    )
    ConfigManager.get().hydrate_all()

    with patch(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        return_value=[],
    ):
        added = save_channel_setup(
            "boss",
            positions=["前端工程师", "产品经理"],
            greet_plans_mode="add",
            data_dir=setup_env,
        )
    assert added["ok"] is True
    assert set(added["positions"]) == {"后端工程师", "前端工程师", "产品经理"}

    cfg = get_channel_config("boss")
    assert "前端工程师" in cfg["positions"]
    assert any(p.get("zhiwei") == "前端工程师" for p in cfg["greet_plans"])

    with patch(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        return_value=[],
    ):
        removed = save_channel_setup(
            "boss",
            positions=["后端工程师"],
            greet_plans_mode="remove",
            data_dir=setup_env,
        )
    assert "后端工程师" not in removed["positions"]
    assert "前端工程师" in removed["positions"]

    with patch(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        return_value=[],
    ):
        setted = save_channel_setup(
            "boss",
            greet_plans=[{"zhiwei": "UI 设计师", "zhize": "视觉", "new_number": 15}],
            greet_plans_mode="set",
            data_dir=setup_env,
        )
    assert setted["positions"] == ["UI 设计师"]
    assert setted["greet_plans"][0]["new_number"] == 15
    wb = ConfigManager.get().read("agent.boss.workbench") or {}
    assert (wb.get("boss") or {}).get("greet_position") == "UI 设计师"


def test_save_channel_boss_multi_enqueue_at_expands(setup_env: Path) -> None:
    """多时刻须拆成多条子任务；禁止落盘 enqueue_at='10:00,11:30'."""
    from plugins.mxai.wizard.setup_guide import get_channel_config, save_channel_setup

    with patch(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        return_value=[],
    ):
        result = save_channel_setup(
            "boss",
            greet_plans=[
                {"zhiwei": "开发工程师", "enqueue_at": "10 11:30", "new_number": 10},
            ],
            greet_plans_mode="add",
            data_dir=setup_env,
        )
    assert result["ok"] is True
    ats = sorted(p["enqueue_at"] for p in result["greet_plans"] if p.get("zhiwei") == "开发工程师")
    assert ats == ["10:00", "11:30"]
    wb = ConfigManager.get().read("agent.boss.workbench") or {}
    plans = (wb.get("boss") or {}).get("greet_plans") or []
    assert all("," not in str(p.get("enqueue_at") or "") for p in plans)
    cfg = get_channel_config("boss")
    assert sorted(
        p["enqueue_at"] for p in cfg["greet_plans"] if p.get("zhiwei") == "开发工程师"
    ) == ["10:00", "11:30"]


def test_save_channel_risk_hot_applies(setup_env: Path) -> None:
    """助理改风控经 ConfigManager.replace，内存与 get_channel 即时可见."""
    from plugins.mxai.wizard.channel_defaults import apply_safe_channel_defaults
    from plugins.mxai.wizard.setup_guide import get_channel_config, save_channel_setup

    apply_safe_channel_defaults(force=True)
    ConfigManager.get().hydrate_all()

    result = save_channel_setup(
        "douyin",
        risk={"daily_dm_limit": 66, "min_interval_sec": 9, "daily_collect_limit": 120},
        data_dir=setup_env,
    )
    assert result["ok"] is True
    assert "risk" in result["applied"]
    assert result["risk"]["daily_dm_limit"] == 66
    assert result["risk"]["min_interval_sec"] == 9

    mem = ConfigManager.get().read("agent.douyin.risk") or {}
    assert mem["daily_dm_limit"] == 66
    assert mem["min_interval_sec"] == 9
    assert mem["daily_collect_limit"] == 120

    cfg = get_channel_config("douyin")
    assert cfg["risk"]["daily_dm_limit"] == 66
    assert cfg["risk"]["min_interval_sec"] == 9


def test_channel_risk_defaults_and_get_channel(setup_env: Path) -> None:
    """按渠道初始化风控；通用模板值可被升级；get_channel 暴露 risk."""
    from plugins.mxai.wizard.channel_defaults import (
        apply_safe_channel_defaults,
        build_channel_risk_defaults,
        merge_channel_risk,
    )
    from plugins.mxai.wizard.channel_defaults import _patch_domain
    from plugins.mxai.wizard.setup_guide import get_channel_config

    dy = build_channel_risk_defaults("douyin")
    assert dy["daily_dm_limit"] == 80
    assert dy["daily_collect_limit"] == 500
    assert dy["daily_reply_limit"] == 50
    assert dy["daily_add_limit"] == 0

    wx = build_channel_risk_defaults("wechat")
    assert wx["daily_add_limit"] == 15
    assert wx["min_interval_sec"] == 8

    # 仍停在通用种子 → 升级为渠道值；用户自定义不覆盖
    upgraded = merge_channel_risk(
        {"daily_dm_limit": 200, "daily_collect_limit": 0, "min_interval_sec": 3},
        "douyin",
        force=False,
    )
    assert upgraded["daily_dm_limit"] == 80
    assert upgraded["daily_collect_limit"] == 500
    custom = merge_channel_risk(
        {"daily_dm_limit": 999, "daily_collect_limit": 12},
        "douyin",
        force=False,
    )
    assert custom["daily_dm_limit"] == 999
    assert custom["daily_collect_limit"] == 12

    _patch_domain(
        "xiaohongshu",
        "risk",
        {
            "daily_dm_limit": 200,
            "daily_add_limit": 30,
            "daily_collect_limit": 0,
            "daily_reply_limit": 0,
            "min_interval_sec": 3,
        },
        merge_mode="replace",
    )
    ConfigManager.get().hydrate_all()
    apply_safe_channel_defaults(force=False)
    ConfigManager.get().hydrate_all()
    xhs_risk = ConfigManager.get().read("agent.xiaohongshu.risk") or {}
    assert xhs_risk["daily_dm_limit"] == 50
    assert xhs_risk["daily_collect_limit"] == 300

    cfg = get_channel_config("xiaohongshu")
    assert "risk" in cfg
    assert cfg["risk"]["daily_dm_limit"] == 50
    assert cfg["risk"]["min_interval_sec"] == 6


def test_save_channel_comment_collect_all_day(setup_env: Path) -> None:
    """评论采集「全天」写入全天窗，并 sync cron."""
    from plugins.mxai.wizard.channel_defaults import _patch_domain
    from plugins.mxai.wizard.setup_guide import get_channel_config, save_channel_setup

    _patch_domain(
        "xiaohongshu",
        "workbench",
        {"comment_collect": {"run_window": {"start": "09:00", "end": "19:00"}, "daily_start_at": "09:00"}},
        merge_mode="replace",
    )
    ConfigManager.get().hydrate_all()

    with patch(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        return_value=[],
    ) as sync_cron:
        result = save_channel_setup(
            "xiaohongshu",
            run_window_module="comment_collect",
            run_window_preset="all_day",
            interval_minutes=40,
            data_dir=setup_env,
        )
    assert result["ok"] is True
    assert "全天" in result["schedule"]["label"]
    assert result["schedule"]["start"] == "00:00"
    assert result["schedule"]["end"] == "23:59"
    assert result["schedule"]["interval_minutes"] == 40
    sync_cron.assert_called_once_with("xiaohongshu")

    cfg = get_channel_config("xiaohongshu")
    assert "全天" in cfg["schedules"]["comment_collect"]["label"]
    assert cfg["schedules"]["comment_collect"]["start"] == "00:00"
    assert cfg["schedules"]["comment_collect"]["end"] == "23:59"
    assert cfg["schedules"]["comment_collect"]["interval_minutes"] == 40
    wb = ConfigManager.get().read("agent.xiaohongshu.workbench") or {}
    assert wb["comment_collect"]["run_window"] == {"start": "00:00", "end": "23:59"}
    assert wb["comment_collect"]["daily_start_at"] == "00:00"
    assert wb["comment_collect"]["interval_minutes"] == 40
    assert (wb.get("scheduler") or {}).get("benchmark_monitor", {}).get("interval_minutes") == 40


def test_save_channel_private_and_boss_run_windows(setup_env: Path) -> None:
    """个微/企微/Boss 工作时段：全天落盘 + get_channel.schedules + cron sync."""
    from plugins.mxai.wizard.channel_defaults import _patch_domain
    from plugins.mxai.wizard.setup_guide import get_channel_config, save_channel_setup

    _patch_domain(
        "wechat",
        "workbench",
        {
            "add_friends": {"run_window": {"start": "09:00", "end": "18:00"}},
            "scheduler": {
                "scheduled_touch": {
                    "enabled": True,
                    "mode": "segmented",
                    "interval_minutes": 20,
                    "run_window": {"start": "10:00", "end": "20:00"},
                }
            },
        },
        merge_mode="replace",
    )
    _patch_domain(
        "qiyeweixin",
        "workbench",
        {"batch_add": {"run_window": {"start": "09:00", "end": "18:00"}}},
        merge_mode="replace",
    )
    _patch_domain(
        "boss",
        "workbench",
        {
            "boss": {
                "greet": {"run_window": {"start": "09:00", "end": "18:00"}},
                "proactive_dm": {
                    "interval_minutes": 30,
                    "run_window": {"start": "09:00", "end": "18:00"},
                },
            }
        },
        merge_mode="replace",
    )
    ConfigManager.get().hydrate_all()

    with patch(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        return_value=[],
    ) as sync_cron:
        wechat = save_channel_setup(
            "wechat",
            run_window_module="add_friends",
            run_window_preset="all_day",
            data_dir=setup_env,
        )
        touch = save_channel_setup(
            "wechat",
            run_window_module="scheduled_touch",
            run_window={"start": "08:00", "end": "22:00"},
            interval_minutes=15,
            data_dir=setup_env,
        )
        qy = save_channel_setup(
            "qiyeweixin",
            run_window_module="batch_add",
            run_window_preset="all_day",
            data_dir=setup_env,
        )
        greet = save_channel_setup(
            "boss",
            run_window_module="boss_greet",
            run_window_preset="all_day",
            data_dir=setup_env,
        )
        dm = save_channel_setup(
            "boss",
            run_window_module="boss_proactive_dm",
            run_window={"start": "10:00", "end": "19:00"},
            interval_minutes=25,
            data_dir=setup_env,
        )

    assert wechat["schedule"] == {
        "module": "add_friends",
        "start": "00:00",
        "end": "23:59",
        "label": "全天",
    }
    assert touch["schedule"]["start"] == "08:00"
    assert touch["schedule"]["interval_minutes"] == 15
    assert qy["schedule"]["end"] == "23:59"
    assert "全天" in greet["schedule"]["label"]
    assert dm["schedule"]["interval_minutes"] == 25
    assert sync_cron.call_count == 5

    wc_cfg = get_channel_config("wechat")
    assert wc_cfg["schedules"]["add_friends"]["start"] == "00:00"
    assert wc_cfg["schedules"]["scheduled_touch"]["end"] == "22:00"
    assert wc_cfg["schedules"]["scheduled_touch"]["interval_minutes"] == 15

    qy_cfg = get_channel_config("qiyeweixin")
    assert "全天" in qy_cfg["schedules"]["batch_add"]["label"]

    boss_cfg = get_channel_config("boss")
    assert boss_cfg["schedules"]["boss_greet"]["start"] == "00:00"
    assert boss_cfg["schedules"]["boss_proactive_dm"]["end"] == "19:00"
    assert boss_cfg["schedules"]["boss_proactive_dm"]["interval_minutes"] == 25


def test_save_channel_keywords_add_and_remove(setup_env: Path) -> None:
    """搜索词同样支持 add/remove，避免只传一词整表覆盖."""
    from plugins.mxai.cfg.comment_keywords import read_comment_keywords
    from plugins.mxai.wizard.channel_defaults import _patch_domain
    from plugins.mxai.wizard.setup_guide import save_channel_setup

    _patch_domain(
        "douyin",
        "comment_keywords",
        {"search_keywords": ["餐饮加盟", "美食探店"], "match_keywords": []},
        merge_mode="replace",
    )
    ConfigManager.get().hydrate_all()

    added = save_channel_setup(
        "douyin",
        search_keywords=["火锅"],
        keywords_mode="add",
        data_dir=setup_env,
    )
    assert added["search_keywords"] == ["餐饮加盟", "美食探店", "火锅"]

    removed = save_channel_setup(
        "douyin",
        search_keywords=["美食探店"],
        keywords_mode="remove",
        data_dir=setup_env,
    )
    assert removed["search_keywords"] == ["餐饮加盟", "火锅"]
    assert read_comment_keywords("douyin")["search_keywords"] == ["餐饮加盟", "火锅"]
