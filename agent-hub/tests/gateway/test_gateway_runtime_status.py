"""Gateway runtime status ownership tests."""

from __future__ import annotations

import json

from gateway import status as gw_status


def test_hub_platform_write_is_ignored_when_gateway_live(tmp_path, monkeypatch) -> None:
    pid_path = tmp_path / "gateway.pid"
    state_path = tmp_path / "gateway_state.json"
    lock_path = tmp_path / "gateway.lock"

    live_pid = 424242
    state_path.write_text(
        json.dumps(
            {
                "pid": live_pid,
                "kind": "hermes-gateway",
                "argv": ["gateway", "run"],
                "gateway_state": "running",
                "platforms": {"api_server": {"state": "connected"}},
            }
        ),
        encoding="utf-8",
    )
    pid_path.write_text(json.dumps({"pid": live_pid, "kind": "hermes-gateway"}), encoding="utf-8")
    lock_path.write_text(json.dumps({"pid": live_pid, "kind": "hermes-gateway"}), encoding="utf-8")

    monkeypatch.setattr(gw_status, "_get_pid_path", lambda: pid_path)
    monkeypatch.setattr(gw_status, "_get_runtime_status_path", lambda: state_path)
    monkeypatch.setattr(gw_status, "_get_gateway_lock_path", lambda _p=None: lock_path)
    monkeypatch.setattr(gw_status, "get_running_pid", lambda *a, **k: live_pid)
    monkeypatch.setattr(gw_status, "_looks_like_gateway_process", lambda _pid: False)
    monkeypatch.setattr(gw_status.os, "getpid", lambda: 99999)

    gw_status.write_runtime_status(
        platform="clawbot",
        platform_state="connecting",
        error_code=None,
        error_message=None,
    )

    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["pid"] == live_pid
    assert "clawbot" not in payload.get("platforms", {})
    assert payload["platforms"]["api_server"]["state"] == "connected"


def test_runtime_status_owned_by_live_gateway() -> None:
    assert gw_status.runtime_status_owned_by_live_gateway({"pid": 1}) is False
