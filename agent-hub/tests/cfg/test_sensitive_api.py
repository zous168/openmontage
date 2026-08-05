"""LT-002.07.3：敏感词 API."""

def test_sensitive_crud(mxai_client) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/sensitive-words",
        json={"data": {"words": ["违禁词"]}},
    )
    assert put.status_code == 200
    got = mxai_client.get("/api/plugins/mxai/agents/douyin/sensitive-words").json()
    assert "违禁词" in got["data"]["words"]
