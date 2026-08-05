"""LT-020.02.01 WorkLog touch_class."""

from __future__ import annotations

from plugins.mxai.worklog.service import append_worklog, list_worklogs
from plugins.mxai.worklog.touch_class import resolve_touch_class


def test_resolve_touch_class_mapping() -> None:
    assert resolve_touch_class("comment_reply") == "exposure_intent"
    assert resolve_touch_class("dm") == "intent_only"
    assert resolve_touch_class("first_comment") == "exposure"
    assert resolve_touch_class("unknown_op") is None


def test_append_worklog_sets_touch_class(tmp_path) -> None:
    data_dir = tmp_path
    append_worklog(
        profile_id="douyin",
        op_type="comment_reply",
        exec_status="成功",
        op_object="test",
        data_dir=data_dir,
    )
    rows = list_worklogs(profile_id="douyin", data_dir=data_dir)
    assert rows[0]["touch_class"] == "exposure_intent"
