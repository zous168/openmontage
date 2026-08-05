"""Unified WS endpoint tests."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.api.ws import mxai_unified_ws
from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge, reset_rpa_worker_bridge


@pytest.fixture
def ws_client():
    reset_rpa_worker_bridge()
    app = FastAPI()
    app.add_api_websocket_route("/api/v1/ws", mxai_unified_ws)
    with TestClient(app) as client:
        yield client
    reset_rpa_worker_bridge()


def test_v1_ws_gui_ping(ws_client: TestClient):
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        ws.send_text("ping")
        frame = json.loads(ws.receive_text())
        assert frame.get("event") == "pong"


def test_v1_ws_rpa_worker_hello(ws_client: TestClient):
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "role": "rpa_worker",
                    "type": "hello",
                    "worker_id": "test-v1",
                    "channels": ["wechat"],
                }
            )
        )
        ack = json.loads(ws.receive_text())
        assert ack.get("type") == "hello.ack"
        assert get_rpa_worker_bridge().is_connected()


def test_v1_ws_routes_workflow_accepted(
    ws_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
):
    accepted: list[dict] = []
    monkeypatch.setattr(
        get_rpa_worker_bridge(),
        "on_workflow_accepted",
        lambda data: accepted.append(dict(data)),
    )
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        ws.send_text(
            json.dumps(
                {
                    "role": "rpa_worker",
                    "type": "hello",
                    "worker_id": "test-v1",
                    "channels": ["wechat"],
                }
            )
        )
        ws.receive_text()
        ws.send_text(
            json.dumps(
                {
                    "type": "workflow.accepted",
                    "data": {
                        "request_id": "task-1",
                        "instance_id": "instance-real",
                    },
                }
            )
        )
    assert accepted == [
        {"request_id": "task-1", "instance_id": "instance-real"}
    ]
