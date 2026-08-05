"""核心下钻：agent 与 profile_ids 边界解析."""

from plugins.mxai.api.worklogs import resolve_worklog_profile_scope


def test_whitelist_only():
    pid, pids, empty = resolve_worklog_profile_scope(None, ["douyin", "xiaohongshu"])
    assert pid is None
    assert pids == ["douyin", "xiaohongshu"]
    assert empty is False


def test_agent_narrows_within_whitelist():
    pid, pids, empty = resolve_worklog_profile_scope("douyin", ["douyin", "xiaohongshu"])
    assert pid is None
    assert pids == ["douyin"]
    assert empty is False


def test_agent_outside_whitelist_is_empty():
    pid, pids, empty = resolve_worklog_profile_scope("wechat", ["douyin", "xiaohongshu"])
    assert empty is True
    assert pid is None
    assert pids is None


def test_agent_only():
    pid, pids, empty = resolve_worklog_profile_scope("wechat", [])
    assert pid == "wechat"
    assert pids is None
    assert empty is False
