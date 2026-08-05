"""LT-020.03.02 handle_comment_reply handler."""

from __future__ import annotations

from plugins.mxai.orchestrator.models import Task, TaskStatus
from plugins.mxai.orchestrator.task_handlers import handle_comment_reply
from plugins.mxai.crm.lead_service import get_lead, save_leads
from plugins.mxai.rpa.types import CollectedComment


def test_handle_comment_reply_success(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    data_dir = tmp_path
    lead_id = save_leads(
        profile_id="douyin",
        source_channel="douyin",
        comments=[CollectedComment("c1", "用户A", "多少钱", "v1", "kw")],
        data_dir=data_dir,
    )[0]
    task = Task(
        task_id="tsk_test",
        name="reply",
        profile_id="douyin",
        task_type="comment_reply",
        payload={"lead_ids": [lead_id]},
    )
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.task_handlers.resolve_reply",
        lambda *_a, **_k: {"source": "faq", "text": "欢迎咨询"},
    )
    from types import SimpleNamespace

    monkeypatch.setattr(
        "plugins.mxai.orchestrator.task_handlers.run_comment_reply",
        lambda *_a, **_k: SimpleNamespace(platform_reply_comment_id="rc_test"),
    )
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.task_handlers.apply_operation_cooldown",
        lambda *_a, **_k: 0,
    )
    result = handle_comment_reply(task)
    assert result["replied"] == 1
    lead = get_lead(lead_id=lead_id, data_dir=data_dir)
    assert int(lead["comment_reply_count"]) == 1
    assert lead["comment_reply_status"] == "sent"
    assert lead["platform_reply_comment_id"]


def test_handle_comment_reply_disabled(tmp_path, monkeypatch) -> None:
    from plugins.mxai.cfg.manager import ConfigManager

    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    from plugins.mxai.cfg.domains import ensure_config_runtime

    ConfigManager.reset()
    ensure_config_runtime()
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {"comment_reply": {"enabled": False}},
    )
    task = Task(
        task_id="tsk_off",
        name="reply",
        profile_id="douyin",
        task_type="comment_reply",
        payload={"lead_ids": ["lead_x"]},
    )
    result = handle_comment_reply(task)
    assert result["skipped"] is True
