"""FR-CHAT-07：TurnMutationJournal 可逆 cfg 回滚."""

from __future__ import annotations

import copy

from plugins.mxai.agents.turn_journal import TurnMutationJournal, record_cfg_before


def test_record_before_first_wins_and_rollback(monkeypatch, tmp_path):
    j = TurnMutationJournal()
    restored: list[tuple[str, dict]] = []
    synced: list[str] = []

    class _FakeCM:
        def replace(self, domain_id, payload):
            restored.append((domain_id, copy.deepcopy(payload)))

    class _FakeReg:
        @staticmethod
        def get(domain_id):
            return object()

    monkeypatch.setattr(
        "plugins.mxai.cfg.manager.ConfigManager.get",
        lambda: _FakeCM(),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.registry.ConfigRegistry.get",
        _FakeReg.get,
    )
    monkeypatch.setattr(
        "plugins.mxai.scheduler.cron.sync_profile_scheduler_jobs",
        lambda module: synced.append(module),
    )

    tid = j.begin(hermes_session_id="mxai-assistant-chat")
    j.bind_context(tid)
    before = {"add_friends": {"run_window": {"start": "10:00", "end": "12:00"}}}
    j.record_before("wechat", "workbench", before)
    # 二次写入不应覆盖 before
    j.record_before(
        "wechat",
        "workbench",
        {"add_friends": {"run_window": {"start": "09:00", "end": "16:00"}}},
    )

    rb = j.rollback(tid)
    assert rb["reverted"] is True
    assert restored == [("agent.wechat.workbench", before)]
    assert synced == ["wechat"]


def test_record_cfg_before_uses_active_turn_without_contextvar(monkeypatch):
    """MCP 工具线程无 ContextVar 时回落到 active_turn_id."""
    from plugins.mxai.agents import turn_journal as tj

    j = TurnMutationJournal()
    monkeypatch.setattr(tj, "_JOURNAL", j)
    tid = j.begin()
    # 不 bind_context，模拟工具线程
    record_cfg_before("wechat", "workbench", {"x": 1})
    state = j.get(tid)
    assert state is not None
    assert "agent.wechat.workbench" in state.entries


def test_assistant_flight_single_inflight():
    from plugins.mxai.agents.turn_journal import ASSISTANT_FLIGHT_KEY, TurnMutationJournal

    j = TurnMutationJournal()
    t1 = j.begin(flight_key=ASSISTANT_FLIGHT_KEY)
    assert t1 is not None
    assert j.is_flight_busy()
    t2 = j.begin(flight_key=ASSISTANT_FLIGHT_KEY)
    assert t2 is None
    j.end(t1)
    assert not j.is_flight_busy()
    t3 = j.begin(flight_key=ASSISTANT_FLIGHT_KEY)
    assert t3 is not None
    j.end(t3)