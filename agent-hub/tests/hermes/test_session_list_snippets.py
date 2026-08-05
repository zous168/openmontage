"""Session list title/preview sanitization (WeChat-style recent sessions)."""

import tempfile
from pathlib import Path

import pytest

from hermes_state import SessionDB


@pytest.fixture
def session_db(tmp_path: Path) -> SessionDB:
    return SessionDB(db_path=tmp_path / "state.db")


def test_sanitize_title_strips_think_blocks():
    raw = "<think>internal reasoning</think>你是谁"
    assert SessionDB.sanitize_title(raw) == "你是谁"


def test_clean_session_snippet_strips_wechat_prefix():
    text = "[微信] 你好，在吗"
    assert SessionDB.clean_session_snippet(text) == "你好，在吗"


def test_list_sessions_preview_uses_latest_user_message(session_db: SessionDB):
    sid = "test-preview-order"
    session_db.create_session(session_id=sid, source="cli")
    session_db.append_message(sid, "user", "第一条")
    session_db.append_message(sid, "assistant", "reply-1")
    session_db.append_message(sid, "user", "最新一条")

    rows = session_db.list_sessions_rich(limit=10)
    match = next(r for r in rows if r["id"] == sid)
    assert match["preview"] == "最新一条"


def test_list_sessions_title_strips_think_on_read(session_db: SessionDB):
    sid = "test-think-title"
    session_db.create_session(session_id=sid, source="cli")
    session_db.append_message(sid, "user", "Hi")
    think_title = "<think>The user said Hi</think>"
    session_db._conn.execute(
        "UPDATE sessions SET title = ? WHERE id = ?",
        (think_title, sid),
    )
    session_db._conn.commit()

    rows = session_db.list_sessions_rich(limit=10)
    match = next(r for r in rows if r["id"] == sid)
    assert match.get("title") is None
    assert match["preview"] == "Hi"
