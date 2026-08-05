"""LT-002.05.4：Boss 邀约."""

def test_boss_invite(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/boss/tasks/invite",
        json={"candidate_id": "cand_88", "slot": "周三 14:00"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "已完成"
