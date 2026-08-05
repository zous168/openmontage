"""A-Main 会话历史：Hermes SessionDB（assistant Profile）."""

from __future__ import annotations

import json

from plugins.mxai.agents.assistant import (
    ASSISTANT_CHANNEL_CLAWBOT,
    ASSISTANT_CHANNEL_FLOATING,
    ASSISTANT_CHANNEL_WECOM,
    HERMES_ASSISTANT_PROFILE,
    assistant_channel_session_id,
    assistant_inbound_session_id,
    assistant_inbound_session_key,
)
from plugins.mxai.agents.service import (
    _sanitize_transcript_text,
    add_favorite,
    clear_history,
    export_commands,
    list_favorites,
    list_history,
    list_unified_transcript,
    remove_favorite,
)


def _seed_assistant_transcript(mxai_env) -> None:
    from hermes_state import SessionDB

    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    db_path = mxai_env / "profiles" / "assistant" / "state.db"
    db = SessionDB(db_path=db_path)
    try:
        db.create_session(sid, source=ASSISTANT_CHANNEL_FLOATING)
        db.append_message(sid, "user", "启动抖音评论抓取")
        db.append_message(sid, "assistant", "已为您启动抖音评论采集任务。")
    finally:
        db.close()


def test_list_history_from_session_db(mxai_env) -> None:
    _seed_assistant_transcript(mxai_env)
    items = list_history(limit=10)
    assert len(items) == 1
    assert items[0]["message"] == "启动抖音评论抓取"
    assert "抖音" in items[0]["reply"]
    assert items[0]["agent"] == "assistant"
    assert items[0]["session_id"] == assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)


def test_clear_history_deletes_floating_session(mxai_env) -> None:
    from hermes_state import SessionDB

    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    db = SessionDB(db_path=mxai_env / "profiles" / "assistant" / "state.db")
    try:
        db.create_session(sid, ASSISTANT_CHANNEL_FLOATING)
        db.append_message(sid, "user", "web only")
        db.append_message(sid, "assistant", "ok")
    finally:
        db.close()

    cleared = clear_history()
    assert cleared == 1
    assert len(list_history()) == 0


def test_export_commands_includes_hermes_profile(mxai_env) -> None:
    _seed_assistant_transcript(mxai_env)
    add_favorite("导出本周报表")
    payload = export_commands()
    assert payload["hermes_profile"] == HERMES_ASSISTANT_PROFILE
    assert payload["session_id"] == assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    assert payload["total"] == 1
    assert payload["favorites"]


def test_ensure_assistant_chat_session_creates_floating_row(mxai_env) -> None:
    from hermes_state import SessionDB
    from plugins.mxai.agents.assistant import ensure_assistant_chat_session

    ensure_assistant_chat_session()
    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    db = SessionDB(db_path=mxai_env / "profiles" / "assistant" / "state.db")
    try:
        row = db.get_session(sid)
        assert row is not None
        assert row["id"] == sid
        assert row["source"] == ASSISTANT_CHANNEL_FLOATING
    finally:
        db.close()


def test_favorites_crud(mxai_env) -> None:
    fav = add_favorite("暂停所有任务")
    assert fav["text"] == "暂停所有任务"
    items = list_favorites()
    assert any(x["id"] == fav["id"] for x in items)
    assert remove_favorite(fav["id"]) is True
    assert remove_favorite(fav["id"]) is False


def test_history_api_contract(mxai_client, mxai_env) -> None:
    _seed_assistant_transcript(mxai_env)
    body = mxai_client.get("/api/plugins/mxai/chat/commands/history").json()
    assert body["hermes_profile"] == HERMES_ASSISTANT_PROFILE
    assert body["session_id"] == assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    assert body["total"] == 1
    assert body["items"][0]["message"] == "启动抖音评论抓取"


def _seed_wecom_channel(mxai_env) -> None:
    from hermes_state import SessionDB

    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_WECOM)
    db_path = mxai_env / "profiles" / "assistant" / "state.db"
    db = SessionDB(db_path=db_path)
    try:
        db.create_session(sid, source=ASSISTANT_CHANNEL_WECOM)
        db.append_message(sid, "user", "微信客户咨询价格")
        db.append_message(sid, "assistant", "您好，报价已发送。")
    finally:
        db.close()


def test_assistant_inbound_uses_floating_channel_session() -> None:
    sid_a = assistant_inbound_session_id("wx_user_1")
    sid_b = assistant_inbound_session_id("wx_user_2")
    expected_sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    assert sid_a == sid_b == expected_sid
    assert assistant_inbound_session_key("wx_user_1") == (
        "agent:assistant:mxai:chat:floating-chat"
    )


def test_list_unified_transcript_floating_only(mxai_env) -> None:
    _seed_assistant_transcript(mxai_env)
    _seed_wecom_channel(mxai_env)
    items = list_unified_transcript(limit=20)
    assert len(items) == 2
    session_ids = {m["session_id"] for m in items}
    assert session_ids == {assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)}


def test_list_unified_transcript_excludes_clawbot(mxai_env) -> None:
    from hermes_state import SessionDB

    _seed_assistant_transcript(mxai_env)
    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_CLAWBOT)
    db = SessionDB(db_path=mxai_env / "profiles" / "assistant" / "state.db")
    try:
        db.create_session(sid, source=ASSISTANT_CHANNEL_CLAWBOT)
        db.append_message(sid, "user", "[微信] 外部消息")
        db.append_message(sid, "assistant", "外部回复")
    finally:
        db.close()

    items = list_unified_transcript(limit=20)
    assert len(items) == 2
    assert all(
        m["session_id"] == assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
        for m in items
    )


