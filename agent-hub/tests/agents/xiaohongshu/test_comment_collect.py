"""LT-002.01.01：小红书笔记评论采集."""

from plugins.mxai.crm.lead_service import count_leads
from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_xhs_comment_collect(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/xiaohongshu/tasks/comment-collect",
        json={"keywords": ["护肤", "美妆"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["profile_id"] == "xiaohongshu"
    task_id = body["task_id"]
    task = QueueManager.get().get_task(task_id)
    assert task is not None
    assert task.status.value == "已完成"
    assert count_leads(profile_id="xiaohongshu") >= 2
