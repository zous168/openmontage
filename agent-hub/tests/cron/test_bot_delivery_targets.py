"""Cron delivery target resolution for bot platforms."""

from __future__ import annotations

import pytest


def test_resolve_wecom_bot_target_from_session(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    monkeypatch.setattr(
        "gateway.platforms.wecom.config.load_wecom_config",
        lambda: {"bot_id": "bot-1"},
    )
    monkeypatch.setattr(
        "gateway.platforms.wecom.resolve_wecom_test_target",
        lambda *, bot_id: {"chat_id": "chat-abc", "chat_type": "dm"},
    )

    target = sched._resolve_wecom_bot_target()
    assert target == {
        "platform": "wecom",
        "chat_id": "chat-abc",
        "thread_id": None,
        "chat_type": "dm",
    }


def test_resolve_wecom_prefers_bot_session_over_home_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    monkeypatch.setenv("WECOM_HOME_CHANNEL", "legacy-home")
    monkeypatch.setattr(
        "gateway.platforms.wecom.config.load_wecom_config",
        lambda: {"bot_id": "bot-1"},
    )
    monkeypatch.setattr(
        "gateway.platforms.wecom.resolve_wecom_test_target",
        lambda *, bot_id: {"chat_id": "chat-abc", "chat_type": "dm"},
    )

    target = sched._resolve_platform_delivery_target("wecom")
    assert target is not None
    assert target["chat_id"] == "chat-abc"
    assert target.get("chat_type") == "dm"


def test_resolve_clawbot_target_from_bound_user(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    monkeypatch.setattr(
        "gateway.platforms.clawbot.config.load_clawbot_config",
        lambda: {
            "bind_status": True,
            "token": "tok",
            "account_id": "acct",
            "user_id": "wx-user-1",
        },
    )
    monkeypatch.setattr(
        "gateway.platforms.clawbot.config.clawbot_credentials_ready",
        lambda cfg=None: True,
    )

    target = sched._resolve_clawbot_target()
    assert target == {"platform": "clawbot", "chat_id": "wx-user-1", "thread_id": None}


def test_clawbot_is_known_delivery_platform() -> None:
    from cron.scheduler import _is_known_delivery_platform

    assert _is_known_delivery_platform("clawbot")


def test_cron_delivery_targets_surfaces_direct_bot_without_gateway_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: wecom/clawbot are configured via their own plugin config
    loaders, invisible to get_connected_platforms(). cron_delivery_targets()
    must still list a direct bot whose resolver reaches a target, else the
    dashboard dropdown wrongly shows Local-only."""
    from cron import scheduler as sched

    # Base gateway config reports NOTHING connected (marketing-hub reality).
    class _Cfg:
        def get_connected_platforms(self):
            return []

    monkeypatch.setattr("gateway.config.load_gateway_config", lambda: _Cfg())
    # wecom resolves (bound bot chat); clawbot does not (unbound).
    monkeypatch.setattr(
        sched,
        "_resolve_platform_delivery_target",
        lambda name: {"platform": "wecom", "chat_id": "x"} if name == "wecom" else None,
    )

    targets = {t["id"]: t for t in sched.cron_delivery_targets()}
    assert "wecom" in targets
    assert targets["wecom"]["home_target_set"] is True
    assert "clawbot" not in targets  # resolver None → correctly hidden until bound


def test_api_server_origin_falls_back_to_clawbot(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched

    monkeypatch.setattr(
        sched,
        "_resolve_clawbot_target",
        lambda: {"platform": "clawbot", "chat_id": "wx-user", "thread_id": None},
    )
    job = {
        "id": "j1",
        "name": "test",
        "origin": {"platform": "api_server", "chat_id": "mxai-assistant-floating-chat"},
    }
    target = sched._resolve_single_delivery_target(job, "origin")
    assert target is not None
    assert target["platform"] == "clawbot"
    assert target["chat_id"] == "wx-user"
