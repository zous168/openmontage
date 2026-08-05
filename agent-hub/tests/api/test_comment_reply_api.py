"""LT-020.03.01 POST comment-reply API."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.api.deps import get_queue
from plugins.mxai.cfg.manager import ConfigManager


def _enable_comment_reply(mxai_env) -> None:
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {"comment_reply": {"enabled": True, "author_name": "测试抖音号"}},
    )
    ConfigManager.get().patch(
        "agent.douyin.comment_keywords",
        {"search_keywords": ["工程机械"], "match_keywords": []},
    )


def test_comment_reply_enqueue(mxai_client: TestClient, mxai_env) -> None:
    _enable_comment_reply(mxai_env)
    get_queue().set_agent_enabled("douyin", True)
    res = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-reply",
        json={"search_keywords": ["工程机械"]},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["task_id"]
    assert body["search_keywords"] == ["工程机械"]


def test_comment_reply_uses_saved_keywords(mxai_client: TestClient, mxai_env) -> None:
    _enable_comment_reply(mxai_env)
    get_queue().set_agent_enabled("douyin", True)
    res = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-reply",
        json={},
    )
    assert res.status_code == 200
    assert res.json()["search_keywords"] == ["工程机械"]


def test_comment_reply_requires_keywords(mxai_client: TestClient, mxai_env) -> None:
    ConfigManager.get().patch(
        "agent.douyin.workbench",
        {"comment_reply": {"enabled": True, "author_name": "测试抖音号"}},
    )
    ConfigManager.get().patch(
        "agent.douyin.comment_keywords",
        {"search_keywords": [], "match_keywords": []},
    )
    get_queue().set_agent_enabled("douyin", True)
    res = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-reply",
        json={},
    )
    assert res.status_code == 422


def test_comment_reply_409_when_not_armed(mxai_client: TestClient, mxai_env) -> None:
    _enable_comment_reply(mxai_env)
    get_queue().disarm_work()
    res = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/tasks/comment-reply",
        json={"search_keywords": ["工程机械"]},
    )
    assert res.status_code == 409
    get_queue().arm_work()
