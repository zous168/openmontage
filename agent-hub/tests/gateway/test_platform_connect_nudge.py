"""Platform hot-connect nudge file tests."""

from __future__ import annotations

import json

from gateway.platform_connect_nudge import (
    consume_platform_connect_nudges,
    write_platform_connect_nudge,
)


def test_write_and_consume_platform_connect_nudge(tmp_path, monkeypatch) -> None:
    device = tmp_path / "device"
    device.mkdir()
    nudge_file = device / "platform_connect_nudges.json"
    monkeypatch.setattr(
        "gateway.platform_connect_nudge._nudge_path",
        lambda: nudge_file,
    )

    write_platform_connect_nudge("clawbot")
    assert nudge_file.is_file()
    payload = json.loads(nudge_file.read_text(encoding="utf-8"))
    assert "clawbot" in payload

    nudged = consume_platform_connect_nudges()
    assert nudged == {"clawbot"}
    assert not nudge_file.is_file()

    assert consume_platform_connect_nudges() == set()
