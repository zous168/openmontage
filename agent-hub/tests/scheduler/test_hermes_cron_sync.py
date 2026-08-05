"""CR-132 / LT-038.03：Hermes Cron 首次建一次（确定性 id + 中文 name + create-if-absent）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from agent.profile_scope import hermes_profile_scope
from cron.jobs import list_jobs, resolve_job_ref
from plugins.mxai.cfg.agent_bindings import agent_profile_for_channel
from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.scheduler.cron import (
    benchmark_job_id,
    comment_collect_job_id,
    scheduled_touch_job_id,
    scheduled_touch_job_name,
    sync_comment_collect_job,
    sync_scheduled_touch_job,
    sync_benchmark_job,
)


@pytest.fixture
def sync_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setattr(
        "runtime_paths.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.state.resolve_hub_data_dir_path",
        lambda: data_dir,
    )
    profiles = data_dir / "profiles"
    # 业务 Agent profile（cron 按 kind→功能 落盘）
    biz_profiles = sorted(
        {
            agent_profile_for_channel(name)
            for name in ("wechat", "qiyeweixin", "douyin", "xiaohongshu", "shipinhao", "boss")
        }
        | {"boss_resume"}
    )
    for name in biz_profiles:
        p = profiles / name
        p.mkdir(parents=True)
        (p / "config.yaml").write_text("model: test\n", encoding="utf-8")
        if name in ("wechat_chat", "qiyeweixin_chat"):
            (p / "risk.yaml").write_text("daily_dm_limit: 9999\n", encoding="utf-8")
    ConfigManager.reset()
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profiles / name,
    )
    ensure_runtime_bootstrap(data_dir)
    ensure_config_runtime()
    # CR-162：既有 sync 单测默认满足 G1+G2（不写盘、不提前 sync），专注功能开关 / schedule
    monkeypatch.setattr(
        "plugins.mxai.scheduler.cron._g1_scheduler_active",
        lambda: True,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.run_enabled.is_run_enabled",
        lambda _pid: True,
    )
    return data_dir


def _touch_wb(interval: int = 30) -> dict:
    return {
        "scheduler": {
            "scheduled_touch": {"enabled": True, "mode": "segmented", "interval_minutes": interval}
        }
    }


def _cron_home(sync_env: Path, channel_id: str) -> Path:
    return sync_env / "profiles" / agent_profile_for_channel(channel_id)


def test_sync_scheduled_touch_creates_job_with_id_and_chinese_name(sync_env: Path) -> None:
    result = sync_scheduled_touch_job("wechat", _touch_wb(30))
    assert result and result.get("ensured")
    # 确定性 id（路径安全，无冒号）+ 中文 name
    assert result["job_id"] == scheduled_touch_job_id("wechat") == "mxai-wechat-scheduled_touch"
    assert result["job_name"] == scheduled_touch_job_name("wechat") == "微信·存量定时触达"

    profile_home = _cron_home(sync_env, "wechat")
    with hermes_profile_scope(profile_home):
        job = resolve_job_ref(scheduled_touch_job_id("wechat"))
    assert job is not None
    assert job["id"] == "mxai-wechat-scheduled_touch"  # id = 确定性
    assert job["name"] == "微信·存量定时触达"  # name = 中文
    # http 执行类型（方案 A）：url 指向 gateway 内 cron-run 端点，非脚本
    http = job.get("http")
    assert http and "/api/plugins/mxai/cron/run/scheduled_touch/wechat" in http["url"]
    assert job.get("script") is None


def test_sync_matches_job_by_id(sync_env: Path) -> None:
    from plugins.mxai.scheduler.cron import sync_benchmark_job

    sync_benchmark_job("douyin", {"scheduler": {"benchmark_monitor": {"enabled": True, "interval_minutes": 45}}})
    sync_scheduled_touch_job("wechat", _touch_wb(15))

    with hermes_profile_scope(_cron_home(sync_env, "douyin")):
        jobs = list_jobs(include_disabled=True)
    assert any(j.get("id") == benchmark_job_id("douyin") for j in jobs)

    with hermes_profile_scope(_cron_home(sync_env, "wechat")):
        jobs = list_jobs(include_disabled=True)
    assert any(j.get("id") == scheduled_touch_job_id("wechat") for j in jobs)


def test_sync_comment_collect_job_create_and_schedule(sync_env: Path) -> None:
    """公域评论采集独立 cron：初始化创建，改间隔/时段后指纹同步."""
    jid = comment_collect_job_id("xiaohongshu")
    profile_home = _cron_home(sync_env, "xiaohongshu")
    wb = {
        "comment_collect": {
            "enabled": True,
            "interval_minutes": 40,
            "run_window": {"start": "00:00", "end": "23:59"},
        },
    }
    row = sync_comment_collect_job("xiaohongshu", wb)
    assert row is not None
    assert row["job_id"] == jid
    assert row["schedule"] == "*/40 * * * *"
    with hermes_profile_scope(profile_home):
        job = resolve_job_ref(jid)
    assert job is not None
    assert job["name"] == "小红书·评论采集"
    http = job.get("http") or {}
    assert "/api/plugins/mxai/cron/run/comment_collect/xiaohongshu" in str(http.get("url") or "")
    assert job.get("enabled") is True

    sync_comment_collect_job(
        "xiaohongshu",
        {
            "comment_collect": {
                "enabled": True,
                "interval_minutes": 20,
                "run_window": {"start": "09:00", "end": "18:00"},
            },
        },
    )
    with hermes_profile_scope(profile_home):
        job2 = resolve_job_ref(jid)
    assert job2["schedule"]["expr"] == "*/20 9-18 * * *"

    sync_comment_collect_job(
        "xiaohongshu",
        {"comment_collect": {**wb["comment_collect"], "enabled": False}},
    )
    with hermes_profile_scope(profile_home):
        assert resolve_job_ref(jid).get("enabled") is False


def test_sync_comment_reply_job_create_and_schedule(sync_env: Path) -> None:
    """公域 AI 评论回复独立 cron：间隔+时段 → 表达式；关开关则 enabled=false（不再卡昵称）."""
    from plugins.mxai.scheduler.cron import (
        comment_reply_job_id,
        sync_comment_reply_job,
    )

    jid = comment_reply_job_id("douyin")
    profile_home = _cron_home(sync_env, "douyin")
    wb = {
        "comment_reply": {
            "enabled": True,
            "author_name": "",
            "interval_minutes": 30,
            "run_window": {"start": "09:00", "end": "18:00"},
        },
    }
    row = sync_comment_reply_job("douyin", wb)
    assert row is not None
    assert row["job_id"] == jid
    assert row["schedule"] == "*/30 9-18 * * *"
    with hermes_profile_scope(profile_home):
        job = resolve_job_ref(jid)
    assert job is not None
    assert job["name"] == "抖音·AI评论回复"
    http = job.get("http") or {}
    assert "/api/plugins/mxai/cron/run/comment_reply/douyin" in str(http.get("url") or "")
    assert job.get("enabled") is True

    sync_comment_reply_job(
        "douyin",
        {
            "comment_reply": {
                **wb["comment_reply"],
                "interval_minutes": 15,
                "run_window": {"start": "00:00", "end": "23:59"},
            },
        },
    )
    with hermes_profile_scope(profile_home):
        assert resolve_job_ref(jid)["schedule"]["expr"] == "*/15 * * * *"

    sync_comment_reply_job(
        "douyin",
        {"comment_reply": {**wb["comment_reply"], "enabled": False}},
    )
    with hermes_profile_scope(profile_home):
        assert resolve_job_ref(jid).get("enabled") is False

    sync_comment_reply_job(
        "douyin",
        {"comment_reply": {**wb["comment_reply"], "enabled": True, "author_name": ""}},
    )
    with hermes_profile_scope(profile_home):
        assert resolve_job_ref(jid).get("enabled") is True


def test_workbench_sync_updates_schedule(sync_env: Path) -> None:
    """workbench 改 interval 后同步更新 jobs.json schedule（G1 · CR-143）。"""
    jid = scheduled_touch_job_id("wechat")
    profile_home = _cron_home(sync_env, "wechat")

    sync_scheduled_touch_job("wechat", _touch_wb(30))
    with hermes_profile_scope(profile_home):
        job = resolve_job_ref(jid)
    assert job is not None
    assert job["schedule"]["minutes"] == 30

    sync_scheduled_touch_job("wechat", _touch_wb(5))

    with hermes_profile_scope(profile_home):
        jobs = [j for j in list_jobs(include_disabled=True) if j.get("id") == jid]
    assert len(jobs) == 1
    assert jobs[0]["schedule"]["minutes"] == 5


def test_create_if_absent_idempotent_no_duplicate(sync_env: Path) -> None:
    """同一 config 二次 sync 不重复建 job。"""
    jid = scheduled_touch_job_id("wechat")
    sync_scheduled_touch_job("wechat", _touch_wb(30))
    sync_scheduled_touch_job("wechat", _touch_wb(30))

    with hermes_profile_scope(_cron_home(sync_env, "wechat")):
        jobs = [j for j in list_jobs(include_disabled=True) if j.get("id") == jid]
    assert len(jobs) == 1


def test_sync_disabled_still_creates_job(sync_env: Path) -> None:
    """未启用也必须创建：enabled=false 落盘，不跳过。"""
    jid = scheduled_touch_job_id("wechat")
    result = sync_scheduled_touch_job(
        "wechat",
        {"scheduler": {"scheduled_touch": {"enabled": False, "mode": "segmented", "interval_minutes": 30}}},
    )
    assert result and result.get("ensured")
    assert result.get("enabled") is False

    with hermes_profile_scope(_cron_home(sync_env, "wechat")):
        job = resolve_job_ref(jid)
    assert job is not None
    assert job.get("enabled") is False


def test_sync_boss_jobs_land_on_feature_agents(sync_env: Path) -> None:
    from plugins.mxai.scheduler.cron import (
        boss_greet_schedule_job_id,
        boss_proactive_dm_job_id,
        sync_boss_greet_schedule_job,
        sync_boss_proactive_dm_job,
    )

    wb = {"boss": {"dm_enabled": True, "greet_enabled": False, "greet_plans": []}}
    sync_boss_proactive_dm_job("boss", wb)
    sync_boss_greet_schedule_job("boss", wb)

    dm_home = sync_env / "profiles" / "boss_dm"
    resume_home = sync_env / "profiles" / "boss_resume"
    with hermes_profile_scope(dm_home):
        assert resolve_job_ref(boss_proactive_dm_job_id("boss")) is not None
        assert resolve_job_ref(boss_greet_schedule_job_id("boss")) is None
    with hermes_profile_scope(resume_home):
        assert resolve_job_ref(boss_greet_schedule_job_id("boss")) is not None


def test_init_creates_maintenance_and_business_uniformly(sync_env: Path) -> None:
    """插件启动统一初始化：维护 job + 业务 job 未启用也须落盘（与 init 同 sync 路径）。"""
    from plugins.mxai.scheduler.cron import MAINTENANCE_JOB_ID, sync_maintenance_job

    m = sync_maintenance_job()
    assert m and m.get("job_id") == MAINTENANCE_JOB_ID

    result = sync_scheduled_touch_job(
        "wechat",
        {"scheduler": {"scheduled_touch": {"enabled": False, "mode": "segmented", "interval_minutes": 30}}},
    )
    assert result and result.get("job_id") == scheduled_touch_job_id("wechat")
    assert result.get("enabled") is False

    with hermes_profile_scope(_cron_home(sync_env, "wechat")):
        job = resolve_job_ref(scheduled_touch_job_id("wechat"))
    assert job is not None
    assert job.get("enabled") is False


def test_sync_rehomes_job_when_binding_changes(sync_env: Path) -> None:
    """功能页改 agent_bindings 后 sync 将 job 迁到新 profile 并更新 schedule."""
    from plugins.mxai.cfg.agent_bindings import FEATURE_FIRST_COMMENT
    from plugins.mxai.scheduler.cron import first_comment_job_id, sync_profile_scheduler_jobs

    wrong_home = sync_env / "profiles" / "douyin_dm"
    wrong_home.mkdir(parents=True, exist_ok=True)
    jid = first_comment_job_id("douyin")
    wb = {
        "agent_bindings": {
            "default": "douyin_comment",
            "modules": {FEATURE_FIRST_COMMENT: "douyin_comment"},
        },
        "scheduler": {
            "first_comment": {
                "enabled": True,
                "interval_minutes": 30,
                "run_window": {"start": "09:00", "end": "18:00"},
            }
        },
    }
    with hermes_profile_scope(wrong_home):
        from cron.jobs import create_job

        create_job(
            id=jid,
            name="抖音·巡检首评",
            schedule="0 9 * * *",
            http={"url": "http://127.0.0.1:8642/api/plugins/mxai/cron/run/first_comment_daily/douyin"},
            deliver="local",
            prompt="抖音·巡检首评",
        )

    sync_profile_scheduler_jobs("douyin", wb)

    right_home = sync_env / "profiles" / "douyin_comment"
    with hermes_profile_scope(right_home):
        job = resolve_job_ref(jid)
    assert job is not None
    assert job.get("schedule", {}).get("expr") == "*/30 9-18 * * *"
    with hermes_profile_scope(wrong_home):
        assert resolve_job_ref(jid) is None


def test_benchmark_cron_enabled_follows_feature_switches(sync_env: Path) -> None:
    """对标监控 cron enabled 与采集/回复功能页开关一致."""
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.scheduler.cron import sync_benchmark_job

    ConfigManager.get().patch(
        "agent.douyin.benchmarks",
        {"accounts": ["@bench_a"]},
    )
    base_wb = {
        "comment_collect": {"enabled": True},
        "comment_reply": {"enabled": True},
        "scheduler": {"benchmark_monitor": {"enabled": True, "interval_minutes": 45}},
    }
    jid = benchmark_job_id("douyin")
    profile_home = _cron_home(sync_env, "douyin")

    sync_benchmark_job("douyin", base_wb)
    with hermes_profile_scope(profile_home):
        assert resolve_job_ref(jid).get("enabled") is True

    sync_benchmark_job(
        "douyin",
        {**base_wb, "comment_reply": {"enabled": False}},
    )
    with hermes_profile_scope(profile_home):
        assert resolve_job_ref(jid).get("enabled") is False

    sync_benchmark_job(
        "douyin",
        {**base_wb, "comment_collect": {"enabled": False}},
    )
    with hermes_profile_scope(profile_home):
        assert resolve_job_ref(jid).get("enabled") is False


def test_rehome_deduplicates_job_across_profiles(sync_env: Path) -> None:
    """同一 mxai job id 落在多 profile 时 rehome 只保留目标 profile 一份."""
    from plugins.mxai.cfg.migrations._cron_channel_relocate import (
        _read_jobs_list,
        _write_jobs_list,
        rehome_channel_mxai_jobs,
    )

    jid = benchmark_job_id("douyin")
    target_home = sync_env / "profiles" / "douyin_comment"
    duplicate_home = sync_env / "profiles" / "douyin_dm"
    duplicate_home.mkdir(parents=True, exist_ok=True)
    # bootstrap/set_run_enabled→sync 可能已写入同 id；先清再种，避免 create_job 追加重复
    for home in (target_home, duplicate_home):
        jf = home / "cron" / "jobs.json"
        if jf.is_file():
            _write_jobs_list(
                jf,
                [j for j in _read_jobs_list(jf) if str(j.get("id") or "") != jid],
            )
    http = {
        "url": "http://127.0.0.1:8642/api/plugins/mxai/cron/run/benchmark_monitor/douyin",
        "method": "POST",
    }
    for home in (target_home, duplicate_home):
        with hermes_profile_scope(home):
            from cron.jobs import create_job

            create_job(
                id=jid,
                name="抖音·对标监控",
                schedule="every 45m",
                http=http,
                deliver="local",
                prompt="抖音·对标监控",
            )

    changed = rehome_channel_mxai_jobs(sync_env, "douyin", {})
    assert changed >= 1

    with hermes_profile_scope(target_home):
        jobs = [j for j in list_jobs(include_disabled=True) if j.get("id") == jid]
        assert len(jobs) == 1
    with hermes_profile_scope(duplicate_home):
        assert resolve_job_ref(jid) is None


def test_put_benchmarks_syncs_benchmark_cron_enabled(sync_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """PUT benchmarks 增删账号后立即同步 benchmark_monitor cron enabled."""
    from plugins.mxai.api.agents import BenchmarksBody, put_benchmarks
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.scheduler.cron import sync_benchmark_job

    monkeypatch.setattr("plugins.mxai.api.agents.require_agent", lambda _a: None)

    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "comment_collect": {"enabled": True},
            "comment_reply": {"enabled": True},
            "scheduler": {"benchmark_monitor": {"enabled": True, "interval_minutes": 45}},
        },
    )
    wb = ConfigManager.get().read("agent.douyin.workbench") or {}
    sync_benchmark_job("douyin", wb)
    jid = benchmark_job_id("douyin")
    profile_home = _cron_home(sync_env, "douyin")

    put_benchmarks("douyin", BenchmarksBody(accounts=["@bench_a"]))
    with hermes_profile_scope(profile_home):
        assert resolve_job_ref(jid).get("enabled") is True

    put_benchmarks("douyin", BenchmarksBody(accounts=[]))
    with hermes_profile_scope(profile_home):
        assert resolve_job_ref(jid).get("enabled") is False


def test_three_gate_g1_off_disables_job(sync_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-162：未开工（G1 关）即使功能开，job.enabled=false。"""
    from plugins.mxai.scheduler.cron import compute_mxai_job_enabled

    monkeypatch.setattr(
        "plugins.mxai.scheduler.cron._g1_scheduler_active",
        lambda: False,
    )
    wb = _touch_wb(30)
    assert compute_mxai_job_enabled("wechat", "scheduled_touch", wb) is False
    result = sync_scheduled_touch_job("wechat", wb)
    assert result and result.get("enabled") is False
    with hermes_profile_scope(_cron_home(sync_env, "wechat")):
        assert resolve_job_ref(scheduled_touch_job_id("wechat")).get("enabled") is False


