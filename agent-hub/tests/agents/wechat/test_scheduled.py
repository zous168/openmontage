"""LT-002.03.4：个微定时消息."""

def test_wechat_scheduled(mxai_client) -> None:
    mxai_client.post("/api/plugins/mxai/run/all/start")
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/tasks/scheduled-msg",
        json={"recipient": "wx_user", "message": "回访消息", "run_now": True},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] in ("已完成", "排队中", "执行中")
