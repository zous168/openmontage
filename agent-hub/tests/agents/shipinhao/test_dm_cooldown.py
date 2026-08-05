"""LT-002.02.02：视频号私信冷却."""

from pathlib import Path

from plugins.mxai.risk.cooldown import apply_operation_cooldown


def test_shipinhao_cooldown(mxai_env: Path) -> None:
    risk = mxai_env / "profiles" / "shipinhao" / "risk.yaml"
    risk.write_text("min_interval_sec: 0.05\n", encoding="utf-8")
    slept1 = apply_operation_cooldown("shipinhao", "dm")
    assert slept1 == 0.0
    slept2 = apply_operation_cooldown("shipinhao", "dm")
    assert slept2 >= 0.04


def test_shipinhao_dm(mxai_client) -> None:
    resp = mxai_client.post(
        "/api/plugins/mxai/agents/shipinhao/tasks/dm",
        json={"recipient": "sph_user", "message": "咨询"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "已完成"
