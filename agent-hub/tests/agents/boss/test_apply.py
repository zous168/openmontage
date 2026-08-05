"""LT-002.05.3：Boss 拓聊/投递响应."""

def test_boss_apply_respond(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/boss/tasks/apply-respond",
        json={"application_id": "app_99", "message": "感谢投递"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "已完成"
