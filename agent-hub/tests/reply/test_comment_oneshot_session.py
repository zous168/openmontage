"""评论智能体 one-shot ephemeral 会话隔离."""

from __future__ import annotations

from typing import Any

import pytest

from plugins.mxai.agents.session_ephemeral import (
    COMMENT_ONESHOT_AGENT_IDS,
    alloc_ephemeral_session,
    needs_oneshot_session,
    wrap_oneshot_session,
)


def test_needs_oneshot_by_feature_and_profile() -> None:
    assert needs_oneshot_session(
        binding_feature="comment_reply", hermes_profile="wechat_chat"
    )
    assert needs_oneshot_session(
        binding_feature="first_comment", hermes_profile="wechat_chat"
    )
    for pid in COMMENT_ONESHOT_AGENT_IDS:
        assert needs_oneshot_session(binding_feature="inbound_reply", hermes_profile=pid)
    assert not needs_oneshot_session(
        binding_feature="inbound_reply", hermes_profile="wechat_chat"
    )
    assert not needs_oneshot_session(
        binding_feature="inbound_reply", hermes_profile="boss_dm"
    )


def test_alloc_ephemeral_session_shape() -> None:
    sid, skey = alloc_ephemeral_session("douyin_comment")
    assert sid.startswith("mxai-douyin_comment-ephemeral-")
    assert skey.startswith("agent:douyin_comment:ephemeral:")
    assert "inbound" not in sid


def test_wrap_oneshot_respects_caller_session() -> None:
    out = wrap_oneshot_session(
        "douyin_comment",
        binding_feature="comment_reply",
        session_id="mxai-douyin_comment-ephemeral-fixed",
        session_key="agent:douyin_comment:ephemeral:fixed",
        persist_session=True,
    )
    assert out["ephemeral_sid"] is None
    assert out["session_id"] == "mxai-douyin_comment-ephemeral-fixed"
    assert out["persist_session"] is True


def test_resolve_reply_comment_uses_ephemeral_and_deletes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugins.mxai.agents import pipeline

    seen: dict[str, Any] = {}
    deleted: list[str] = []

    def fake_complete(
        profile_id: str,
        message: str,
        *,
        recipient: str = "",
        session_id: str | None = None,
        session_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        seen["profile_id"] = profile_id
        seen["session_id"] = session_id
        seen["session_key"] = session_key
        return {"source": "agent_llm", "text": "欢迎了解～"}

    monkeypatch.setattr(pipeline, "_complete_inbound_llm", fake_complete)
    monkeypatch.setattr(pipeline, "_match_sensitive", lambda *_a, **_k: None)
    monkeypatch.setattr(pipeline, "_read_reply_mode", lambda: "llm_unified")
    monkeypatch.setattr(
        "plugins.mxai.agents.session_ephemeral.delete_ephemeral_session",
        lambda profile, sid: deleted.append(sid),
    )
    monkeypatch.setattr(
        "plugins.mxai.crm.customer_inbound.touch_last_inbound",
        lambda *a, **k: None,
    )

    result = pipeline.resolve_reply(
        "douyin_comment",
        "怎么联系",
        recipient="作者A",
        binding_feature="comment_reply",
        bypass_faq=True,
        bypass_kb=True,
    )
    assert result.get("text") == "欢迎了解～"
    assert "ephemeral" in str(seen.get("session_id") or "")
    assert "inbound" not in str(seen.get("session_id") or "")
    assert deleted == [seen["session_id"]]


def test_resolve_reply_wechat_keeps_sticky_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugins.mxai.agents import pipeline

    seen: dict[str, Any] = {}
    deleted: list[str] = []

    def fake_complete(
        profile_id: str,
        message: str,
        *,
        session_id: str | None = None,
        session_key: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        seen["session_id"] = session_id
        seen["session_key"] = session_key
        return {"source": "agent_llm", "text": "在的"}

    monkeypatch.setattr(pipeline, "_complete_inbound_llm", fake_complete)
    monkeypatch.setattr(pipeline, "_match_sensitive", lambda *_a, **_k: None)
    monkeypatch.setattr(pipeline, "_read_reply_mode", lambda: "llm_unified")
    monkeypatch.setattr(
        "plugins.mxai.agents.session_ephemeral.delete_ephemeral_session",
        lambda profile, sid: deleted.append(sid),
    )
    monkeypatch.setattr(
        "plugins.mxai.crm.customer_inbound.touch_last_inbound",
        lambda *a, **k: None,
    )

    pipeline.resolve_reply(
        "wechat_chat",
        "在吗",
        recipient="客户A",
        binding_feature="inbound_reply",
        bypass_faq=True,
        bypass_kb=True,
    )
    # 未显式传 sid 时由 hermes_agent 派生 sticky inbound；此处应保持 None
    assert seen.get("session_id") is None
    assert deleted == []
