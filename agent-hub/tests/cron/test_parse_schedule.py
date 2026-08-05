"""Schedule parsing edge cases for cron jobs."""

from __future__ import annotations

from cron.jobs import parse_schedule


def test_parse_schedule_accepts_once_in_display_roundtrip() -> None:
    parsed = parse_schedule("once in 5m")
    assert parsed["kind"] == "once"
    assert parsed["display"] == "once in 5m"


def test_parse_schedule_duration_one_shot() -> None:
    parsed = parse_schedule("5m")
    assert parsed["kind"] == "once"
    assert parsed["display"] == "once in 5m"
