"""LT-020.02.02 goals/today 含 AI 评论回复."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.worklog.service import append_worklog


def test_goals_today_counts_comment_reply(mxai_client: TestClient, mxai_env) -> None:
    append_worklog(
        profile_id="douyin",
        op_type="comment_reply",
        exec_status="成功",
        data_dir=mxai_env,
    )
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/goals",
        json={"goals": [{"metric": "AI 评论回复", "daily_target": 10}]},
    )
    res = mxai_client.get("/api/plugins/mxai/agents/douyin/goals/today")
    assert res.status_code == 200
    items = res.json()["items"]
    metric = next(i for i in items if i["metric"] == "AI 评论回复")
    assert metric["done"] == 1
    assert metric["target"] == 10
