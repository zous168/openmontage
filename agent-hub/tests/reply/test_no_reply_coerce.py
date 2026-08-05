"""[NO_REPLY] 规范化与出站跳过判定。"""

from __future__ import annotations

from plugins.mxai.agents.pipeline import coerce_no_reply_result, is_no_reply_text
from plugins.mxai.orchestrator.models import Task
from plugins.mxai.orchestrator.queue_manager import _should_skip_outbound_after_hub_reply


def test_is_no_reply_text_exact_only() -> None:
    assert is_no_reply_text("[NO_REPLY]")
    assert is_no_reply_text("  [NO_REPLY]  ")
    assert not is_no_reply_text("你好 [NO_REPLY]")
    assert not is_no_reply_text("无法遵守")


def test_coerce_no_reply_result() -> None:
    out = coerce_no_reply_result({"text": "[NO_REPLY]", "source": "agent_llm"})
    assert out["text"] == ""
    assert out["source"] == "no_reply"
    assert out["no_reply"] is True


def test_should_skip_outbound_after_hub_reply() -> None:
    t = Task(
        task_id="t1",
        profile_id="wechat",
        task_type="inbound_reply",
        name="x",
        payload={"hub_reply": {"text": "", "source": "no_reply"}},
    )
    assert _should_skip_outbound_after_hub_reply(t) is True
    t.payload["hub_reply"] = {"text": "你好", "source": "agent_llm"}
    assert _should_skip_outbound_after_hub_reply(t) is False
