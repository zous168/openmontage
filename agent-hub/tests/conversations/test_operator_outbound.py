"""人工接管出站：send_operator_message 六渠道."""

from plugins.mxai.conversations.outbound import send_operator_message


def test_public_manual_outbound_mock(mxai_env) -> None:
    del mxai_env
    result = send_operator_message("douyin", "lead_a", "您好，人工跟进")
    assert result.get("sent") is True
    assert result.get("mode") == "mock"


def test_boss_manual_outbound_mock(mxai_env) -> None:
    del mxai_env
    result = send_operator_message("boss", "cand_01", "方便明天面试吗")
    assert result.get("sent") is True


def test_empty_message_rejected(mxai_env) -> None:
    del mxai_env
    result = send_operator_message("douyin", "lead_a", "   ")
    assert result.get("sent") is False
