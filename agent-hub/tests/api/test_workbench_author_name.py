"""workbench comment_reply.author_name：可持久化，启用时不再强制必填."""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.api.deps import get_queue


def test_workbench_author_name_roundtrip(mxai_client: TestClient) -> None:
    get_queue().arm_work()
    res = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench/comment-reply",
        json={"author_name": "肉肉_205"},
    )
    assert res.status_code == 200
    assert res.json()["comment_reply"]["author_name"] == "肉肉_205"

    get = mxai_client.get("/api/plugins/mxai/agents/douyin/workbench/comment-reply")
    assert get.status_code == 200
    assert get.json()["comment_reply"]["author_name"] == "肉肉_205"

    wb = mxai_client.get("/api/plugins/mxai/agents/douyin/workbench")
    assert wb.json()["data"]["comment_reply"]["author_name"] == "肉肉_205"


def test_get_workbench_allows_empty_author_name(mxai_client: TestClient) -> None:
    res = mxai_client.get("/api/plugins/mxai/agents/shipinhao/workbench")
    assert res.status_code == 200
    cr = res.json()["data"]["comment_reply"]
    assert cr["enabled"] is True
    assert cr.get("author_name", "") == ""


def test_put_workbench_enabled_allows_empty_author_name(mxai_client: TestClient) -> None:
    res = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench",
        json={"data": {"comment_reply": {"enabled": True, "author_name": ""}}},
    )
    assert res.status_code == 200
    assert res.json()["data"]["comment_reply"]["enabled"] is True


def test_module_enable_comment_reply_allows_empty_author_name(mxai_client: TestClient) -> None:
    res = mxai_client.patch(
        "/api/plugins/mxai/agents/douyin/modules/comment_reply",
        json={"enabled": True},
    )
    assert res.status_code == 200
    assert res.json()["enabled"] is True


def test_module_toggle_preserves_author_name(mxai_client: TestClient) -> None:
    get_queue().arm_work()
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench/comment-reply",
        json={"author_name": "肉肉_205", "enabled": True},
    )
    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/workbench",
        json={"data": {"dm": {"message": "您好"}}},
    )
    toggle = mxai_client.patch(
        "/api/plugins/mxai/agents/douyin/modules/comment_reply",
        json={"enabled": False},
    )
    assert toggle.status_code == 200

    get = mxai_client.get("/api/plugins/mxai/agents/douyin/workbench")
    cr = get.json()["data"]["comment_reply"]
    assert cr["author_name"] == "肉肉_205"
    assert cr["enabled"] is False
    assert get.json()["data"]["dm"]["message"] == "您好"
