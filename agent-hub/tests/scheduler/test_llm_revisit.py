"""LT-038.02.01：content_mode=llm 回访提示词 hook（内联生成 · profile 人设 · 原生历史）."""

from __future__ import annotations

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.scheduler.segmented_touch import (
    TouchCandidate,
    llm_revisit_message,
    normalize_scheduled_touch_config,
)


def _cand(uid: str = "cust_x") -> TouchCandidate:
    return TouchCandidate(
        customer_uid=uid,
        display_name="张三",
        segment_id="silence_1d",
        segment_label="1天未回复",
        message="您好{display_name}",
        last_inbound_at="2026-07-01T00:00:00+00:00",
        silence_sec=172800.0,
    )


def test_normalize_passes_content_mode_and_revisit_prompt() -> None:
    cfg = normalize_scheduled_touch_config(
        {"mode": "segmented", "content_mode": "llm", "revisit_prompt": "关心客户近况"}
    )
    assert cfg["content_mode"] == "llm"
    assert cfg["revisit_prompt"] == "关心客户近况"
    # 缺省回落 static
    assert normalize_scheduled_touch_config({"mode": "segmented"})["content_mode"] == "static"


def test_build_ephemeral_is_generic_kb_vision_only() -> None:
    """通用 ephemeral builder 只管 kb/vision，**不认识**回访业务概念（回访框架已移回本域）。"""
    from plugins.mxai.agents.hermes_agent import _build_ephemeral_system_message

    assert _build_ephemeral_system_message() == ""
    assert "知识库" in _build_ephemeral_system_message(kb_context="FAQ 内容")
    assert "定时回访任务" not in _build_ephemeral_system_message(kb_context="x", vision_context="y")


def test_llm_revisit_hooks_prompt_as_system_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """回访提示词组织成通用 system_message 注入；session_id=客户 inbound（原生历史）；profile=业务号."""
    captured: dict[str, object] = {}

    def _fake_complete(profile_id: str, message: str, **kwargs):
        captured["profile_id"] = profile_id
        captured["message"] = message
        captured.update(kwargs)
        return {"text": "张三您好，好久不见，最近可好？", "source": "agent_llm"}

    monkeypatch.setattr(
        "plugins.mxai.agents.hermes_agent.complete_profile_agent_reply", _fake_complete
    )

    text = llm_revisit_message("wechat", _cand(), revisit_prompt="关心客户近况")
    assert text == "张三您好，好久不见，最近可好？"
    # 铁律：业务 profile，非 assistant
    assert captured["profile_id"] == "wechat"
    # hook：revisit_prompt → 通用 system_message（含回访框架 + 目标；业务语义留在本域）
    sysmsg = str(captured["system_message"])
    assert "定时回访任务" in sysmsg
    assert "关心客户近况" in sysmsg
    assert "revisit_context" not in captured  # 不再有专有参数
    # 原生历史：传客户 inbound session_id（不手动读 transcript）
    from plugins.mxai.agents.hermes_agent import inbound_session_id

    assert captured["session_id"] == inbound_session_id("wechat", "cust_x")
    assert str(captured["session_id"]).startswith("mxai-wechat-inbound")


def test_llm_revisit_default_context_when_prompt_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def _fake_complete(profile_id: str, message: str, **kwargs):
        captured.update(kwargs)
        return {"text": "hi", "source": "agent_llm"}

    monkeypatch.setattr(
        "plugins.mxai.agents.hermes_agent.complete_profile_agent_reply", _fake_complete
    )
    llm_revisit_message("wechat", _cand(), revisit_prompt="")
    assert str(captured["system_message"]).strip()  # 空提示词回落默认，仍注入 system_message


def test_llm_revisit_none_on_generation_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.agents.hermes_agent.complete_profile_agent_reply",
        lambda *a, **k: None,
    )
    assert llm_revisit_message("wechat", _cand(), revisit_prompt="x") is None


def _seed_customer(data_dir, uid: str, last_inbound_at: str) -> None:
    import sqlite3

    from plugins.mxai.crm.storage.hub_repo import init_hub_schema

    db = mxai_db_path("hub.db", data_dir)
    init_hub_schema(db)
    conn = sqlite3.connect(db)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO wechat_contacts (customer_uid, display_name, "
            "source_channel, funnel_stage, funnel_stage_at, created_at, updated_at, last_inbound_at) "
            "VALUES (?, ?, 'wechat', 'consulting', ?, ?, ?, ?)",
            (uid, uid, last_inbound_at, last_inbound_at, last_inbound_at, last_inbound_at),
        )
        conn.commit()
    finally:
        conn.close()


def test_enqueue_llm_skips_candidate_on_generation_failure(tmp_path, monkeypatch) -> None:
    """入队分支：content_mode=llm 且生成失败 → 跳过候选（不入队、记 skipped_llm）."""
    from datetime import timedelta

    from plugins.mxai.scheduler.segmented_touch import run_segmented_scheduled_touch_enqueue
    from core.timeutil import utc_now

    t_2d = (utc_now() - timedelta(days=2)).replace(microsecond=0).isoformat()
    _seed_customer(tmp_path, "cust_2d", last_inbound_at=t_2d)
    monkeypatch.setattr(
        "plugins.mxai.scheduler.segmented_touch.llm_revisit_message", lambda *a, **k: None
    )
    cfg = normalize_scheduled_touch_config(
        {
            "enabled": True,
            "mode": "segmented",
            "content_mode": "llm",
            "revisit_prompt": "关心近况",
            "global_filters": {"max_enqueue_per_run": 30},
        }
    )
    result = run_segmented_scheduled_touch_enqueue("wechat", cfg, data_dir=tmp_path)
    assert result["content_mode"] == "llm"
    assert result["enqueued"] == 0
    assert "cust_2d" in result.get("skipped_llm", [])
