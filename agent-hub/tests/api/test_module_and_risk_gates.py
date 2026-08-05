"""模块开关 / 风控 enabled 门闸."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.api.deps import get_queue


def test_comment_reply_disabled_blocks_manual_task(mxai_client: TestClient) -> None:
    get_queue().arm_work()
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench/comment-reply",
        json={"author_name": "测试号", "enabled": True},
    )
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/comment-keywords",
        json={"search_keywords": ["挖掘机"], "match_keywords": []},
    )
    mxai_client.patch(
        "/api/plugins/mxai/agents/douyin/modules/comment_reply",
        json={"enabled": False},
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-reply",
        json={"search_keywords": ["挖掘机"]},
    )
    assert res.status_code == 422
    assert "disabled" in res.json()["detail"]


def test_comment_collect_disabled_blocks_manual_task(mxai_client: TestClient) -> None:
    get_queue().arm_work()
    mxai_client.patch(
        "/api/plugins/mxai/agents/douyin/modules/comment_collect",
        json={"enabled": False},
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-collect",
        json={"search_keywords": ["挖掘机"]},
    )
    assert res.status_code == 422
    assert "comment_collect disabled" in res.json()["detail"]


def test_risk_disabled_blocks_enqueue(mxai_client: TestClient) -> None:
    get_queue().arm_work()
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/risk",
        json={"data": {"enabled": False, "daily_dm_limit": 999, "min_interval_sec": 1}},
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/dm",
        json={"recipient": "user1", "message": "hi"},
    )
    assert res.status_code == 429
    assert "risk disabled" in res.json()["detail"]
    # 避免污染同 session 其它用例
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/risk",
        json={"data": {"enabled": True, "daily_dm_limit": 999, "min_interval_sec": 1}},
    )
