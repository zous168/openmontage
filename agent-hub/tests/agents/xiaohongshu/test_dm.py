"""LT-002.01.02：小红书私信 + 风控."""

from pathlib import Path

from plugins.mxai.worklog.service import append_worklog


def test_xhs_dm(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/xiaohongshu/tasks/dm",
        json={"recipient": "xhs_user_1", "message": "想了解产品"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "已完成"


def test_xhs_dm_limit(mxai_env: Path, mxai_client) -> None:
    risk = mxai_env / "profiles" / "xiaohongshu" / "risk.yaml"
    risk.write_text("daily_dm_limit: 1\nmin_interval_sec: 0\n", encoding="utf-8")
    append_worklog(
        profile_id="xiaohongshu",
        op_type="dm",
        exec_status="成功",
        data_dir=mxai_env,
    )
    r2 = mxai_client.post(
        "/api/plugins/mxai/agents/xiaohongshu/tasks/dm",
        json={"recipient": "u2", "message": "again"},
    )
    assert r2.status_code == 429
