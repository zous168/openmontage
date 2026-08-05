"""ClawBot Gateway 平台配置与 Channels 目录测试."""

from __future__ import annotations

from gateway.platforms.clawbot.config import load_clawbot_config, patch_clawbot_config
from gateway.platforms.clawbot.onboard import clawbot_bind_status, start_clawbot_bind


def test_clawbot_config_roundtrip(monkeypatch, tmp_path) -> None:
    import hermes_cli.config as cfg_mod

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("platforms: {}\n", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)

    patch_clawbot_config({"enabled": True, "bind_status": False})
    loaded = load_clawbot_config()
    assert loaded["enabled"] is True
    assert loaded["bind_status"] is False


def test_clawbot_bind_flow(monkeypatch, tmp_path) -> None:
    import hermes_cli.config as cfg_mod

    monkeypatch.setenv("MXAI_MOCK", "1")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("platforms: {}\n", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)
    monkeypatch.setattr(cfg_mod, "get_hermes_home", lambda: tmp_path)
    monkeypatch.setattr(
        "gateway.platform_connect_nudge._nudge_path",
        lambda: tmp_path / "device" / "platform_connect_nudges.json",
    )

    start = start_clawbot_bind()
    token = start["bind_token"]
    assert token.startswith("qr_")

    st = clawbot_bind_status(token)
    assert st["status"] in {"pending", "confirmed"}
    if st["status"] == "pending":
        import time

        time.sleep(1.3)
        st = clawbot_bind_status(token)
    assert st.get("bound") is True
    assert load_clawbot_config()["bind_status"] is True


def test_clawbot_bind_status_ignores_stale_bind_flag(monkeypatch, tmp_path) -> None:
    import hermes_cli.config as cfg_mod

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "platforms:\n  clawbot:\n    enabled: true\n    token: live_tok\n    extra:\n"
        "      bind_status: true\n      bound_wxid: wxid_stale\n"
        "      account_id: bot@im.bot\n      token: live_tok\n"
        "      bind_session:\n        token: stale_qr\n        status: pending\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)

    st = clawbot_bind_status("stale_qr")
    assert st["status"] == "pending"
    assert st.get("bound") is not True


def test_patch_clawbot_config_sets_assistant_profile(monkeypatch, tmp_path) -> None:
    import hermes_cli.config as cfg_mod
    import hermes_cli.profiles as profiles_mod

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "platforms:\n  clawbot:\n    enabled: true\n    extra:\n"
        "      bind_status: true\n"
        "    token: tok\n    extra:\n      account_id: acc\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)
    root = tmp_path / "profiles"
    (root / "assistant").mkdir(parents=True)
    monkeypatch.setattr(profiles_mod, "_get_profiles_root", lambda: root)

    patch_clawbot_config({"stats": {"received": 1, "replied": 0, "today": 1}})
    plat = cfg_mod.load_config().get("platforms", {}).get("clawbot", {})
    extra = plat.get("extra") if isinstance(plat.get("extra"), dict) else {}
    assert extra.get("profile") == "assistant"


def test_session_resolve_profile_clawbot(monkeypatch, tmp_path) -> None:
    from gateway.config import GatewayConfig, Platform, PlatformConfig
    from gateway.session import SessionSource, SessionStore

    import hermes_cli.profiles as profiles_mod

    root = tmp_path / "profiles"
    (root / "assistant").mkdir(parents=True)
    monkeypatch.setattr(profiles_mod, "_get_profiles_root", lambda: root)

    cfg = GatewayConfig()
    cfg.platforms[Platform.CLAWBOT] = PlatformConfig(
        enabled=True,
        extra={"bind_status": True, "profile": "assistant"},
    )
    store = SessionStore(tmp_path / "sessions", cfg)
    source = SessionSource(platform=Platform.CLAWBOT, chat_id="wxuser@im.wechat")
    assert store.resolve_profile(source) == "assistant"


def test_clawbot_credentials_ready() -> None:
    from gateway.platforms.clawbot.config import clawbot_credentials_ready

    assert clawbot_credentials_ready(
        {"bind_status": True, "token": "tok", "account_id": "acc"}
    )
    assert not clawbot_credentials_ready(
        {"bind_status": True, "token": "", "account_id": "acc"}
    )
    assert not clawbot_credentials_ready(
        {"bind_status": True, "bound_wxid": "wxid_x", "token": "", "account_id": ""}
    )


