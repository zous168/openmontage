"""AI 调试会话基元（CR-119 / LT-034.01.1）：隔离命名族 + 独立记忆键 + 只读 seed."""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.agents import hermes_agent


@pytest.fixture
def debug_profile(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """隔离 profile：把 ``get_profile_dir`` 指向临时目录，避免污染真实 state.db。

    ``_profile_session_db`` lazy-import ``hermes_cli.profiles.get_profile_dir``，
    monkeypatch 该属性即可让本测试的所有 SessionDB 落到 ``tmp_path/profiles/{id}``。
    """
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profiles / name,
    )
    return "douyin"


def test_debug_session_id_distinct_from_inbound(debug_profile: str) -> None:
    pid = debug_profile
    sid = hermes_agent.debug_session_id(pid, "tok-1")
    assert "-debug-" in sid
    # 同 token 稳定
    assert sid == hermes_agent.debug_session_id(pid, "tok-1")
    # 与同参 inbound id 不相等（命名族区分）
    assert sid != hermes_agent.inbound_session_id(pid, "tok-1")


def test_debug_session_key_distinct_from_inbound(debug_profile: str) -> None:
    pid = debug_profile
    key = hermes_agent.debug_session_key(pid, "tok-1")
    assert key.startswith("agent:")
    assert ":debug:" in key
    assert key != hermes_agent.inbound_session_key(pid, "tok-1")


def test_record_debug_turn_writes_user_assistant_with_null_user_id(
    debug_profile: str,
) -> None:
    pid = debug_profile
    token = "tok-debug"
    hermes_agent.record_debug_turn(pid, token, "你们有优惠吗", "本月满减 9 折。")

    sid = hermes_agent.debug_session_id(pid, token)
    db = hermes_agent._profile_session_db(pid)
    try:
        session = db.get_session(sid)
        assert session is not None
        # 调试会话刻意不写 customer_uid → 客户发现天然排除
        assert session["user_id"] is None
        messages = db.get_messages(sid)
        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant"]
        assert messages[0]["content"] == "你们有优惠吗"
        assert messages[1]["content"] == "本月满减 9 折。"
    finally:
        db.close()


def test_seed_debug_from_customer_is_readonly_copy(debug_profile: str) -> None:
    pid = debug_profile
    customer_uid = "cust-7788"
    token = "tok-seed"

    # 造一个真实客户 inbound 会话（2 轮 = 4 条 user/assistant）
    hermes_agent.record_inbound_turn(pid, customer_uid, "在吗", "在的，请讲。")
    hermes_agent.record_inbound_turn(pid, customer_uid, "多少钱", "99 元。")

    src_sid = hermes_agent.inbound_session_id(pid, customer_uid)
    db = hermes_agent._profile_session_db(pid)
    try:
        before = len(db.get_messages(src_sid))
    finally:
        db.close()
    assert before == 4

    seeded = hermes_agent.seed_debug_from_customer(pid, customer_uid, token)
    assert seeded > 0

    dst_sid = hermes_agent.debug_session_id(pid, token)
    db = hermes_agent._profile_session_db(pid)
    try:
        dst_messages = db.get_messages(dst_sid)
        # debug 会话含被复制内容
        assert [m["content"] for m in dst_messages] == [
            "在吗",
            "在的，请讲。",
            "多少钱",
            "99 元。",
        ]
        # 只读断言：真实 inbound 会话消息数不变
        assert len(db.get_messages(src_sid)) == before
        # seed 进的会话同样 user_id 为 None（仍是调试态）
        assert db.get_session(dst_sid)["user_id"] is None
    finally:
        db.close()


def test_seed_debug_from_missing_customer_returns_zero(debug_profile: str) -> None:
    pid = debug_profile
    seeded = hermes_agent.seed_debug_from_customer(pid, "no-such-customer", "tok-x")
    assert seeded == 0
