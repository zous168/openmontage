"""LT-020.06.01 demo_seed comment_reply worklogs."""

from __future__ import annotations

from plugins.mxai.cfg.bootstrap.demo_seed import seed_demo_data
from plugins.mxai.worklog.service import list_worklogs


def test_demo_seed_includes_comment_reply_logs(mxai_env) -> None:
    seed_demo_data(mxai_env, force=True)
    rows = list_worklogs(data_dir=mxai_env, limit=200)
    reply_rows = [r for r in rows if r.get("op_type") == "comment_reply"]
    assert len(reply_rows) >= 6
    public = {"douyin", "xiaohongshu", "shipinhao"}
    assert sum(1 for r in reply_rows if r.get("profile_id") in public) >= 6
    assert all(r.get("touch_class") == "exposure_intent" for r in reply_rows)
