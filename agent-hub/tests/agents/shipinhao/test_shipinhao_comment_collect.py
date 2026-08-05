"""LT-002.02.01：视频号评论采集."""

from plugins.mxai.crm.lead_service import count_leads
from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_shipinhao_comment_collect(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/shipinhao/tasks/comment-collect",
        json={"keywords": ["直播"]},
    )
    assert resp.status_code == 200
    task_id = resp.json()["task_id"]
    task = QueueManager.get().get_task(task_id)
    assert task is not None
    assert task.status.value == "已完成"
    assert count_leads(profile_id="shipinhao") >= 1
