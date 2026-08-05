"""ClawBot iLink QR helper tests."""

from __future__ import annotations

from gateway.platforms.clawbot import ilink as clawbot_ilink


def test_fetch_ilink_qr_parses_response(monkeypatch) -> None:
    def fake_get(base_url: str, endpoint: str, *, timeout: float = 35.0):
        assert "get_bot_qrcode" in endpoint
        return {
            "qrcode": "abc123",
            "qrcode_img_content": "https://example.com/qr",
        }

    monkeypatch.setattr(clawbot_ilink, "_ilink_get", fake_get)
    out = clawbot_ilink.fetch_ilink_qr()
    assert out["qrcode"] == "abc123"
    assert out["qr_payload"] == "https://example.com/qr"


def test_ilink_send_requires_user_initiate_without_session() -> None:
    assert clawbot_ilink.ilink_send_requires_user_initiate(
        {"ret": -2},
        has_context_token=False,
    )
    assert not clawbot_ilink.ilink_send_requires_user_initiate(
        {"ret": -2, "errmsg": "unknown error"},
        has_context_token=True,
    )


def test_send_clawbot_test_message_user_must_initiate(monkeypatch) -> None:
    monkeypatch.setattr(
        clawbot_ilink,
        "clawbot_has_peer_session",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(
        clawbot_ilink,
        "send_ilink_text_message",
        lambda **kwargs: {"ret": -2},
    )
    ok, detail = clawbot_ilink.send_clawbot_test_message(
        token="tok",
        base_url="https://ilinkai.weixin.qq.com",
        user_id="user@im.wechat",
    )
    assert ok is False
    assert "先发" in detail or "发送任意一条" in detail


def test_send_clawbot_test_message_requires_peer_session(monkeypatch) -> None:
    monkeypatch.setattr(
        clawbot_ilink,
        "clawbot_has_peer_session",
        lambda **kwargs: False,
    )
    sent: list[dict] = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return {"ret": 0}

    monkeypatch.setattr(clawbot_ilink, "send_ilink_text_message", fake_send)
    ok, detail = clawbot_ilink.send_clawbot_test_message(
        token="tok",
        base_url="https://ilinkai.weixin.qq.com",
        user_id="user@im.wechat",
    )
    assert ok is False
    assert "先发" in detail or "发送任意一条" in detail
    assert sent == []


def test_send_clawbot_test_message(monkeypatch) -> None:
    sent: list[dict[str, str]] = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return {"ret": 0}

    monkeypatch.setattr(
        clawbot_ilink,
        "clawbot_has_peer_session",
        lambda **kwargs: True,
    )
    monkeypatch.setattr(clawbot_ilink, "send_ilink_text_message", fake_send)
    ok, detail = clawbot_ilink.send_clawbot_test_message(
        token="tok",
        base_url="https://ilinkai.weixin.qq.com",
        user_id="user@im.wechat",
        account_id="acc1",
    )
    assert ok is True
    assert "微信" in detail
    assert sent[0]["to_user_id"] == "user@im.wechat"
    assert "通道测试" in sent[0]["text"]


def test_send_clawbot_bind_success_message(monkeypatch) -> None:
    sent: list[dict[str, str]] = []

    def fake_send(**kwargs):
        sent.append(kwargs)
        return {"ret": 0}

    monkeypatch.setattr(clawbot_ilink, "send_ilink_text_message", fake_send)
    ok = clawbot_ilink.send_clawbot_bind_success_message(
        token="tok",
        base_url="https://ilinkai.weixin.qq.com",
        user_id="user@im.wechat",
    )
    assert ok is True
    assert sent[0]["to_user_id"] == "user@im.wechat"
    assert "绑定成功" in sent[0]["text"]
    assert "重启" not in sent[0]["text"]


def test_send_clawbot_bind_success_message_swallows_errors(monkeypatch) -> None:
    def boom(**kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(clawbot_ilink, "send_ilink_text_message", boom)
    ok = clawbot_ilink.send_clawbot_bind_success_message(
        token="tok",
        base_url="https://ilinkai.weixin.qq.com",
        user_id="user@im.wechat",
    )
    assert ok is False


def test_poll_ilink_qr_status_confirmed(monkeypatch) -> None:
    def fake_get(base_url: str, endpoint: str, *, timeout: float = 35.0):
        assert "get_qrcode_status" in endpoint
        return {
            "status": "confirmed",
            "ilink_bot_id": "bot_1",
            "bot_token": "tok_1",
            "baseurl": "https://ilinkai.weixin.qq.com",
            "ilink_user_id": "user_1",
        }

    monkeypatch.setattr(clawbot_ilink, "_ilink_get", fake_get)
    out = clawbot_ilink.poll_ilink_qr_status("abc123")
    assert out["status"] == "confirmed"
    assert out["account_id"] == "bot_1"
    assert out["token"] == "tok_1"
