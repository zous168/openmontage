"""CR-169 · POST …/tasks/video-comment 端点门闸。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.api.deps import get_queue

_URL = "/api/plugins/mxai/agents/douyin/tasks/video-comment"


def _enable(client: TestClient) -> None:
    # 走模块开关而非 PUT workbench：后者会连带同步 Hermes cron job 文件
    client.patch(
        "/api/plugins/mxai/agents/douyin/modules/video_comment",
        json={"enabled": True},
    )


def test_disabled_module_blocks_manual_task(mxai_client: TestClient) -> None:
    get_queue().arm_work()
    mxai_client.patch(
        "/api/plugins/mxai/agents/douyin/modules/video_comment",
        json={"enabled": False},
    )
    res = mxai_client.post(_URL, json={"recipient": "dy_1", "message": "作品不错"})
    assert res.status_code == 422
    assert "video_comment disabled" in res.json()["detail"]


def test_enqueue_when_enabled(mxai_client: TestClient) -> None:
    get_queue().arm_work()
    _enable(mxai_client)
    res = mxai_client.post(_URL, json={"recipient": "dy_ok", "message": "作品不错"})
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] in {"queued", "排队中"}
    task = get_queue()._tasks[body["task_id"]]
    assert task.task_type == "video_comment"
    assert task.payload["recipient"] == "dy_ok"


def test_empty_message_is_accepted(mxai_client: TestClient) -> None:
    """D-b：正文由 AI 生成，message 只是生成输入（客户评论），空也照常入队。"""
    get_queue().arm_work()
    _enable(mxai_client)
    res = mxai_client.post(_URL, json={"recipient": "dy_ok", "message": "  "})
    assert res.status_code == 200, res.text
    task = get_queue()._tasks[res.json()["task_id"]]
    assert task.payload["customer_comment"] == ""
    assert "message" not in task.payload


def test_empty_recipient_rejected(mxai_client: TestClient) -> None:
    get_queue().arm_work()
    _enable(mxai_client)
    res = mxai_client.post(_URL, json={"recipient": "  ", "message": "这个多少钱？"})
    assert res.status_code == 422


def test_non_douyin_channel_rejected(mxai_client: TestClient) -> None:
    """本期仅抖音；小红书/视频号显式 422，不静默入队。"""
    get_queue().arm_work()
    res = mxai_client.post(
        "/api/plugins/mxai/agents/xiaohongshu/tasks/video-comment",
        json={"recipient": "xhs_1", "message": "作品不错"},
    )
    assert res.status_code == 422
    assert "仅支持抖音" in res.json()["detail"]


def test_manual_blocks_ineligible_lead(mxai_client: TestClient, monkeypatch) -> None:
    """手动入队与自动扫描同口径：不可评 lead（如当日 no_video）422。"""
    import plugins.mxai.crm.lead_service as lead_svc

    get_queue().arm_work()
    _enable(mxai_client)
    monkeypatch.setattr(
        lead_svc,
        "get_lead",
        lambda **_kw: {
            "lead_id": "lead_nv",
            "douyin_id": "dy_nv",
            "video_comment_status": "no_video",
            "source_comment": "nihao",
        },
    )
    monkeypatch.setattr(
        lead_svc,
        "video_comment_ineligibility_reason",
        lambda *_a, **_k: "今日已判定无视频可评论，次日可再试",
    )
    res = mxai_client.post(
        _URL,
        json={"recipient": "dy_nv", "message": "nihao", "lead_id": "lead_nv"},
    )
    assert res.status_code == 422, res.text
    assert "无视频可评论" in res.json()["detail"]
