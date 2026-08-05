"""LT-002.07.2：风控配置 API."""

def test_risk_crud(mxai_client) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/wechat/risk",
        json={"data": {"daily_dm_limit": 50, "min_interval_sec": 2}},
    )
    assert put.status_code == 200
    got = mxai_client.get("/api/plugins/mxai/agents/wechat/risk").json()
    assert got["data"]["daily_dm_limit"] == 50
