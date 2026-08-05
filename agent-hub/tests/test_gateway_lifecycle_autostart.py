"""Gateway autostart must not run before hub API port is serving."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from hermes_cli import gateway_lifecycle as gl


def test_hub_listen_endpoint_defaults():
    with patch.dict("os.environ", {}, clear=True):
        assert gl.hub_listen_endpoint() == ("127.0.0.1", 8642)


def test_hub_listen_endpoint_maps_wildcard_to_loopback():
    with patch.dict("os.environ", {"HUB_API_HOST": "0.0.0.0", "HUB_API_PORT": "9000"}):
        assert gl.hub_listen_endpoint() == ("127.0.0.1", 9000)


def test_wait_for_hub_serving_returns_false_when_cancelled():
    cancel = asyncio.Event()
    cancel.set()
    result = asyncio.run(
        gl.wait_for_hub_serving(cancel, timeout=1.0, poll_interval=0.01)
    )
    assert result is False


def test_wait_for_hub_serving_returns_true_when_port_ready():
    cancel = asyncio.Event()
    with patch.object(gl, "hub_listen_ready", side_effect=[False, True]):
        result = asyncio.run(
            gl.wait_for_hub_serving(cancel, timeout=1.0, poll_interval=0.01)
        )
    assert result is True


def test_gateway_autostart_enabled_by_default(monkeypatch):
    monkeypatch.delenv("HERMES_GATEWAY_AUTOSTART", raising=False)
    assert gl.is_gateway_autostart_enabled() is True


def test_gateway_autostart_can_disable(monkeypatch):
    monkeypatch.setenv("HERMES_GATEWAY_AUTOSTART", "0")
    assert gl.is_gateway_autostart_enabled() is False
