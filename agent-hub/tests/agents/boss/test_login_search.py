"""LT-002.05.1：Boss 搜索."""

def test_boss_search(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/boss/tasks/boss-search",
        json={"keywords": ["产品经理", "北京"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "已完成"
    result = body.get("result") or {}
    assert result.get("logged_in") or result.get("jobs") or result.get("keywords")
