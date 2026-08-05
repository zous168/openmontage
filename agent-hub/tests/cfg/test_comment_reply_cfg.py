"""LT-020.01.02 workbench.comment_reply cfg."""

from __future__ import annotations

import pytest

from plugins.mxai.cfg.comment_reply import (
    merge_comment_reply_workbench,
    parse_comment_reply,
    validate_comment_reply,
    write_comment_reply,
)


def test_defaults_max_replies_one() -> None:
    cfg = parse_comment_reply({})
    assert cfg["max_replies_per_lead"] == 1
    assert cfg["enabled"] is True
    assert cfg["chain_to_dm"] is False


def test_validate_max_replies_range() -> None:
    with pytest.raises(ValueError, match="1-10"):
        validate_comment_reply({"max_replies_per_lead": 0})
    with pytest.raises(ValueError, match="1-10"):
        validate_comment_reply({"max_replies_per_lead": 11})
    validate_comment_reply({"max_replies_per_lead": 3})


def test_write_comment_reply_persists(mxai_env, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(mxai_env))
    saved = write_comment_reply(
        "douyin",
        {"max_replies_per_lead": 2, "chain_to_dm": True, "author_name": "测试号"},
    )
    assert saved["max_replies_per_lead"] == 2
    assert saved["chain_to_dm"] is True


def test_write_allows_empty_author_name(mxai_env, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(mxai_env))
    saved = write_comment_reply("douyin", {"enabled": True, "author_name": ""})
    assert saved["enabled"] is True
    assert saved["author_name"] == ""


def test_prepare_comment_reply_payload(mxai_env, monkeypatch) -> None:
    monkeypatch.setenv("HUB_DATA_DIR", str(mxai_env))
    from plugins.mxai.cfg.manager import ConfigManager
    from plugins.mxai.cfg.comment_reply import prepare_comment_reply_payload

    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {"comment_reply": {"author_name": "官方账号", "enabled": True}},
    )
    ConfigManager.get().patch(
        "agent.douyin.comment_keywords",
        {"search_keywords": ["挖掘机"], "match_keywords": []},
    )

    out = prepare_comment_reply_payload("douyin", {"author_name": "残留昵称"})
    assert "author_name" not in out
    assert out["search_keywords"] == ["挖掘机"]


def test_merge_workbench_validates() -> None:
    wb = merge_comment_reply_workbench({"comment_reply": {"max_replies_per_lead": 5, "author_name": "x"}})
    assert wb["comment_reply"]["max_replies_per_lead"] == 5


def test_parse_preserves_run_window_and_schedule() -> None:
    cfg = parse_comment_reply(
        {
            "enabled": True,
            "author_name": "测试号",
            "daily_start_at": "09:00",
            "interval_minutes": 30,
            "max_videos_per_run": 10,
            "max_comments_per_run": 20,
            "run_window": {"start": "09:00", "end": "18:00"},
        }
    )
    assert cfg["daily_start_at"] == "09:00"
    assert cfg["run_window"] == {"start": "09:00", "end": "18:00"}
    assert cfg["interval_minutes"] == 30
    wb = merge_comment_reply_workbench({"comment_reply": dict(cfg)}, profile_id="douyin")
    assert wb["comment_reply"]["run_window"]["end"] == "18:00"


def test_merge_workbench_private_agent_no_author_name() -> None:
    wb = merge_comment_reply_workbench(
        {"comment_reply": {"enabled": True, "author_name": ""}},
        profile_id="wechat",
    )
    assert wb["comment_reply"]["enabled"] is False
