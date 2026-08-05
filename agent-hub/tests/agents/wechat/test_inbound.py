"""LT-002.03.2：个微入站取回复文案（不入队出站）."""


def test_wechat_inbound(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/inbound",
        json={"message_id": "wx1", "sender": "wx_user", "message": "你好"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "replied"
    assert body["task_id"] is None
    assert body["send_status"] == "not_enqueued"
    assert body["reply"]["source"] == "llm"
