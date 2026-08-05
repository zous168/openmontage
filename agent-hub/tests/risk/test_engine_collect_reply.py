"""CR-143：comment_collect / comment_reply 风控真管道（check_enqueue + QueueManager）."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.cfg.bootstrap.runtime_bootstrap import ensure_runtime_bootstrap
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.risk.engine import check_enqueue, check_execute, get_risk_limits
from plugins.mxai.worklog.service import append_worklog


@pytest.fixture(autouse=True)
def _reset_cfg_manager() -> None:
    from plugins.mxai.cfg.manager import ConfigManager

    ConfigManager.reset()
    yield
    ConfigManager.reset()


@pytest.fixture
def pipe_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
    # risk SSOT 在 cfg/{channel}/，非 profiles/（bootstrap 会清掉误建的渠道 profile 目录）
    from plugins.mxai.cfg.paths import agent_cfg_path

    risk_path = agent_cfg_path("douyin", "risk.yaml")
    risk_path.parent.mkdir(parents=True, exist_ok=True)
    risk_path.write_text(
        "daily_collect_limit: 2\ndaily_reply_limit: 1\nenabled: true\n",
        encoding="utf-8",
    )
    mgr = ConfigManager.get()
    mgr._snapshots.pop("agent.douyin.risk", None)
    mgr.patch(
        "agent.douyin.risk",
        {"daily_collect_limit": 2, "daily_reply_limit": 1, "enabled": True},
    )
    return data_dir


def test_get_risk_limits_includes_collect_reply(pipe_env: Path) -> None:
    limits = get_risk_limits("douyin")
    assert limits["daily_collect_limit"] == 2
    assert limits["daily_reply_limit"] == 1


def test_comment_collect_enqueue_blocked(pipe_env: Path) -> None:
    from plugins.mxai.crm.lead_service import insert_comment_lead

    for i in range(2):
        insert_comment_lead(
            profile_id="douyin",
            nickname=f"用户{i}",
            douyin_id=f"dy_uid_{i}",
            comment="多少钱",
            intent="高",
            data_dir=pipe_env,
        )
    # 多跑几次采集工作流本身不超限；按客户数才拦
    for _ in range(5):
        append_worklog(
            profile_id="douyin",
            op_type="comment_collect",
            exec_status="成功",
            data_dir=pipe_env,
        )
    enq = check_enqueue("douyin", "comment_collect", data_dir=pipe_env)
    assert enq.allowed is False
    assert "daily_collect_limit" in enq.reason


def test_comment_collect_allows_when_workflows_many_but_customers_under_limit(
    pipe_env: Path,
) -> None:
    for _ in range(5):
        append_worklog(
            profile_id="douyin",
            op_type="comment_collect",
            exec_status="成功",
            data_dir=pipe_env,
        )
    enq = check_enqueue("douyin", "comment_collect", data_dir=pipe_env)
    assert enq.allowed is True


def test_comment_reply_execute_dual_check(pipe_env: Path) -> None:
    from plugins.mxai.crm.lead_service import insert_comment_lead, record_comment_reply_success

    lead = insert_comment_lead(
        profile_id="douyin",
        nickname="回复用户",
        douyin_id="dy_reply_1",
        comment="怎么联系",
        intent="高",
        data_dir=pipe_env,
    )
    record_comment_reply_success(
        lead["lead_id"],
        platform_reply_comment_id="pr1",
        max_replies_per_lead=1,
        data_dir=pipe_env,
    )
    # 工作流 WorkLog 再多也不应单独作为日上限依据
    for _ in range(3):
        append_worklog(
            profile_id="douyin",
            op_type="comment_reply",
            exec_status="成功",
            data_dir=pipe_env,
        )
    enq = check_enqueue("douyin", "comment_reply", data_dir=pipe_env)
    exe = check_execute("douyin", "comment_reply", data_dir=pipe_env)
    assert enq.allowed is False
    assert exe.allowed is False
    assert "daily_reply_limit" in enq.reason


def test_comment_reply_allows_when_only_workflows_no_replies(pipe_env: Path) -> None:
    for _ in range(5):
        append_worklog(
            profile_id="douyin",
            op_type="comment_reply",
            exec_status="成功",
            data_dir=pipe_env,
        )
    assert check_enqueue("douyin", "comment_reply", data_dir=pipe_env).allowed is True


def test_queue_enqueue_collect_writes_risk_worklog(pipe_env: Path) -> None:
    from plugins.mxai.crm.lead_service import insert_comment_lead

    for i in range(2):
        insert_comment_lead(
            profile_id="douyin",
            nickname=f"超限用户{i}",
            douyin_id=f"dy_over_{i}",
            comment="求报价",
            intent="高",
            data_dir=pipe_env,
        )
    q = QueueManager.get()
    with pytest.raises(ValueError, match="daily_collect_limit"):
        q.enqueue(
            profile_id="douyin",
            name="超限采集",
            task_type="comment_collect",
            payload={"search_keywords": ["AI"]},
            bypass_work_armed=True,
        )


def test_reply_limit_fallback_workbench_max_per_day(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profiles / name,
    )
    from plugins.mxai.cfg.domains import ensure_config_runtime
    from plugins.mxai.cfg.manager import ConfigManager

    ConfigManager.reset()
    ensure_runtime_bootstrap(data_dir)
    ensure_config_runtime()
    from plugins.mxai.cfg.paths import agent_cfg_path
    from plugins.mxai.cfg.store import atomic_write_yaml

    # 无 daily_reply_limit 键 → 回退 workbench.comment_reply.max_per_day
    atomic_write_yaml(agent_cfg_path("douyin", "risk.yaml"), {"enabled": True})
    ConfigManager.get().reload_domain("agent.douyin.risk")
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {"comment_reply": {"max_per_day": 1, "enabled": True, "author_name": "x"}},
    )
    assert get_risk_limits("douyin")["daily_reply_limit"] == 1
    from plugins.mxai.crm.lead_service import insert_comment_lead, record_comment_reply_success

    lead = insert_comment_lead(
        profile_id="douyin",
        nickname="回退用户",
        douyin_id="dy_fb_1",
        comment="报价",
        intent="高",
        data_dir=data_dir,
    )
    record_comment_reply_success(
        lead["lead_id"],
        platform_reply_comment_id="pr_fb",
        max_replies_per_lead=1,
        data_dir=data_dir,
    )
    blocked = check_enqueue("douyin", "comment_reply", data_dir=data_dir)
    assert blocked.allowed is False
