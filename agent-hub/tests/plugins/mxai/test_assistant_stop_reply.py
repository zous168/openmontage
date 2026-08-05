"""停止生成文案与 stop 优先于 unavailable（FR-CHAT-07 bugfix）。"""

from __future__ import annotations

from plugins.mxai.agents.assistant import _stopped_reply_text


def test_stopped_reply_text():
    assert _stopped_reply_text(reverted=False) == "已停止更改"
    assert _stopped_reply_text(reverted=True) == "已停止更改，配置已恢复为更改前。"


def test_stop_assistant_turn_unknown_returns_reply_text():
    from plugins.mxai.agents.assistant import stop_assistant_turn

    res = stop_assistant_turn("turn_does_not_exist")
    assert res["ok"] is True
    assert res["reply_text"] == "已停止更改"


def test_persist_stop_skips_user(monkeypatch):
    """停止落库不得再 append user（否则 transcript 尾部叠双份你好啊）."""
    from plugins.mxai.agents import assistant as mod

    calls = []

    def _fake_record(profile_id, recipient, user_message, assistant_message, **kw):
        calls.append({"user": user_message, "assistant": assistant_message})

    monkeypatch.setattr(mod, "ensure_assistant_channel_session", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "plugins.mxai.agents.hermes_agent.record_inbound_turn",
        _fake_record,
    )
    mod._persist_assistant_turn("你好啊", "已停止更改", include_user=False)
    assert len(calls) == 1
    assert calls[0]["user"] == ""
    assert calls[0]["assistant"] == "已停止更改"