def test_start_bind_clears_stale_credentials(monkeypatch, tmp_path) -> None:
    import hermes_cli.config as cfg_mod

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "platforms:\n  clawbot:\n    enabled: true\n    extra:\n"
        "      bind_status: true\n      bound_wxid: wxid_stale\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)
    monkeypatch.setenv("MXAI_MOCK", "1")

    start_clawbot_bind()
    loaded = load_clawbot_config()
    assert loaded["bind_status"] is False
    assert loaded["bound_wxid"] == ""
    assert loaded["bind_session"]


def test_rebind_does_not_instant_confirm(monkeypatch, tmp_path) -> None:
    """已绑定账号点「重新绑定」时，须等扫码，不得因旧 token 秒确认。"""
    import hermes_cli.config as cfg_mod

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(
        "platforms:\n  clawbot:\n    enabled: true\n    token: old_tok\n    extra:\n"
        "      bind_status: true\n      bound_wxid: o9@im.wechat\n"
        "      account_id: bot@im.bot\n      token: old_tok\n"
        "      user_id: o9@im.wechat\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)
    monkeypatch.setenv("MXAI_MOCK", "1")

    start = start_clawbot_bind()
    token = start["bind_token"]
    loaded = load_clawbot_config()
    assert loaded["bind_status"] is False
    assert loaded["token"] == ""
    assert loaded["account_id"] == ""

    st = clawbot_bind_status(token)
    assert st["status"] == "pending"
    assert st.get("bound") is not True


def test_confirm_ilink_bind_sends_success_message(monkeypatch, tmp_path) -> None:
    import hermes_cli.config as cfg_mod
    from gateway.platforms.clawbot.onboard import _confirm_ilink_bind

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("platforms: {}\n", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setattr(
        "gateway.platforms.clawbot.onboard._mark_clawbot_bind_ready",
        lambda: None,
    )
    sent: list[str] = []
    monkeypatch.setattr(
        "gateway.platforms.clawbot.onboard.send_clawbot_bind_success_message",
        lambda **k: sent.append(k.get("user_id", "")) or True,
    )

    session = {"token": "qr1", "status": "pending"}
    poll = {
        "account_id": "bot@im.bot",
        "token": "bot_token",
        "base_url": "https://ilinkai.weixin.qq.com",
        "user_id": "wxuser@im.wechat",
    }
    _confirm_ilink_bind(session, poll)
    assert sent == ["wxuser@im.wechat"]


def test_resolve_messaging_platform_state() -> None:
    from hermes_cli.web_routes.oauth_messaging import _resolve_messaging_platform_state

    assert (
        _resolve_messaging_platform_state(
            enabled=False,
            configured=True,
        )
        == "disabled"
    )
    assert (
        _resolve_messaging_platform_state(
            enabled=True,
            configured=False,
        )
        == "not_enabled"
    )
    assert (
        _resolve_messaging_platform_state(
            enabled=True,
            configured=True,
            gateway_running=True,
            runtime_platform={"state": "not_configured"},
        )
        == "enabled"
    )
    assert (
        _resolve_messaging_platform_state(
            enabled=True,
            configured=True,
            gateway_running=True,
            runtime_platform={"state": "connected"},
        )
        == "enabled"
    )


def test_resolve_messaging_platform_connection_state() -> None:
    from hermes_cli.web_routes.oauth_messaging import (
        _resolve_messaging_platform_connection_state,
    )

    assert (
        _resolve_messaging_platform_connection_state(
            enabled=False,
            configured=True,
            gateway_running=True,
            runtime_platform={"state": "connected"},
        )
        is None
    )
    assert (
        _resolve_messaging_platform_connection_state(
            enabled=True,
            configured=False,
            gateway_running=True,
            runtime_platform={"state": "connected"},
        )
        is None
    )
    assert (
        _resolve_messaging_platform_connection_state(
            enabled=True,
            configured=True,
            gateway_running=False,
            runtime_platform={"state": "connected"},
        )
        == "gateway_stopped"
    )
    assert (
        _resolve_messaging_platform_connection_state(
            enabled=True,
            configured=True,
            gateway_running=True,
            runtime_platform={"state": "connected"},
        )
        == "connected"
    )
    assert (
        _resolve_messaging_platform_connection_state(
            enabled=True,
            configured=True,
            gateway_running=True,
            runtime_platform={"state": "connecting"},
        )
        == "connecting"
    )
    assert (
        _resolve_messaging_platform_connection_state(
            enabled=True,
            configured=True,
            gateway_running=True,
            runtime_platform={"state": "not_configured"},
        )
        == "connecting"
    )


def test_messaging_catalog_includes_clawbot() -> None:
    from hermes_cli.web_routes.oauth_messaging import _messaging_platform_catalog

    ids = {e["id"] for e in _messaging_platform_catalog()}
    assert "clawbot" in ids
