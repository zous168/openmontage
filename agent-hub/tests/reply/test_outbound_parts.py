"""出站多气泡拆分。"""

from __future__ import annotations

from plugins.mxai.agents.outbound_parts import (
    attach_outbound_parts,
    outbound_parts_from_reply,
    split_reply_parts,
)


def test_split_reply_parts_single() -> None:
    assert split_reply_parts("你好呀") == ["你好呀"]
    assert split_reply_parts("") == []


def test_split_reply_parts_multi() -> None:
    text = "先说这句\n---\n再说这句\n---\n最后一句"
    assert split_reply_parts(text) == ["先说这句", "再说这句", "最后一句"]


def test_attach_outbound_parts_strips_delimiter_from_text() -> None:
    out = attach_outbound_parts(
        {"text": "A\n---\nB", "source": "agent_llm"}
    )
    assert out["parts"] == ["A", "B"]
    assert out["text"] == "A\n\nB"
    assert "---" not in out["text"]


def test_attach_outbound_parts_strips_markdown() -> None:
    out = attach_outbound_parts(
        {
            "text": "## 优惠\n\n这是 **限时** 活动\n\n---\n\n留个微信？",
            "source": "faq",
        }
    )
    assert out["parts"] == ["优惠\n\n这是 限时 活动", "留个微信？"]
    assert "**" not in out["text"]
    assert "##" not in out["text"]


def test_attach_outbound_parts_idempotent_keeps_parts() -> None:
    first = attach_outbound_parts({"text": "A\n---\nB", "source": "agent_llm"})
    second = attach_outbound_parts(first)
    assert second["parts"] == ["A", "B"]
    assert second["text"] == "A\n\nB"


def test_outbound_parts_from_reply_prefers_parts() -> None:
    assert outbound_parts_from_reply({"parts": ["x", "y"], "text": "ignored"}) == [
        "x",
        "y",
    ]


def test_no_reply_has_empty_parts() -> None:
    out = attach_outbound_parts({"text": "", "source": "no_reply"})
    assert out["parts"] == []
