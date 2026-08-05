"""Gateway pid/lock probe diagnostics (hub autostart logging)."""

from __future__ import annotations

import json

from gateway import status as gw_status


def test_probe_accepts_frozen_gateway_run_argv(tmp_path, monkeypatch) -> None:
    pid_path = tmp_path / "gateway.pid"
    lock_path = tmp_path / "gateway.lock"
    live_pid = 51515

    lock_path.write_text(
        json.dumps(
            {
                "pid": live_pid,
                "kind": "hermes-gateway",
                "argv": ["gateway.run"],
                "start_time": None,
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(gw_status, "_get_pid_path", lambda: pid_path)
    monkeypatch.setattr(gw_status, "_get_gateway_lock_path", lambda _p=None: lock_path)
    monkeypatch.setattr(gw_status, "is_gateway_runtime_lock_active", lambda _p=None: True)
    monkeypatch.setattr(gw_status, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(gw_status, "_looks_like_gateway_process", lambda _pid: False)
    monkeypatch.setattr(gw_status, "_get_process_start_time", lambda _pid: None)

    probe = gw_status.probe_running_pid()
    assert probe["status"] == "running"
    assert probe["candidate_pid"] == live_pid
    assert probe["matched_via"] == "lock_file"
    assert gw_status.get_running_pid() == live_pid


def test_probe_lock_inactive_cleans_stale(tmp_path, monkeypatch) -> None:
    pid_path = tmp_path / "gateway.pid"
    lock_path = tmp_path / "gateway.lock"
    pid_path.write_text('{"pid": 1, "kind": "hermes-gateway"}', encoding="utf-8")
    lock_path.write_text('{"pid": 1}', encoding="utf-8")

    monkeypatch.setattr(gw_status, "_get_pid_path", lambda: pid_path)
    monkeypatch.setattr(gw_status, "_get_gateway_lock_path", lambda _p=None: lock_path)
    monkeypatch.setattr(gw_status, "is_gateway_runtime_lock_active", lambda _p=None: False)

    probe = gw_status.probe_running_pid()
    assert probe["status"] == "lock_inactive"
    assert not pid_path.exists()
    assert not lock_path.exists()


def test_probe_identity_mismatch_logged(tmp_path, monkeypatch) -> None:
    pid_path = tmp_path / "gateway.pid"
    lock_path = tmp_path / "gateway.lock"
    lock_path.write_text(
        json.dumps({"pid": 99, "kind": "hermes-gateway", "argv": ["unknown-entry"]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(gw_status, "_get_pid_path", lambda: pid_path)
    monkeypatch.setattr(gw_status, "_get_gateway_lock_path", lambda _p=None: lock_path)
    monkeypatch.setattr(gw_status, "is_gateway_runtime_lock_active", lambda _p=None: True)
    monkeypatch.setattr(gw_status, "_pid_exists", lambda _pid: True)
    monkeypatch.setattr(gw_status, "_looks_like_gateway_process", lambda _pid: False)
    monkeypatch.setattr(gw_status, "_get_process_start_time", lambda _pid: None)

    probe = gw_status.probe_running_pid()
    assert probe["status"] == "lock_held_unidentified"
    assert any(c["code"] == "identity_mismatch" for c in probe["checks"])
    assert gw_status.get_running_pid() is None
    assert pid_path.exists() is False  # pid file never created
    assert lock_path.exists()  # must not delete lock while held
