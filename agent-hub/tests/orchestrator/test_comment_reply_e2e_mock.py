"""LT-020.04.02 comment_reply 队列闭环 mock."""

from __future__ import annotations

import time

from plugins.mxai.api.deps import get_queue
from plugins.mxai.crm.lead_service import get_lead, save_leads
from plugins.mxai.rpa.types import CollectedComment
from plugins.mxai.worklog.service import list_worklogs


def test_queue_executes_comment_reply(mxai_env) -> None:
    from tests.conftest import arm_test_queue

    lead_id = save_leads(
        profile_id="douyin",
        source_channel="douyin",
        comments=[CollectedComment("c1", "用户A", "多少钱", "v1", "kw")],
        data_dir=mxai_env,
    )[0]
    q = get_queue()
    arm_test_queue()
    q.set_agent_enabled("douyin", True)
    task = q.enqueue(
        profile_id="douyin",
        name="AI 评论回复",
        task_type="comment_reply",
        payload={"lead_ids": [lead_id]},
    )
    deadline = time.time() + 25
    completed = None
    while time.time() < deadline:
        completed = q.get_task(task.task_id)
        if completed and completed.status.value == "已完成":
            break
        time.sleep(0.05)
    assert completed is not None
    assert completed.status.value == "已完成"
    lead = get_lead(lead_id=lead_id, data_dir=mxai_env)
    assert int(lead["comment_reply_count"]) == 1
    logs = list_worklogs(profile_id="douyin", data_dir=mxai_env)
    assert any(l.get("op_type") == "comment_reply" for l in logs)
    assert any(l.get("touch_class") == "exposure_intent" for l in logs)
