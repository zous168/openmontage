"""CR-169 · 客户视频评论 bootstrap 入队与门闸。"""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.domains import ensure_config_runtime
from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.cfg.module_enabled import read_module_enabled
from plugins.mxai.crm.lead_service import insert_comment_lead
from plugins.mxai.orchestrator.bootstrap_public import bootstrap_video_comment
from plugins.mxai.orchestrator.module_status import module_status_for_agent
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.risk.cooldown import CooldownTracker


@pytest.fixture
def vc_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_dir = tmp_path / "hub"
    profiles = data_dir / "profiles" / "douyin"
    profiles.mkdir(parents=True)
    (profiles / "config.yaml").write_text("model: test\n", encoding="utf-8")
    (profiles / "run_enabled.yaml").write_text("enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: data_dir)
    monkeypatch.setattr("plugins.mxai.scheduler.state.resolve_hub_data_dir_path", lambda: data_dir)
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir", lambda name: data_dir / "profiles" / name
    )
    QueueManager.reset()
    ConfigManager.reset()
    # CooldownTracker 是类级全局（跨用例残留），不清会让后续入队被风控冷却拒掉
    CooldownTracker.reset()
    ensure_config_runtime()
    q = QueueManager.get()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("douyin", True)
    return data_dir


def _configure(**over) -> None:
    section = {"auto_enabled": True, "interval_minutes": 30}
    section.update(over)
    ConfigManager.get().patch("agent.douyin.workbench", {"video_comment": section})


def _seed(env: Path, douyin_id: str = "dy_vc") -> str:
    r = insert_comment_lead(
        profile_id="douyin",
        nickname="客户",
        douyin_id=douyin_id,
        comment="c",
        intent="高",
        data_dir=env,
    )
    return str(r["lead_id"])


def test_module_default_disabled(vc_env: Path) -> None:
    """新模块默认关：升级后不会自动开始给客户视频发评论。"""
    assert read_module_enabled("douyin", "video_comment") is False
    assert bootstrap_video_comment("douyin") == []


def test_enqueue_uses_douyin_id_and_customer_comment(vc_env: Path) -> None:
    """D-b：不再下发话术；改带客户那条评论作为 AI 生成输入。"""
    _seed(vc_env, "dy_target")
    _configure()
    rows = bootstrap_video_comment("douyin")
    assert len(rows) == 1
    task = QueueManager.get()._tasks[rows[0]["task_id"]]
    assert task.task_type == "video_comment"
    assert task.payload["recipient"] == "dy_target"
    assert task.payload["customer_comment"] == "c"  # _seed 里客户的评论
    assert "message" not in task.payload


def test_enqueue_no_longer_needs_message(vc_env: Path) -> None:
    """D-b：正文一律 AI 生成，配置里没有话术也照常入队。"""
    _seed(vc_env)
    _configure()
    assert len(bootstrap_video_comment("douyin")) == 1


def test_disabled_blocks_enqueue(vc_env: Path) -> None:
    _seed(vc_env)
    _configure(auto_enabled=False)
    assert bootstrap_video_comment("douyin") == []


def test_run_window_blocks_auto_but_not_manual(vc_env: Path) -> None:
    """时段外：自动路径 skip；manual 绕过（FR-SCHED-11）。"""
    _seed(vc_env)
    _configure(run_window={"start": "03:00", "end": "03:01"})
    assert bootstrap_video_comment("douyin") == []
    rows = bootstrap_video_comment("douyin", source="manual")
    assert len(rows) == 1


def test_interval_not_elapsed_skips(vc_env: Path) -> None:
    import time

    from plugins.mxai.scheduler.state import set_last_video_comment_finished_at

    _seed(vc_env)
    _configure(interval_minutes=30)
    set_last_video_comment_finished_at("douyin", time.time())
    assert bootstrap_video_comment("douyin") == []
    # manual 不受轮次间隔约束
    assert len(bootstrap_video_comment("douyin", source="manual")) == 1


def test_terminal_records_round_baseline(vc_env: Path) -> None:
    """终态必须写 last_finished_at，否则轮次间隔门闸形同虚设（审查发现的 blocker）。"""
    from plugins.mxai.scheduler.public_round_scheduler import record_round_finished
    from plugins.mxai.scheduler.state import get_last_video_comment_finished_at

    # 不断言初始为 None（scheduler_state 是进程外文件，整包跑时可能已被写过），
    # 只断言「记一次终态 → 基准前进」，这才是门闸真正依赖的性质。
    before = get_last_video_comment_finished_at("douyin") or 0.0
    record_round_finished("douyin", "video_comment")
    after = get_last_video_comment_finished_at("douyin")
    assert after is not None and after >= before


def test_queue_terminal_hooks_cover_video_comment() -> None:
    """队列终态回调的 task_type 白名单须含 video_comment（成功与失败两条路径）。"""
    import re
    from pathlib import Path as _P

    src = _P("src/plugins/mxai/orchestrator/queue_manager.py").read_text(encoding="utf-8")
    hooks = re.findall(r'task\.task_type in \(([^)]*)\):\s*\n\s*from plugins\.mxai\.scheduler\.public_round_scheduler import record_round_finished', src)
    assert hooks, "未找到 record_round_finished 调用点"
    for group in hooks:
        assert "video_comment" in group, f"终态回调白名单缺 video_comment: {group}"


def test_enqueue_one_per_round(vc_env: Path) -> None:
    _seed(vc_env, "dy_1")
    _seed(vc_env, "dy_2")
    _configure()
    rows = bootstrap_video_comment("douyin")
    assert len(rows) == 1


def _rows(profile_id: str) -> list[dict]:
    return module_status_for_agent(
        profile_id, work_armed=True, scheduler_active=True, agent_enabled=True
    )


def test_module_row_only_on_douyin(vc_env: Path) -> None:
    """模块仅出现在抖音；小红书/视频号不展示（本期范围）。"""
    assert "video_comment" in {r["module_id"] for r in _rows("douyin")}
    assert "video_comment" not in {r["module_id"] for r in _rows("xiaohongshu")}


def test_module_status_ready_without_message(vc_env: Path) -> None:
    """D-b：无话术字段 → 就绪判定只看运行时段，不再要求填话术。"""
    _configure(run_window={"start": "09:00", "end": "21:00"})
    row = next(r for r in _rows("douyin") if r["module_id"] == "video_comment")
    assert row["init_status"] == "ready"
    assert "评论话术" not in (row.get("missing_hint") or "")


def test_module_status_still_requires_run_window(vc_env: Path) -> None:
    """时段仍是必填（CR-151）——去掉话术不等于什么都不用配。"""
    _configure(run_window={"start": "", "end": ""})
    row = next(r for r in _rows("douyin") if r["module_id"] == "video_comment")
    assert row["init_status"] == "missing_config"