def test_three_gate_g2_off_disables_job(sync_env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """CR-162：渠道总闸关（G2）→ job.enabled=false。"""
    from plugins.mxai.scheduler.cron import compute_mxai_job_enabled

    monkeypatch.setattr(
        "plugins.mxai.cfg.run_enabled.is_run_enabled",
        lambda pid: False if pid == "wechat" else True,
    )
    wb = _touch_wb(30)
    assert compute_mxai_job_enabled("wechat", "scheduled_touch", wb) is False
    result = sync_scheduled_touch_job("wechat", wb)
    assert result and result.get("enabled") is False


def test_three_gate_all_open_enables_job(sync_env: Path) -> None:
    """CR-162：三门全开 → enabled=true。"""
    from plugins.mxai.scheduler.cron import compute_mxai_job_enabled

    wb = _touch_wb(30)
    assert compute_mxai_job_enabled("wechat", "scheduled_touch", wb) is True
    result = sync_scheduled_touch_job("wechat", wb)
    assert result and result.get("enabled") is True
    with hermes_profile_scope(_cron_home(sync_env, "wechat")):
        assert resolve_job_ref(scheduled_touch_job_id("wechat")).get("enabled") is True


def test_compute_first_comment_enabled_without_mode(sync_env: Path) -> None:
    from plugins.mxai.scheduler.cron import compute_mxai_job_enabled

    wb = {
        "scheduler": {
            "first_comment": {"enabled": True, "interval_minutes": 30},
        }
    }
    assert compute_mxai_job_enabled("douyin", "first_comment_daily", wb) is True
    wb["scheduler"]["first_comment"]["enabled"] = False
    assert compute_mxai_job_enabled("douyin", "first_comment_daily", wb) is False
