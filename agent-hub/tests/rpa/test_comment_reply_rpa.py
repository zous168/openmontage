"""LT-020.04.01 comment_reply RPA mock."""

from __future__ import annotations

from plugins.mxai.rpa.common.comment_reply import run_comment_reply


def test_mock_returns_platform_reply_id() -> None:
    posted = run_comment_reply(
        "douyin",
        video_id="vid_1",
        target_comment_id="lead_1",
        reply_text="感谢咨询",
        mode="mock",
        interval_sec=1,
    )
    assert posted.platform_reply_comment_id.startswith("rc_")
    assert posted.text == "感谢咨询"
    assert posted.video_id == "vid_1"
