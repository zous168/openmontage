"""CR-157 配对与易变门禁单测。"""

from __future__ import annotations

from plugins.mxai.train_ai.pairs import pair_messages
from plugins.mxai.train_ai.volatile import ERROR_CODE, check_volatile_content


def _row(i: int, role: str, content: str = "", tool_name: str = "") -> dict:
    return {"id": i, "role": role, "content": content, "tool_name": tool_name, "timestamp": i}


def test_pair_one_to_one_adjacent() -> None:
    rows = [
        _row(1, "user", "你好"),
        _row(2, "assistant", "您好"),
        _row(3, "user", "营业时间？"),
        _row(4, "assistant", "朝九晚六"),
    ]
    pairs = pair_messages(rows)
    assert len(pairs) == 2
    assert pairs[0]["question"] == "你好"
    assert pairs[0]["answer"] == "您好"
    assert pairs[1]["user_message_id"] == "3"


def test_pair_forbid_q1_to_a3() -> None:
    rows = [
        _row(1, "user", "Q1"),
        _row(2, "user", "Q2"),
        _row(3, "assistant", "A"),
    ]
    pairs = pair_messages(rows)
    assert len(pairs) == 1
    assert pairs[0]["question"] == "Q2"


def test_pair_first_assistant_only() -> None:
    rows = [
        _row(1, "user", "Q"),
        _row(2, "assistant", "A1"),
        _row(3, "assistant", "A2"),
    ]
    pairs = pair_messages(rows)
    assert len(pairs) == 1
    assert pairs[0]["answer"] == "A1"


def test_pair_exclude_takeover_interval() -> None:
    rows = [
        _row(1, "user", "人工前"),
        _row(2, "assistant", "AI答"),
        _row(3, "tool", "[takeover]", tool_name="takeover"),
        _row(4, "user", "接管中问"),
        _row(5, "assistant", "人工答"),
        _row(6, "tool", "[release]", tool_name="release"),
        _row(7, "user", "释放后"),
        _row(8, "assistant", "AI再答"),
    ]
    pairs = pair_messages(rows)
    qs = {p["question"] for p in pairs}
    assert "人工前" in qs
    assert "释放后" in qs
    assert "接管中问" not in qs


def test_volatile_price() -> None:
    assert check_volatile_content("现在只要 99 元") == ERROR_CODE
    assert check_volatile_content("欢迎咨询产品介绍") is None


def test_match_threshold_default(tmp_path) -> None:
    from plugins.mxai.train_ai.store import DEFAULT_MATCH_THRESHOLD, get_match_threshold

    assert get_match_threshold(data_dir=tmp_path) == DEFAULT_MATCH_THRESHOLD


def test_parse_refine_json_plain() -> None:
    from plugins.mxai.train_ai.faq_sync import _parse_refine_json

    q, a = _parse_refine_json('{"question":"营业时间？","answer":"朝九晚六"}')
    assert q == "营业时间？"
    assert a == "朝九晚六"


def test_parse_refine_json_fenced() -> None:
    from plugins.mxai.train_ai.faq_sync import _parse_refine_json

    raw = '```json\n{"question":"如何退货？","answer":"订单详情申请售后"}\n```'
    q, a = _parse_refine_json(raw)
    assert q == "如何退货？"
    assert a == "订单详情申请售后"


def test_refine_qa_one_shot(monkeypatch) -> None:
    from plugins.mxai.train_ai import faq_sync

    def _fake(_system: str, _user: str) -> str:
        return '{"question":"店铺几点开门？","answer":"工作日上午九点到下午六点营业。"}'

    monkeypatch.setattr(faq_sync, "_call_refine_llm", _fake)
    q, a = faq_sync.refine_qa("你们店几点开门啊？", "我们工作日上午九点到下午六点营业。")
    assert q == "店铺几点开门？"
    assert "九点" in a


def test_personal_pat_allows_order_detail() -> None:
    """「订单详情」不得误判为个性化订单号。"""
    from plugins.mxai.train_ai.faq_sync import _PERSONAL_PAT

    assert _PERSONAL_PAT.search("请在订单详情申请售后") is None
    assert _PERSONAL_PAT.search("订单号：ABC123") is not None
