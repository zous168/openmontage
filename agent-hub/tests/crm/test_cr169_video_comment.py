"""CR-169 · video_comment_status 三态 / eligible 扫描 / 次日回流。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from plugins.mxai.cfg.paths import mxai_db_path
from plugins.mxai.crm.lead_service import (
    VIDEO_COMMENT_NO_VIDEO,
    VIDEO_COMMENT_NOT_SENT,
    VIDEO_COMMENT_SENT,
    get_lead,
    insert_comment_lead,
    is_lead_eligible_for_video_comment,
    list_lead_ids_pending_video_comment,
    record_video_comment_no_video,
    record_video_comment_sent,
    video_comment_ineligibility_reason,
)


@pytest.fixture
def vc_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """全局单例跨用例残留会让整包跑与单跑结果不同，逐例重置。"""
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.orchestrator.queue_manager import QueueManager

    data_dir = tmp_path / "hub"
    (data_dir / "profiles" / "douyin").mkdir(parents=True)
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setattr("runtime_paths.resolve_hub_data_dir_path", lambda: data_dir)
    monkeypatch.setattr(
        "plugins.mxai.scheduler.state.resolve_hub_data_dir_path", lambda: data_dir
    )
    ConfigManager.reset()
    QueueManager.reset()
    return data_dir


def _add(env: Path, nickname: str, douyin_id: str, time_iso: str | None = None) -> str:
    r = insert_comment_lead(
        profile_id="douyin",
        nickname=nickname,
        douyin_id=douyin_id,
        comment="c",
        intent="高",
        time_iso=time_iso,
        data_dir=env,
    )
    return str(r["lead_id"])


def _set_checked_at(env: Path, lead_id: str, value: str) -> None:
    """直接改判定时间，模拟「昨天判定的无视频」。"""
    conn = sqlite3.connect(mxai_db_path("hub.db", env))
    try:
        conn.execute(
            "UPDATE douyin_leads SET video_comment_checked_at = ? WHERE lead_id = ?",
            (value, lead_id),
        )
        conn.commit()
    finally:
        conn.close()


def test_new_lead_defaults_not_sent(vc_env: Path) -> None:
    lead_id = _add(vc_env, "新客户", "dy_new")
    lead = get_lead(lead_id=lead_id, data_dir=vc_env)
    assert lead["video_comment_status"] == VIDEO_COMMENT_NOT_SENT
    assert lead["video_comment_checked_at"] is None
    assert lead_id in list_lead_ids_pending_video_comment("douyin", data_dir=vc_env)


def test_pending_scan_is_fifo(vc_env: Path) -> None:
    _add(vc_env, "后来的", "dy_b", time_iso="2026-01-02T00:00:00+00:00")
    _add(vc_env, "先来的", "dy_a", time_iso="2026-01-01T00:00:00+00:00")
    ids = list_lead_ids_pending_video_comment("douyin", data_dir=vc_env)
    first = get_lead(lead_id=ids[0], data_dir=vc_env)
    assert first["douyin_id"] == "dy_a"


def test_sent_is_terminal(vc_env: Path) -> None:
    lead_id = _add(vc_env, "已评", "dy_sent")
    record_video_comment_sent(lead_id, data_dir=vc_env)
    assert get_lead(lead_id=lead_id, data_dir=vc_env)["video_comment_status"] == VIDEO_COMMENT_SENT
    assert list_lead_ids_pending_video_comment("douyin", data_dir=vc_env) == []


def test_no_video_skipped_same_day(vc_env: Path) -> None:
    lead_id = _add(vc_env, "无作品", "dy_nv")
    record_video_comment_no_video(lead_id, data_dir=vc_env)
    lead = get_lead(lead_id=lead_id, data_dir=vc_env)
    assert lead["video_comment_status"] == VIDEO_COMMENT_NO_VIDEO
    assert lead["video_comment_checked_at"]
    assert list_lead_ids_pending_video_comment("douyin", data_dir=vc_env) == []
    assert is_lead_eligible_for_video_comment(lead_id, data_dir=vc_env) is False
    assert "无视频可评论" in (video_comment_ineligibility_reason(lead, data_dir=vc_env) or "")


def test_no_video_returns_next_day(vc_env: Path) -> None:
    """跨北京零点后重新可评；状态列不回跳（仍显示无视频可评论）。"""
    lead_id = _add(vc_env, "昨天无作品", "dy_nv_yesterday")
    record_video_comment_no_video(lead_id, data_dir=vc_env)
    _set_checked_at(vc_env, lead_id, "2020-01-01T00:00:00+00:00")

    assert lead_id in list_lead_ids_pending_video_comment("douyin", data_dir=vc_env)
    assert (
        get_lead(lead_id=lead_id, data_dir=vc_env)["video_comment_status"]
        == VIDEO_COMMENT_NO_VIDEO
    )


def test_no_video_boundary_uses_beijing_day(vc_env: Path) -> None:
    """UTC 今天 16:00 = 北京次日 00:00：判定时间落在北京同一业务日则仍不回流。"""
    lead_id = _add(vc_env, "边界", "dy_boundary")
    record_video_comment_no_video(lead_id, data_dir=vc_env)
    conn = sqlite3.connect(mxai_db_path("hub.db", vc_env))
    try:
        # 取「北京今天 00:30」对应的 UTC 时刻（= 北京日的最早时刻之一）
        today_utc = conn.execute(
            "SELECT datetime(date('now', '+8 hours') || ' 00:30:00', '-8 hours')"
        ).fetchone()[0]
    finally:
        conn.close()
    _set_checked_at(vc_env, lead_id, today_utc)
    assert list_lead_ids_pending_video_comment("douyin", data_dir=vc_env) == []


def test_lead_without_douyin_id_not_eligible(vc_env: Path) -> None:
    """无抖音id 不入队（UI 另展示「缺少抖音id」，库内仍 not_sent）。"""
    lead_id = _add(vc_env, "无id客户", "dy_will_be_cleared")
    lead = get_lead(lead_id=lead_id, data_dir=vc_env)
    assert lead["video_comment_status"] == VIDEO_COMMENT_NOT_SENT
    # insert_comment_lead 强制要求 douyin_id；清空后模拟「评论上报未带抖音id」的存量行
    conn = sqlite3.connect(mxai_db_path("hub.db", vc_env))
    try:
        conn.execute("UPDATE douyin_leads SET douyin_id = '' WHERE lead_id = ?", (lead_id,))
        conn.commit()
    finally:
        conn.close()
    assert list_lead_ids_pending_video_comment("douyin", data_dir=vc_env) == []


def test_video_comment_independent_from_dm_touch(vc_env: Path) -> None:
    """两个触达状态互不影响（同一 Lead 可私信已发、视频评论未发）。"""
    from plugins.mxai.crm.lead_service import list_lead_ids_pending_dm, record_dm_sent

    lead_id = _add(vc_env, "双状态", "dy_both")
    record_dm_sent(lead_id, data_dir=vc_env)
    assert list_lead_ids_pending_dm("douyin", data_dir=vc_env) == []
    assert lead_id in list_lead_ids_pending_video_comment("douyin", data_dir=vc_env)
