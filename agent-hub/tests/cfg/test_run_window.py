"""run_window 校验单测 — CR-132 / CR-133."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import core.timeutil as tu
from plugins.mxai.cfg.run_window import (
    is_manual_task_payload,
    task_respects_run_window,
    within_hhmm_window,
    within_workbench_run_window,
)

_BJ = timezone(timedelta(hours=8))


def test_within_hhmm_window_same_day() -> None:
    assert within_hhmm_window("09:00", "21:00", "12:00") is True
    assert within_hhmm_window("09:00", "21:00", "08:59") is False
    assert within_hhmm_window("12:00", "23:09", "11:58") is False
    assert within_hhmm_window("12:00", "23:09", "12:00") is True


def test_within_hhmm_window_cross_midnight() -> None:
    assert within_hhmm_window("22:00", "06:00", "23:30") is True
    assert within_hhmm_window("22:00", "06:00", "12:00") is False
    assert within_hhmm_window("22:00", "06:00", "05:30") is True


def test_empty_window_means_unrestricted() -> None:
    assert within_hhmm_window("", "21:00", "12:00") is True
    assert within_hhmm_window("09:00", "", "12:00") is True


def test_within_workbench_run_window_comment_collect() -> None:
    wb = {"comment_collect": {"run_window": {"start": "12:00", "end": "23:00"}}}
    ok, start, end = within_workbench_run_window(wb, "comment_collect", now_hm="11:58")
    assert ok is False and start == "12:00" and end == "23:00"
    ok2, _, _ = within_workbench_run_window(wb, "comment_collect", now_hm="12:01")
    assert ok2 is True


def test_comment_collect_not_gated_by_run_window_drain(monkeypatch) -> None:
    """公域采集调度走 public_round_scheduler；drain 不再用 run_window."""
    wb = {"comment_collect": {"run_window": {"start": "12:00", "end": "23:00"}}}
    monkeypatch.setattr(
        "plugins.mxai.cfg.manager.ConfigManager.get",
        lambda: type("M", (), {"read": lambda _self, _k: wb})(),
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 7, 11, 58, tzinfo=_BJ))
    assert is_manual_task_payload({"source": "manual"}) is True
    assert task_respects_run_window(
        "comment_collect", "douyin", {"source": "manual"}
    ) is True
    assert task_respects_run_window(
        "comment_collect", "douyin", {"source": "bootstrap"}
    ) is True


def test_add_friends_respects_window(monkeypatch) -> None:
    wb = {
        "add_friends": {"run_window": {"start": "09:00", "end": "18:00"}},
        "batch_add": {"run_window": {"start": "09:00", "end": "18:00"}},
    }
    monkeypatch.setattr(
        "plugins.mxai.api.agents._read_workbench",
        lambda _agent: wb,
    )
    monkeypatch.setattr(tu, "beijing_now", lambda: datetime(2026, 7, 7, 20, 0, tzinfo=_BJ))
    assert task_respects_run_window("add_friends", "wechat", {"source": "bootstrap"}) is False
    assert task_respects_run_window("add_friends", "wechat", {"source": "manual"}) is True
    # 企微加客户门闸读 batch_add.run_window（非 add_friends）
    assert task_respects_run_window("add_contacts", "qiyeweixin", {}) is False
