"""会话消息：客户发现 / transcript / 模式态均走 Hermes SessionDB（LT-031 / CR-159）."""

from plugins.mxai.cfg.agent_bindings import inbound_session_profile
from plugins.mxai.conversations.service import (
    _parse_reply_op_object,
    get_conversation_mode,
    list_conversations,
    list_messages,
    set_conversation_mode,
)
from plugins.mxai.worklog.service import append_worklog


def _hp(channel: str) -> str:
    """生产写侧口径：SessionDB 落 inbound_reply 绑定的业务 Agent."""
    return inbound_session_profile(channel)


def test_parse_reply_op_object() -> None:
    peer, q, a = _parse_reply_op_object(
        "mock_qiyeweixin_xjeq · 问:产品多少钱 · 答:感谢咨询，请查看手册"
    )
    assert peer == "mock_qiyeweixin_xjeq"
    assert q == "产品多少钱"
    assert a == "感谢咨询，请查看手册"


def test_list_messages_reads_session_transcript(mxai_env) -> None:
    """transcript 来源 = Hermes SessionDB；列表入参仍为 channel."""
    del mxai_env
    from plugins.mxai.agents.hermes_agent import record_inbound_turn

    record_inbound_turn(_hp("qiyeweixin"), "mock_peer_a", "在吗", "您好，有什么可以帮您？")

    convs = list_conversations("qiyeweixin")
    assert any(c["id"] == "C-mock_peer_a" and c["name"] == "mock_peer_a" for c in convs)
    assert any(c["id"] == "C-mock_peer_a" and c.get("channel") == "qiyeweixin" for c in convs)
    msgs = list_messages("qiyeweixin", "C-mock_peer_a")
    assert len(msgs) == 2
    assert msgs[0]["from"] == "user"
    assert msgs[0]["text"] == "在吗"
    assert msgs[1]["from"] == "ai"
    assert "帮您" in msgs[1]["text"]


def test_list_messages_ignores_worklog_as_transcript(mxai_env) -> None:
    """仅 worklog（无 SessionDB 写入）时 transcript 为空：worklog ≠ 对话来源."""
    del mxai_env
    append_worklog(
        profile_id="qiyeweixin",
        op_type="inbound_reply",
        exec_status="成功",
        op_object="mock_peer_wlonly · 问:价格 · 答:请留资",
    )
    msgs = list_messages("qiyeweixin", "C-mock_peer_wlonly")
    assert msgs == []


def test_list_messages_restores_takeover_marker(mxai_env) -> None:
    """接管 marker（role=tool/takeover）还原为系统提示气泡（from=system, kind=takeover）."""
    del mxai_env
    from plugins.mxai.agents.hermes_agent import (
        record_inbound_turn,
        record_operator_message,
        record_takeover_marker,
    )

    peer = "mock_peer_takeover"
    hp = _hp("qiyeweixin")
    record_inbound_turn(hp, peer, "在吗", "您好")
    record_takeover_marker(hp, peer, operator="坐席小王")
    record_operator_message(hp, peer, "人工报价 199")

    msgs = list_messages("qiyeweixin", f"C-{peer}")
    markers = [m for m in msgs if m.get("kind") == "takeover"]
    assert len(markers) == 1
    assert markers[0]["from"] == "system"
    assert "[takeover]" in markers[0]["text"]
    assert any(m.get("from") == "ai" and m.get("text") == "人工报价 199" for m in msgs)
    assert msgs.index(markers[0]) < next(
        i for i, m in enumerate(msgs) if m.get("text") == "人工报价 199"
    )


def test_record_inbound_user_writes_session(mxai_env) -> None:
    """接管态客户入站经 record_inbound_user 落 SessionDB（role=user 同客户 session）."""
    del mxai_env
    from plugins.mxai.agents.hermes_agent import record_inbound_user

    peer = "mock_peer_takeover_in"
    record_inbound_user(_hp("qiyeweixin"), peer, "接管期间的新问题")
    msgs = list_messages("qiyeweixin", f"C-{peer}")
    assert len(msgs) == 1
    assert msgs[0]["from"] == "user"
    assert msgs[0]["text"] == "接管期间的新问题"


def test_takeover_inbound_transcript_from_session_only(mxai_env) -> None:
    """接管态入站气泡仅靠 SessionDB 即返回完整 transcript."""
    del mxai_env
    from plugins.mxai.agents.hermes_agent import (
        record_inbound_turn,
        record_inbound_user,
        record_operator_message,
        record_takeover_marker,
    )

    peer = "mock_peer_full_takeover"
    hp = _hp("qiyeweixin")
    record_inbound_turn(hp, peer, "在吗", "您好")
    record_takeover_marker(hp, peer, operator="坐席小李")
    record_inbound_user(hp, peer, "接管期间客户追问")
    record_operator_message(hp, peer, "人工回复 OK")

    msgs = list_messages("qiyeweixin", f"C-{peer}")
    assert [m.get("from") for m in msgs] == ["user", "ai", "system", "user", "ai"]
    assert msgs[3]["text"] == "接管期间客户追问"
    assert msgs[2].get("kind") == "takeover"
    assert msgs[4]["text"] == "人工回复 OK"


