"""ClawBot 消息统计测试."""

from __future__ import annotations

import pytest


@pytest.fixture
def clawbot_stats_env(monkeypatch, tmp_path):
    import runtime_paths as rp_mod

    device = tmp_path / "device"
    device.mkdir(parents=True)
    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: tmp_path)
    monkeypatch.setattr(
        "core.timeutil.beijing_today_str",
        lambda: "2026-07-01",
    )
    return tmp_path


def test_clawbot_stats_increment(clawbot_stats_env) -> None:
    from gateway.platforms.clawbot.stats import (
        load_clawbot_message_stats,
        record_clawbot_received,
        record_clawbot_replied,
    )

    record_clawbot_received()
    record_clawbot_received()
    record_clawbot_replied()

    stats = load_clawbot_message_stats()
    assert stats == {"received": 2, "replied": 1, "today": 3}


def test_clawbot_stats_resets_today_on_new_beijing_day(clawbot_stats_env, monkeypatch) -> None:
    from gateway.platforms.clawbot.stats import (
        load_clawbot_message_stats,
        record_clawbot_received,
    )

    record_clawbot_received()
    assert load_clawbot_message_stats()["today"] == 1

    monkeypatch.setattr(
        "core.timeutil.beijing_today_str",
        lambda: "2026-07-02",
    )
    record_clawbot_received()
    stats = load_clawbot_message_stats()
    assert stats["received"] == 2
    assert stats["today"] == 1


def test_clawbot_stats_records_last_inbound_peer(clawbot_stats_env) -> None:
    from gateway.platforms.clawbot.stats import (
        get_last_clawbot_inbound_peer,
        record_clawbot_received,
    )

    record_clawbot_received(sender_id="wxid_peer_abc")
    assert get_last_clawbot_inbound_peer() == "wxid_peer_abc"


def test_clawbot_platform_extra_uses_live_stats(clawbot_stats_env, monkeypatch) -> None:
    import hermes_cli.config as cfg_mod
    from gateway.platforms.clawbot.config import patch_clawbot_config
    from gateway.platforms.clawbot.stats import record_clawbot_received
    from hermes_cli.web_routes.oauth_messaging import _clawbot_platform_extra

    cfg_path = clawbot_stats_env / "config.yaml"
    cfg_path.write_text("platforms: {}\n", encoding="utf-8")
    monkeypatch.setattr(cfg_mod, "get_config_path", lambda: cfg_path)

    patch_clawbot_config(
        {
            "enabled": True,
            "bind_status": True,
            "token": "tok",
            "account_id": "acc",
            "bound_wxid": "wxid_x",
        }
    )
    record_clawbot_received()
    monkeypatch.setattr(
        "gateway.platforms.clawbot.ilink.clawbot_has_peer_session",
        lambda **kwargs: True,
    )
    extra = _clawbot_platform_extra()
    assert extra["stats"]["received"] == 1
    assert extra["session_ready"] is True
