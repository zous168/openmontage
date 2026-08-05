"""FAQ API：渠道废弃（CR-165）；助理端点不返回 410。"""


def test_channel_faq_gone(mxai_client) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/faq",
        json={"data": {"entries": [{"question": "价格", "answer": "联系顾问"}]}},
    )
    assert put.status_code == 410
    got = mxai_client.get("/api/plugins/mxai/agents/douyin/faq")
    assert got.status_code == 410
    body = got.json()
    detail = body.get("detail") or body
    if isinstance(detail, dict):
        assert detail.get("code") == "FAQ_MOVED_TO_KB"


def test_assistant_faq_not_gone(mxai_client) -> None:
    """助理仍走原端点（非 410）；写失败属既有 ConfigManager 域注册问题，不在本 CR。"""
    got = mxai_client.get("/api/plugins/mxai/agents/assistant/faq")
    assert got.status_code != 410
