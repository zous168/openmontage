"""Local guard MxAI WS path tests."""

from __future__ import annotations

from starlette.datastructures import Headers

from hermes_cli.dashboard_auth.local_guard import (
    is_mxai_websocket_path,
    is_mxai_ws_local_upgrade,
)


def _request(path: str, *, client_host: str = "127.0.0.1", upgrade: bool = True):
    from unittest.mock import MagicMock

    headers = Headers({"upgrade": "websocket"} if upgrade else {})
    request = MagicMock()
    request.url.path = path
    request.headers = headers
    request.client = MagicMock(host=client_host)
    return request


def test_mxai_ws_paths():
    assert is_mxai_websocket_path("/api/v1/ws")
    assert is_mxai_websocket_path("/api/plugins/mxai/ws")
    assert not is_mxai_websocket_path("/api/plugins/mxai/queue/summary")


def test_mxai_ws_local_upgrade_localhost():
    assert is_mxai_ws_local_upgrade(_request("/api/v1/ws"))
    assert not is_mxai_ws_local_upgrade(_request("/api/v1/ws", upgrade=False))
    assert not is_mxai_ws_local_upgrade(_request("/api/v1/ws", client_host="192.168.1.1"))
