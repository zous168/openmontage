"""LT-002.03.3：个微批量加好友."""

from __future__ import annotations

from plugins.mxai.rpa.wechat.sidecar import WechatSidecar


def test_wechat_add_friends(mxai_client) -> None:
    from plugins.mxai.api.deps import get_queue

    WechatSidecar.reset()
    q = get_queue()
    q.set_agent_enabled("wechat", True)
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/tasks/add-friends",
        json={"contacts": ["user_a", "user_b"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("queued") == 2
    assert len(body.get("task_ids") or []) == 2
    done = 0
    for tid in body["task_ids"]:
        task = q.wait_task(tid, timeout_sec=5.0)
        if task and task.status.value == "已完成":
            done += 1
    assert done >= 1