def test_sanitize_transcript_text_strips_wecom_tag() -> None:
    text, channel = _sanitize_transcript_text("[企微] 回魂计")
    assert text == "回魂计"
    assert channel == "wecom"


def test_sanitize_transcript_text_strips_tool_call_leak() -> None:
    raw = '[TOOL_CALL] {tool => "vision_analyze"} [/TOOL_CALL]\n\n商品信息如下。'
    text, channel = _sanitize_transcript_text(raw)
    assert "[TOOL_CALL]" not in text
    assert "商品信息" in text
    assert channel is None


def test_transcript_includes_floating_image_bubble(mxai_env, monkeypatch) -> None:
    from hermes_state import SessionDB
    from gateway.platforms.base import get_image_cache_dir

    cache_dir = get_image_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    img_name = "img_transcript0001.jpg"
    (cache_dir / img_name).write_bytes(b"\xff\xd8\xff" + b"x" * 32)

    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    db = SessionDB(db_path=mxai_env / "profiles" / "assistant" / "state.db")
    try:
        db.create_session(sid, source=ASSISTANT_CHANNEL_FLOATING)
        db.append_message(
            sid,
            "user",
            f"发图\n[mxai-image:{img_name}]",
        )
    finally:
        db.close()

    items = list_unified_transcript(limit=20)
    user_rows = [m for m in items if m.get("from") == "user"]
    assert user_rows
    last = user_rows[-1]
    assert last.get("channel") == "local"
    assert last.get("images")
    assert img_name in (last["images"][0].get("url") or "")


def test_transcript_includes_material_preview_from_marker(mxai_env) -> None:
    from hermes_state import SessionDB
    from plugins.mxai.media import material_preview_marker

    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    db = SessionDB(db_path=mxai_env / "profiles" / "assistant" / "state.db")
    try:
        db.create_session(sid, source=ASSISTANT_CHANNEL_FLOATING)
        db.append_message(
            sid,
            "assistant",
            f"已找到素材 {material_preview_marker(7)}",
        )
    finally:
        db.close()

    items = list_unified_transcript(limit=20)
    ai_rows = [m for m in items if m.get("from") == "ai"]
    assert ai_rows
    last = ai_rows[-1]
    assert last.get("images")
    assert "assets/7/preview" in (last["images"][0].get("url") or "")
    assert "[mxai-material" not in (last.get("text") or "")


def test_transcript_includes_material_preview_from_tool_output(mxai_env) -> None:
    from hermes_state import SessionDB

    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    tool_payload = (
        '{"asset_id": 9, "display_name": "card.jpg", '
        '"preview_kind": "image", "preview_url": "/api/plugins/mxai/materials/assets/9/preview"}'
    )
    db = SessionDB(db_path=mxai_env / "profiles" / "assistant" / "state.db")
    try:
        db.create_session(sid, source=ASSISTANT_CHANNEL_FLOATING)
        db.append_message(sid, "user", "查看")
        db.append_message(sid, "tool", tool_payload, tool_name="mxai_materials_get")
        db.append_message(sid, "assistant", "这是你要看的知识卡片。")
    finally:
        db.close()

    items = list_unified_transcript(limit=20)
    ai_rows = [m for m in items if m.get("from") == "ai"]
    assert ai_rows
    last = ai_rows[-1]
    assert last.get("images")
    assert "assets/9/preview" in (last["images"][0].get("url") or "")


def test_transcript_includes_generated_image_from_tool_output(mxai_env, monkeypatch) -> None:
    from hermes_state import SessionDB
    from gateway.platforms.base import get_image_cache_dir

    cache_dir = get_image_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    img_name = "image_20260302_120000_abcd1234.png"
    img_path = cache_dir / img_name
    img_path.write_bytes(b"\x89PNG\r\n" + b"x" * 32)

    sid = assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
    tool_payload = json.dumps(
        {
            "success": True,
            "image": str(img_path),
            "preview_marker": f"[mxai-image:{img_name}]",
        }
    )
    db = SessionDB(db_path=mxai_env / "profiles" / "assistant" / "state.db")
    try:
        db.create_session(sid, source=ASSISTANT_CHANNEL_FLOATING)
        db.append_message(sid, "user", "生成一张海报")
        db.append_message(sid, "tool", tool_payload, tool_name="image_generate")
        db.append_message(sid, "assistant", "海报已生成。")
    finally:
        db.close()

    items = list_unified_transcript(limit=20)
    ai_rows = [m for m in items if m.get("from") == "ai"]
    assert ai_rows
    last = ai_rows[-1]
    assert last.get("images")
    assert img_name in (last["images"][0].get("url") or "")


def test_transcript_api_contract(mxai_client, mxai_env) -> None:
    _seed_assistant_transcript(mxai_env)
    _seed_wecom_channel(mxai_env)
    body = mxai_client.get("/api/plugins/mxai/chat/transcript?limit=20").json()
    assert body["hermes_profile"] == HERMES_ASSISTANT_PROFILE
    assert body["total"] == 2
    assert body["session_id"] == assistant_channel_session_id(ASSISTANT_CHANNEL_FLOATING)
