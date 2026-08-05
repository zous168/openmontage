"""LT-020.03.03 T1→T16 链式入队."""

from __future__ import annotations

from plugins.mxai.api.deps import get_queue
from plugins.mxai.crm.lead_service import save_leads
from plugins.mxai.orchestrator.comment_reply_chain import maybe_enqueue_comment_reply_after_collect
from plugins.mxai.orchestrator.task_handlers import handle_comment_collect
from plugins.mxai.orchestrator.models import Task
from plugins.mxai.rpa.types import CollectedComment


def test_auto_chain_after_collect(mxai_env, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(mxai_env))
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.cfg.domains import ensure_config_runtime

    ConfigManager.reset()
    ensure_config_runtime()
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "comment_reply": {
                "enabled": True,
                "auto_after_intent": True,
                "author_name": "测试号",
                "daily_start_at": "00:00",
                "interval_minutes": 60,
                "run_window": {"start": "00:00", "end": "23:59"},
            },
            "comment_collect": {"run_window": {"start": "", "end": ""}},
        },
    )
    ConfigManager.get().patch(
        "agent.douyin.comment_keywords",
        {"search_keywords": ["AI"], "match_keywords": []},
    )
    get_queue().arm_work()
    get_queue().set_agent_enabled("douyin", True)
    lead_ids = save_leads(
        profile_id="douyin",
        source_channel="douyin",
        comments=[CollectedComment("c1", "用户A", "多少钱", "v1", "AI")],
        data_dir=mxai_env,
    )
    chained = maybe_enqueue_comment_reply_after_collect("douyin", lead_ids, parent_task_id="tsk_parent")
    assert len(chained) == 1


def test_chain_respects_interval(mxai_env, monkeypatch) -> None:
    import time

    monkeypatch.setenv("HUB_DATA_DIR", str(mxai_env))
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.cfg.domains import ensure_config_runtime
    from plugins.mxai.scheduler.state import set_last_reply_finished_at

    ConfigManager.reset()
    ensure_config_runtime()
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "comment_reply": {
                "enabled": True,
                "auto_after_intent": True,
                "author_name": "测试号",
                "daily_start_at": "00:00",
                "interval_minutes": 60,
                "run_window": {"start": "00:00", "end": "23:59"},
            },
        },
    )
    ConfigManager.get().patch(
        "agent.douyin.comment_keywords",
        {"search_keywords": ["AI"], "match_keywords": []},
    )
    get_queue().arm_work()
    get_queue().set_agent_enabled("douyin", True)
    set_last_reply_finished_at("douyin", time.time())
    lead_ids = save_leads(
        profile_id="douyin",
        source_channel="douyin",
        comments=[CollectedComment("c1", "用户A", "多少钱", "v1", "AI")],
        data_dir=mxai_env,
    )
    chained = maybe_enqueue_comment_reply_after_collect("douyin", lead_ids, parent_task_id="tsk_parent")
    assert chained == []


def test_comment_collect_handler_chains(mxai_env, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(mxai_env))
    get_queue().arm_work()
    get_queue().set_agent_enabled("douyin", True)
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.cfg.domains import ensure_config_runtime

    ConfigManager.reset()
    ensure_config_runtime()
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {
            "comment_reply": {
                "enabled": True,
                "auto_after_intent": True,
                "author_name": "测试号",
                "daily_start_at": "00:00",
                "interval_minutes": 60,
                "run_window": {"start": "00:00", "end": "23:59"},
            },
            "comment_collect": {"run_window": {"start": "", "end": ""}},
        },
    )
    ConfigManager.get().patch(
        "agent.douyin.comment_keywords",
        {"search_keywords": ["AI"], "match_keywords": []},
    )
    task = Task(
        task_id="tsk_collect",
        name="collect",
        profile_id="douyin",
        task_type="comment_collect",
        payload={"search_keywords": ["AI"], "match_keywords": []},
    )
    result = handle_comment_collect(task)
    assert result["lead_ids"]
    assert result.get("chained_comment_reply")
