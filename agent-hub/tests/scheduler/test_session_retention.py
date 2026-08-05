"""LT-031.05.02：差异化会话过期/空闲归档（BR-08）.

覆盖：
- profile_id 前缀解析；
- 纯判定 retention_decision（公域 24h 删、Boss 7 天删、私域永久跳、未到期跳、未知渠道跳、archive 动作）；
- sweep_expired_sessions 端到端（真实临时 SessionDB：到期删 / 私域留 / 未到期留）。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from plugins.mxai.scheduler import session_retention as sr


# ── profile_id 解析 ──────────────────────────────────────────────────────────

def test_parse_profile_id_public() -> None:
    assert sr.parse_profile_id("mxai-douyin-inbound-deadbeef0badf00d") == "douyin"


def test_parse_profile_id_private() -> None:
    assert sr.parse_profile_id("mxai-wechat-inbound-default") == "wechat"


def test_parse_profile_id_non_mxai_returns_none() -> None:
    assert sr.parse_profile_id("cli-12345") is None
    assert sr.parse_profile_id("") is None
    assert sr.parse_profile_id("mxai-douyin-other-x") is None


# ── 纯判定 retention_decision ────────────────────────────────────────────────

NOW = 1_700_000_000.0


def _ago(hours: float) -> float:
    return NOW - hours * 3600.0


def test_public_expires_after_24h_deletes() -> None:
    sid = "mxai-douyin-inbound-aaaa"
    # 24h 整 + 一点 → 删除
    assert sr.retention_decision(sid, _ago(24.1), now=NOW) == sr.ACTION_DELETE


def test_public_not_expired_skips() -> None:
    sid = "mxai-xiaohongshu-inbound-bbbb"
    assert sr.retention_decision(sid, _ago(23.0), now=NOW) == sr.ACTION_SKIP


def test_boss_expires_after_7_days_deletes() -> None:
    sid = "mxai-boss-inbound-cccc"
    assert sr.retention_decision(sid, _ago(24 * 7 + 1), now=NOW) == sr.ACTION_DELETE
    # 6 天 → 未到期
    assert sr.retention_decision(sid, _ago(24 * 6), now=NOW) == sr.ACTION_SKIP


def test_private_permanent_always_skips() -> None:
    for pid in ("wechat", "qiyeweixin"):
        sid = f"mxai-{pid}-inbound-dddd"
        # 即便过去很久也永久保留
        assert sr.retention_decision(sid, _ago(24 * 365), now=NOW) == sr.ACTION_SKIP


def test_unknown_channel_skips() -> None:
    sid = "mxai-unknownchan-inbound-eeee"
    assert sr.retention_decision(sid, _ago(99999), now=NOW) == sr.ACTION_SKIP


def test_missing_last_active_skips() -> None:
    sid = "mxai-douyin-inbound-ffff"
    assert sr.retention_decision(sid, None, now=NOW) == sr.ACTION_SKIP


def test_archive_action_when_policy_says_archive(monkeypatch: pytest.MonkeyPatch) -> None:
    # 注入一个 archive 策略渠道，验证 action 透传
    monkeypatch.setitem(
        sr.RETENTION_POLICIES,
        "archchan",
        sr.RetentionPolicy(retention_hours=1.0, action=sr.ACTION_ARCHIVE),
    )
    sid = "mxai-archchan-inbound-1111"
    assert sr.retention_decision(sid, _ago(2.0), now=NOW) == sr.ACTION_ARCHIVE


# ── sweep 端到端（真实临时 SessionDB）───────────────────────────────────────

@pytest.fixture
def state_db(tmp_path: Path):
    from hermes_state import SessionDB

    db_path = tmp_path / "state.db"
    db = SessionDB(db_path=db_path)
    yield db, db_path
    db.close()


def _seed(db, sid: str, last_active_ts: float) -> None:
    """建 session 并写一条消息，再把消息时间戳改成指定值（控制 last_active）。"""
    db.ensure_session(sid, "agent_reply")
    db.append_message(sid, "user", "hi")
    # 直接改 messages.timestamp，使 MAX(timestamp) = last_active_ts
    db._execute_write(  # noqa: SLF001 — 测试内直接落库以构造 last_active
        lambda conn: conn.execute(
            "UPDATE messages SET timestamp = ? WHERE session_id = ?",
            (last_active_ts, sid),
        )
    )


def test_sweep_deletes_expired_public_keeps_private_and_fresh(state_db) -> None:
    db, db_path = state_db
    now = time.time()
    expired_public = "mxai-douyin-inbound-exp1"
    fresh_public = "mxai-douyin-inbound-fresh1"
    private_old = "mxai-wechat-inbound-perm1"
    non_mxai = "cli-keepme"

    _seed(db, expired_public, now - 25 * 3600)   # 公域 25h 前 → 删
    _seed(db, fresh_public, now - 1 * 3600)       # 公域 1h 前 → 留
    _seed(db, private_old, now - 1000 * 3600)     # 私域很久 → 永久留
    _seed(db, non_mxai, now - 1000 * 3600)        # 非入站 → 不在扫描范围

    result = sr.sweep_expired_sessions(now=now, db_path=db_path)

    assert result["ok"] is True
    assert result["deleted"] == 1
    assert result["errors"] == 0
    # 扫描仅覆盖 mxai-*-inbound-*（3 条），non_mxai 不计入
    assert result["scanned"] == 3

    assert db.get_session(expired_public) is None
    assert db.get_session(fresh_public) is not None
    assert db.get_session(private_old) is not None
    assert db.get_session(non_mxai) is not None


def test_sweep_empty_db_is_noop(tmp_path: Path) -> None:
    result = sr.sweep_expired_sessions(db_path=tmp_path / "missing.db")
    assert result == {
        "ok": True,
        "scanned": 0,
        "deleted": 0,
        "archived": 0,
        "skipped": 0,
        "errors": 0,
    }


def test_sweep_traverses_all_profile_dbs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """不带 db_path 时遍历各渠道 profile 的 state.db 并汇总（LT-031 per-profile 隔离）。"""
    from hermes_state import SessionDB

    now = time.time()
    # 仅把 get_profile_dir 指向各自临时目录；douyin 放一个到期会话，wechat 放永久会话。
    def _fake_profile_dir(name: str) -> Path:
        return tmp_path / "profiles" / name

    monkeypatch.setattr("hermes_cli.profiles.get_profile_dir", _fake_profile_dir)

    douyin_db = SessionDB(db_path=_fake_profile_dir("douyin") / "state.db")
    wechat_db = SessionDB(db_path=_fake_profile_dir("wechat") / "state.db")
    try:
        _seed(douyin_db, "mxai-douyin-inbound-exp1", now - 25 * 3600)  # 公域到期 → 删
        _seed(wechat_db, "mxai-wechat-inbound-perm1", now - 1000 * 3600)  # 私域永久 → 留

        result = sr.sweep_expired_sessions(now=now)

        assert result["ok"] is True
        assert result["deleted"] == 1
        assert result["skipped"] == 1
        assert result["errors"] == 0
        # 两库各扫到 1 条入站会话
        assert result["scanned"] == 2
        assert douyin_db.get_session("mxai-douyin-inbound-exp1") is None
        assert wechat_db.get_session("mxai-wechat-inbound-perm1") is not None
    finally:
        douyin_db.close()
        wechat_db.close()
