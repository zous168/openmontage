"""LT-002.05.2：Boss 打招呼."""

def test_boss_greet(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/boss/tasks/greet",
        json={"candidates": ["cand_1", "cand_2"], "template": "您好"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "已完成"
