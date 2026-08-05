"""CR-119 / LT-034.01.4：AI 调试会话启动清扫（机制 B 临时态核心）.

覆盖：
- ``sweep_debug_sessions`` 删除单库全部遗留 ``mxai-%-debug-%`` 调试会话，
  真实 ``mxai-%-inbound-%`` 会话**仍在且消息数不变**（隔离/零污染）；
- 空库 / 缺库 no-op；
- 不带 db_path 时遍历各渠道 profile 库并汇总（LT-031 per-profile 隔离）。

记忆键说明：mxai 客户记忆为方案甲 transcript-only（无独立 MemoryProvider），
``agent:%:debug:%`` 键无独立落库——删除 debug **会话**（连带 transcript/messages）即彻底
清理，故本测仅断言会话被删（no-op 删键，见 session_retention 模块注释）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.agents import hermes_agent as ha
from plugins.mxai.scheduler import session_retention as sr


@pytest.fixture
def open_db():
    """打开一个独立 SessionDB 连接做断言（与 record_*_turn 各自开关的连接隔离，
    避免 sweep 内部 ``db.close()`` 误关断言连接）。"""
    from hermes_state import SessionDB

    opened: list = []

    def _open(path: Path):
        db = SessionDB(db_path=path)
        opened.append(db)
        return db

    yield _open
    for db in opened:
        db.close()


def _patch_profile_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """把 ``get_profile_dir`` 指向临时目录——record_*_turn 经此落各自 per-profile 库
    （真实写路径，非 monkeypatch 单一 DB 实例）。"""
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: tmp_path / "profiles" / name,
    )


def _profile_db_path(tmp_path: Path, profile: str) -> Path:
    return tmp_path / "profiles" / profile / "state.db"


def test_sweep_deletes_debug_keeps_real_inbound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, open_db
) -> None:
    _patch_profile_dir(monkeypatch, tmp_path)
    profile = "douyin"

    # 1 个真实 inbound 会话（写 user+assistant 两条）+ 2 个调试会话（不同 token）。
    # record_*_turn 各自开关其内部 SessionDB（真实路径），与下方断言连接隔离。
    ha.record_inbound_turn(profile, "customer-uid-1", "你好", "您好，请问需要什么帮助")
    ha.record_debug_turn(profile, "tokenA", "测试问题A", "回答A")
    ha.record_debug_turn(profile, "tokenB", "测试问题B", "回答B")

    inbound_sid = ha.inbound_session_id(profile, "customer-uid-1")
    debug_a = ha.debug_session_id(profile, "tokenA")
    debug_b = ha.debug_session_id(profile, "tokenB")
    db_path = _profile_db_path(tmp_path, profile)

    # 前置自检：三会话都在，inbound 两条消息
    pre = open_db(db_path)
    assert pre.get_session(inbound_sid) is not None
    assert pre.get_session(debug_a) is not None
    assert pre.get_session(debug_b) is not None
    inbound_msg_count = len(pre.get_messages(inbound_sid))
    assert inbound_msg_count == 2

    result = sr.sweep_debug_sessions(db_path=db_path)

    assert result["ok"] is True
    assert result["scanned"] == 2
    assert result["deleted"] == 2
    assert result["errors"] == 0

    # 用新连接断言清扫结果（sweep 已关其自身连接）
    post = open_db(db_path)
    assert post.get_session(debug_a) is None
    assert post.get_session(debug_b) is None
    # 真实 inbound 会话仍在且消息数不变
    assert post.get_session(inbound_sid) is not None
    assert len(post.get_messages(inbound_sid)) == inbound_msg_count


def test_sweep_empty_db_is_noop(tmp_path: Path) -> None:
    result = sr.sweep_debug_sessions(db_path=tmp_path / "missing.db")
    assert result == {"ok": True, "scanned": 0, "deleted": 0, "errors": 0}


def test_sweep_no_debug_sessions_is_noop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, open_db
) -> None:
    _patch_profile_dir(monkeypatch, tmp_path)
    # 仅真实 inbound，无调试会话
    ha.record_inbound_turn("wechat", "cust-x", "在吗", "在的")
    db_path = _profile_db_path(tmp_path, "wechat")

    result = sr.sweep_debug_sessions(db_path=db_path)

    assert result == {"ok": True, "scanned": 0, "deleted": 0, "errors": 0}
    assert open_db(db_path).get_session(ha.inbound_session_id("wechat", "cust-x")) is not None


def test_sweep_traverses_all_profile_dbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """不带 db_path 时遍历各渠道 profile 的 state.db 并汇总（LT-031 per-profile 隔离）。"""
    from hermes_state import SessionDB

    def _fake_profile_dir(name: str) -> Path:
        return tmp_path / "profiles" / name

    monkeypatch.setattr("hermes_cli.profiles.get_profile_dir", _fake_profile_dir)

    douyin_db = SessionDB(db_path=_fake_profile_dir("douyin") / "state.db")
    wechat_db = SessionDB(db_path=_fake_profile_dir("wechat") / "state.db")
    try:
        # douyin: 1 真实 inbound + 1 调试；wechat: 1 调试。
        douyin_inbound = "mxai-douyin-inbound-keepme00000000"
        douyin_db.ensure_session(douyin_inbound, "agent_reply", user_id="cust-a")
        douyin_db.append_message(douyin_inbound, "user", "hi")

        douyin_debug = ha.debug_session_id("douyin", "tk1")
        douyin_db.ensure_session(douyin_debug, "api_server", user_id=None)
        douyin_db.append_message(douyin_debug, "user", "dbg")

        wechat_debug = ha.debug_session_id("wechat", "tk2")
        wechat_db.ensure_session(wechat_debug, "api_server", user_id=None)
        wechat_db.append_message(wechat_debug, "user", "dbg2")

        result = sr.sweep_debug_sessions()

        assert result["ok"] is True
        assert result["scanned"] == 2
        assert result["deleted"] == 2
        assert result["errors"] == 0

        # 调试会话两库各被清；真实 inbound 留存
        assert douyin_db.get_session(douyin_debug) is None
        assert wechat_db.get_session(wechat_debug) is None
        assert douyin_db.get_session(douyin_inbound) is not None
    finally:
        douyin_db.close()
        wechat_db.close()
