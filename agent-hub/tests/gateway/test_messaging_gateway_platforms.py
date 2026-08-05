"""Gateway 渠道 API 测试（标准 config.yaml + .env 存储）."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def test_wecom_via_messaging_api(messaging_client: TestClient) -> None:
    put = messaging_client.put(
        "/api/messaging/platforms/wecom",
        json={
            "enabled": True,
            "env": {
                "WECOM_BOT_ID": "bot_test",
                "WECOM_SECRET": "sec",
            },
            "extra": {"welcome": "你好"},
        },
    )
    assert put.status_code == 200

    listed = messaging_client.get("/api/messaging/platforms").json()
    wecom = next(p for p in listed["platforms"] if p["id"] == "wecom")
    assert wecom["enabled"] is True
    assert wecom["platform_extra"]["welcome"] == "你好"


def test_clawbot_bind_via_messaging_api(messaging_client: TestClient) -> None:
    start = messaging_client.post("/api/messaging/clawbot/onboarding/start").json()
    token = start["bind_token"]
    assert token.startswith("qr_")

    time.sleep(1.3)
    st = messaging_client.get(
        f"/api/messaging/clawbot/onboarding/status?token={token}"
    ).json()
    assert st["status"] == "confirmed"
    assert st["bound"] is True

    listed = messaging_client.get("/api/messaging/platforms").json()
    claw = next(p for p in listed["platforms"] if p["id"] == "clawbot")
    assert claw["platform_extra"]["bind_status"] is True
    assert claw["platform_extra"]["bound_wxid"]


def test_mxai_channels_allowlist_includes_clawbot(monkeypatch) -> None:
    import hermes_cli.web_routes.oauth_messaging as om

    om.set_channels_platform_allowlist(
        frozenset({"wecom", "clawbot", "feishu", "dingtalk"}),
        display_order=("clawbot", "wecom", "feishu", "dingtalk"),
    )
    try:
        ids = [e["id"] for e in om._messaging_platform_catalog()]
        assert ids == ["clawbot", "wecom", "feishu", "dingtalk"]
    finally:
        monkeypatch.setattr(om, "_CHANNELS_PLATFORM_ALLOWLIST", None)
        monkeypatch.setattr(om, "_CHANNELS_PLATFORM_DISPLAY_ORDER", None)
