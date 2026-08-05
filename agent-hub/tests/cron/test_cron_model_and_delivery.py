"""Cron model resolution and direct-bot delivery under profile scope."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli.config import load_config


@pytest.fixture
def hub_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "hub"
    root.mkdir()
    (root / "config.yaml").write_text(
        "model:\n  default: root-model\n",
        encoding="utf-8",
    )
    assistant = root / "profiles" / "assistant"
    assistant.mkdir(parents=True)
    (assistant / "config.yaml").write_text("agent:\n  max_turns: 5\n", encoding="utf-8")
    monkeypatch.setenv("HUB_DATA_DIR", str(root))
    return root


def test_resolve_cron_model_inherits_root_default(hub_root: Path) -> None:
    from agent.profile_scope import hermes_profile_scope
    from cron.scheduler import _resolve_cron_model

    assistant_home = hub_root / "profiles" / "assistant"
    with hermes_profile_scope(assistant_home):
        model = _resolve_cron_model({}, load_config())

    assert model == "root-model"


def test_resolve_cron_model_falls_back_to_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron.scheduler import _resolve_cron_model

    monkeypatch.delenv("HERMES_MODEL", raising=False)
    monkeypatch.setattr(
        "agent.auxiliary_client._read_main_model",
        lambda: "",
    )
    monkeypatch.setattr(
        "cron.scheduler._resolve_cron_model_from_inventory",
        lambda: "inventory-model",
    )

    assert _resolve_cron_model({}, {"model": ""}) == "inventory-model"


def test_deliver_clawbot_when_gateway_platform_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    from cron import scheduler as sched
    from gateway.config import GatewayConfig, Platform, PlatformConfig

    gw = GatewayConfig()
    gw.platforms[Platform.CLAWBOT] = PlatformConfig(enabled=False)

    monkeypatch.setattr(sched, "_platform_delivery_ready", lambda _name: True)
    monkeypatch.setattr(
        sched,
        "_synthesize_direct_bot_pconfig",
        lambda _name: PlatformConfig(enabled=True, token="tok", extra={"user_id": "wx-1"}),
    )
    monkeypatch.setattr(
        "gateway.config.load_gateway_config",
        lambda: gw,
    )
    monkeypatch.setattr(
        "cron.scheduler.asyncio.run",
        lambda coro: (coro.close(), {"success": True})[1],
    )

    err = sched._deliver_result(
        {"id": "abc123456789", "name": "t", "deliver": "clawbot"},
        "hello",
        adapters=None,
        loop=None,
    )
    assert err is None
