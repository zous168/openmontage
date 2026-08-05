"""m0013 · 旧 channel state.db inbound → 业务 Agent."""

from __future__ import annotations

from pathlib import Path

from plugins.mxai.agents.hermes_agent import (
    _ensure_inbound_session,
    inbound_session_id,
    record_inbound_turn,
)
from plugins.mxai.cfg.agent_bindings import AGENT_QIYEWEIXIN_CHAT, inbound_session_profile
from plugins.mxai.cfg.migrations.m0013_channel_inbound_sessions_to_agent import MIGRATION
from plugins.mxai.conversations.service import list_conversations, list_messages
from hermes_state import SessionDB


def test_m0013_migrates_from_live_channel_state_db(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: data_dir / "profiles" / name,
    )

    channel = "qiyeweixin"
    hermes = inbound_session_profile(channel)
    assert hermes == AGENT_QIYEWEIXIN_CHAT

    # 旧渠道库写一轮问答
    src_dir = data_dir / "profiles" / channel
    src_dir.mkdir(parents=True)
    src = SessionDB(db_path=src_dir / "state.db")
    try:
        peer = "legacy_peer_1"
        sid = inbound_session_id(channel, peer)
        _ensure_inbound_session(src, sid, peer)
        src.append_message(sid, "user", "旧库问")
        src.append_message(sid, "assistant", "旧库答")
    finally:
        src.close()

    # 业务 Agent 目录占位（无会话）
    (data_dir / "profiles" / hermes).mkdir(parents=True)

    cfg = data_dir / "plugins" / "mxai" / "cfg" / channel
    cfg.mkdir(parents=True)
    (cfg / "workbench.yaml").write_text(
        "agent_bindings:\n  default: qiyeweixin_chat\n  modules:\n    inbound_reply: qiyeweixin_chat\n",
        encoding="utf-8",
    )

    n = MIGRATION.apply(data_dir)
    assert n >= 1

    # 再跑幂等
    assert MIGRATION.apply(data_dir) == 0

    # list 经 channel 可见迁入内容
    convs = list_conversations(channel)
    assert any(c["id"] == "C-legacy_peer_1" for c in convs)
    msgs = list_messages(channel, "C-legacy_peer_1")
    assert any(m.get("text") == "旧库问" for m in msgs)
    assert any(m.get("text") == "旧库答" for m in msgs)


def test_m0013_skips_when_dest_already_has_messages(tmp_path: Path, monkeypatch) -> None:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: data_dir / "profiles" / name,
    )

    channel = "qiyeweixin"
    hermes = AGENT_QIYEWEIXIN_CHAT
    peer = "already_there"

    src_dir = data_dir / "profiles" / channel
    src_dir.mkdir(parents=True)
    src = SessionDB(db_path=src_dir / "state.db")
    try:
        sid = inbound_session_id(channel, peer)
        _ensure_inbound_session(src, sid, peer)
        src.append_message(sid, "user", "源侧")
        src.append_message(sid, "assistant", "源答")
    finally:
        src.close()

    record_inbound_turn(hermes, peer, "新侧问", "新侧答")

    cfg = data_dir / "plugins" / "mxai" / "cfg" / channel
    cfg.mkdir(parents=True)
    (cfg / "workbench.yaml").write_text(
        "agent_bindings:\n  default: qiyeweixin_chat\n  modules:\n    inbound_reply: qiyeweixin_chat\n",
        encoding="utf-8",
    )

    assert MIGRATION.apply(data_dir) == 0
    msgs = list_messages(channel, f"C-{peer}")
    texts = [m.get("text") for m in msgs]
    assert "新侧问" in texts
    assert "源侧" not in texts