def test_set_conversation_mode_roundtrip_via_session(mxai_env) -> None:
    """模式态纯由 SessionDB takeover/release marker 还原（无 cache）：takeover→release→auto."""
    del mxai_env
    peer = "peer_mode_x"
    cid = f"C-{peer}"
    assert get_conversation_mode("wechat", cid) == "auto"
    set_conversation_mode("wechat", cid, "takeover")
    assert get_conversation_mode("wechat", cid) == "takeover"
    set_conversation_mode("wechat", cid, "auto")
    assert get_conversation_mode("wechat", cid) == "auto"


def test_set_conversation_mode_normalizes_legacy_id(mxai_env) -> None:
    """旧版含 ·问:·答: 的 conv_id 仍能归一到 peer，并经 marker 切换模式态."""
    del mxai_env
    legacy_id = "C-peer_x · 问:你好 · 答:您好"
    set_conversation_mode("wechat", legacy_id, "takeover")
    assert get_conversation_mode("wechat", "C-peer_x") == "takeover"


def test_list_conversations_one_per_customer(mxai_env) -> None:
    """同一客户多轮 inbound → SessionDB 一个 session → 列表一条，预览取最新客户消息."""
    del mxai_env
    from plugins.mxai.agents.hermes_agent import record_inbound_turn

    hp = _hp("qiyeweixin")
    record_inbound_turn(hp, "mock_peer_b", "价格", "请留资")
    record_inbound_turn(hp, "mock_peer_b", "还有优惠吗", "有的")
    convs = list_conversations("qiyeweixin")
    ids = [c["id"] for c in convs if c["name"] == "mock_peer_b"]
    assert ids == ["C-mock_peer_b"]
    row = next(c for c in convs if c["id"] == "C-mock_peer_b")
    assert "还有优惠吗" in row["last"]
    assert row.get("time") is not None


def test_conversation_name_is_customer_uid(mxai_env) -> None:
    """会话名取 SessionDB user_id（customer_uid），非 worklog op_object 解析."""
    del mxai_env
    from plugins.mxai.agents.hermes_agent import record_inbound_turn

    record_inbound_turn(_hp("qiyeweixin"), "ww_user_3", "价格多少", "请留资")
    convs = list_conversations("qiyeweixin")
    row = next(c for c in convs if c["id"] == "C-ww_user_3")
    assert row["name"] == "ww_user_3"
    assert "价格多少" in row["last"]
    assert row.get("channel") == "qiyeweixin"


def test_list_messages_from_dm_session(mxai_env) -> None:
    """公域 channel：发现 + transcript 均取默认绑定 Agent SessionDB."""
    del mxai_env
    from plugins.mxai.agents.hermes_agent import record_inbound_turn

    record_inbound_turn(_hp("douyin"), "lead_dy_1", "多少钱", "请留联系方式")
    convs = list_conversations("douyin")
    assert any(c["id"] == "C-lead_dy_1" for c in convs)
    msgs = list_messages("douyin", "C-lead_dy_1")
    assert len(msgs) == 2
    assert msgs[0]["text"] == "多少钱"


def test_boss_recruit_conversation(mxai_env) -> None:
    """boss 渠道客户从 SessionDB 发现（非 worklog）."""
    del mxai_env
    from plugins.mxai.agents.hermes_agent import record_inbound_turn

    record_inbound_turn(_hp("boss"), "cand_boss_1", "薪资多少", "15-20K")
    convs = list_conversations("boss")
    assert any(c["id"] == "C-cand_boss_1" for c in convs)


def test_operator_message_and_mode_via_session(mxai_env) -> None:
    """坐席出站全程纯 SessionDB：takeover marker 置接管态，出站还原为 ai 气泡."""
    del mxai_env
    from plugins.mxai.agents.hermes_agent import record_operator_message

    set_conversation_mode("douyin", "C-peer_op", "takeover")
    record_operator_message(_hp("douyin"), "peer_op", "人工报价")
    assert get_conversation_mode("douyin", "C-peer_op") == "takeover"
    msgs = list_messages("douyin", "C-peer_op")
    assert any(m.get("from") == "ai" and m.get("text") == "人工报价" for m in msgs)
