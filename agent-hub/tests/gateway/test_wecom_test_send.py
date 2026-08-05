"""WeCom dashboard channel test send helpers."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gateway.platforms import wecom


def test_wecom_test_session_store_roundtrip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    store = wecom.WeComTestSessionStore.for_bot("bot_1")
    store.record(chat_id="chat_a", reply_req_id="req_1", chat_type="dm")
    latest = store.latest()
    assert latest == {
        "chat_id": "chat_a",
        "reply_req_id": "req_1",
        "chat_type": "dm",
    }


def test_resolve_wecom_test_target_uses_latest_session(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    wecom.WeComTestSessionStore.for_bot("bot_1").record(
        chat_id="chat_b",
        reply_req_id="req_2",
        chat_type="group",
    )
    target = wecom.resolve_wecom_test_target(bot_id="bot_1")
    assert target is not None
    assert target["chat_id"] == "chat_b"
    assert target["reply_req_id"] == "req_2"


def test_send_wecom_test_message_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_direct(**kwargs):
        assert kwargs.get("chat_type") == "dm"
        return {"success": True, "chat_id": kwargs["chat_id"]}

    monkeypatch.setattr(wecom, "send_wecom_direct", fake_direct)
    monkeypatch.setattr("gateway.platforms.wecom.adapter.send_wecom_direct", fake_direct)
    ok, detail = wecom.send_wecom_test_message(
        extra={"bot_id": "bot", "secret": "sec"},
        chat_id="chat_1",
        chat_type="dm",
    )
    assert ok is True
    assert "企业微信" in detail


def test_send_wecom_test_message_user_must_initiate(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_direct(**kwargs):
        return {"success": False, "error": "invalid chatid for session"}

    monkeypatch.setattr(wecom, "send_wecom_direct", fake_direct)
    monkeypatch.setattr("gateway.platforms.wecom.adapter.send_wecom_direct", fake_direct)
    ok, detail = wecom.send_wecom_test_message(
        extra={"bot_id": "bot", "secret": "sec"},
        chat_id="chat_1",
    )
    assert ok is False
    assert detail == wecom.WECOM_USER_MUST_MESSAGE_FIRST


def test_wecom_platform_test_endpoint_sends_message(
    messaging_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        wecom,
        "resolve_wecom_test_target",
        lambda **kwargs: {"chat_id": "chat_test", "reply_req_id": "req_test"},
    )
    async def fake_send(**kwargs):
        return True, "测试消息已发送到企业微信，请查收。"

    monkeypatch.setattr(wecom, "send_wecom_test_message_async", fake_send)

    put = messaging_client.put(
        "/api/messaging/platforms/wecom",
        json={
            "enabled": True,
            "env": {
                "WECOM_BOT_ID": "bot_test",
                "WECOM_SECRET": "sec",
            },
        },
    )
    assert put.status_code == 200

    resp = messaging_client.post("/api/messaging/platforms/wecom/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "测试消息" in body["message"]


def test_wecom_platform_test_requires_prior_message(
    messaging_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wecom, "resolve_wecom_test_target", lambda **kwargs: None)

    messaging_client.put(
        "/api/messaging/platforms/wecom",
        json={
            "enabled": True,
            "env": {
                "WECOM_BOT_ID": "bot_test",
                "WECOM_SECRET": "sec",
            },
        },
    )
    resp = messaging_client.post("/api/messaging/platforms/wecom/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is False
    assert body["message"] == wecom.WECOM_USER_MUST_MESSAGE_FIRST
