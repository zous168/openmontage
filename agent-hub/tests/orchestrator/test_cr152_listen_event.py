"""CR-152 · listen-event 入队与 ①/② 编排."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from plugins.mxai.api.deps import get_queue
from plugins.mxai.conversations.service import set_conversation_mode
from plugins.mxai.orchestrator.inbound_listen_coord import reset_inbound_listen_coord
from plugins.mxai.orchestrator.models import TaskStatus


@pytest.fixture(autouse=True)
def _reset_coord() -> None:
    reset_inbound_listen_coord()


def _enable_wechat() -> None:
    q = get_queue()
    q.set_agent_enabled("wechat", True)


def test_listen_event_queues_inbound_reply(mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_wechat()
    stops: list[tuple[str, list[str] | None]] = []
    mock_bridge = MagicMock()
    mock_bridge.send_monitor = lambda action, channels=None: stops.append((action, channels)) or True
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: mock_bridge,
    )

    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={
            "sender": "peer_a",
            "message": "你好",
            "message_id": "evt-1",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "queued"
    assert body["task_id"]
    assert body["profile_id"] == "wechat"
    assert ("stop", ["weixin_listen"]) in stops

    task = get_queue().get_task(body["task_id"])
    assert task is not None
    assert task.task_type == "inbound_reply"
    assert task.payload.get("sender") == "peer_a"
    assert task.payload.get("source") == "automan_listen"


def test_listen_event_skips_public_agent(mxai_client: TestClient) -> None:
    res = mxai_client.post(
        "/api/plugins/mxai/agents/douyin/listen-event",
        json={"sender": "u1", "message": "hi", "message_id": "m1"},
    )
    assert res.status_code == 404


def test_listen_event_skips_takeover(mxai_client: TestClient, mxai_env, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_wechat()
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    peer = "takeover_peer"
    set_conversation_mode("wechat", f"C-{peer}", "takeover", data_dir=mxai_env)
    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={"sender": peer, "message": "新问题", "message_id": "m-takeover"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "skipped"
    assert res.json()["reason"] == "takeover"


def test_listen_event_duplicate_message_id(mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_wechat()
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    payload = {"sender": "dup_peer", "message": "a", "message_id": "same-id"}
    r1 = mxai_client.post("/api/plugins/mxai/agents/wechat/listen-event", json=payload)
    assert r1.status_code == 200
    assert r1.json()["status"] == "queued"
    r2 = mxai_client.post("/api/plugins/mxai/agents/wechat/listen-event", json=payload)
    assert r2.status_code == 200
    assert r2.json()["status"] == "skipped"
    assert r2.json()["reason"] == "duplicate"


def test_listen_event_conversation_inflight(mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable_wechat()
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    r1 = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={"sender": "same_peer", "message": "1", "message_id": "id-1"},
    )
    assert r1.json()["status"] == "queued"
    r2 = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={"sender": "same_peer", "message": "2", "message_id": "id-2"},
    )
    assert r2.json()["status"] == "skipped"
    assert r2.json()["reason"] == "conversation_inflight"


def test_resume_listen_after_inbound_reply_terminal(
    mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    q = get_queue()
    q.arm_work()
    q.set_global_pause(False)
    q.set_agent_enabled("wechat", True)
    monkeypatch.setattr(
        "plugins.mxai.cfg.run_enabled.is_run_enabled",
        lambda pid: pid == "wechat",
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.module_enabled.read_module_enabled",
        lambda pid, mid: mid == "inbound_reply",
    )

    starts: list[tuple[str, list[str] | None]] = []
    mock_bridge = MagicMock()
    mock_bridge.send_monitor = lambda action, channels=None: starts.append((action, channels)) or True
    mock_bridge.is_connected = lambda: True
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: mock_bridge,
    )

    from plugins.mxai.orchestrator.inbound_listen_coord import mark_channel_replying

    mark_channel_replying("wechat")
    task = q.enqueue(
        profile_id="wechat",
        name="t",
        task_type="inbound_reply",
        payload={"sender": "p1", "message": "hi", "hub_reply": {"text": "回"}},
    )
    # 模拟 drain 完成（mxai_client fixture 会真跑 handler；此处直接走 finally 路径）
    with q._mutex:
        t = q._tasks[task.task_id]
        t.status = TaskStatus.DONE
    q._maybe_resume_inbound_listen(t)

    assert q.count_inbound_reply_in_flight("wechat") == 0
    assert ("start", ["weixin_listen"]) in starts


def test_resume_listen_blocked_when_three_gates_closed(
    mxai_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """三门任一关（此处未开工）→ 禁止恢复听，即使 monitor 会话残留。"""
    from plugins.mxai.orchestrator.inbound_listen_coord import (
        mark_channel_replying,
        mark_monitor_sessions,
    )

    q = get_queue()
    q.set_agent_enabled("wechat", True)
    mark_monitor_sessions(["wechat"])
    q.disarm_work()
    q.set_global_pause(True)
    monkeypatch.setattr(q, "_drain_rpa", lambda: None)
    monkeypatch.setattr(
        "plugins.mxai.cfg.run_enabled.is_run_enabled",
        lambda pid: True,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.module_enabled.read_module_enabled",
        lambda pid, mid: True,
    )

    starts: list[tuple[str, list[str] | None]] = []
    mock_bridge = MagicMock()
    mock_bridge.send_monitor = lambda action, channels=None: starts.append((action, channels)) or True
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: mock_bridge,
    )

    mark_channel_replying("wechat")
    task = q.enqueue(
        profile_id="wechat",
        name="t",
        task_type="inbound_reply",
        payload={"sender": "p1", "message": "hi", "hub_reply": {"text": "回"}},
        bypass_work_armed=True,
    )
    with q._mutex:
        t = q._tasks[task.task_id]
        t.status = TaskStatus.DONE
    q._maybe_resume_inbound_listen(t)

    assert all(a != "start" for a, _ in starts)


def test_work_not_started_409(mxai_client: TestClient) -> None:
    get_queue().disarm_work()
    get_queue().set_agent_enabled("wechat", True)
    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={"sender": "x", "message": "y", "message_id": "z"},
    )
    assert res.status_code == 409


def test_listen_event_null_message_id_coerced(
    mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """automan 变量未解析时 message_id=null 不得 422，应入队."""
    _enable_wechat()
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={
            "sender": "__listen_signal__",
            "message": "event_triggered",
            "message_id": None,
            "source": "automan_listen",
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == "queued"
    assert body["task_id"]
    task = get_queue().get_task(body["task_id"])
    assert task is not None
    assert task.task_type == "inbound_reply"
    mid = str((task.payload or {}).get("message_id") or "")
    assert mid.startswith("sig_")


def test_listen_signal_lock_released_after_bind_rewrites_sender(
    mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """signal 加锁 → /inbound bind 改写 sender → 终态须释放占位锁，第二轮可再 queued."""
    _enable_wechat()
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.run_enabled.is_run_enabled",
        lambda pid: pid == "wechat",
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.module_enabled.read_module_enabled",
        lambda pid, mid: mid == "inbound_reply",
    )
    q = get_queue()
    r1 = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={
            "sender": "__listen_signal__",
            "message": "event_triggered",
            "message_id": "sig-lock-1",
            "source": "automan_listen",
        },
    )
    assert r1.json()["status"] == "queued"
    tid1 = r1.json()["task_id"]
    t1 = q.get_task(tid1)
    assert t1 is not None
    assert t1.payload.get("session_lock_sender") == "__listen_signal__"
    assert t1.payload.get("sender") == "__listen_signal__"

    with q._mutex:
        t1.status = TaskStatus.RUNNING
    bound = q.bind_inbound_turn_to_listen_reply(
        "wechat",
        sender="真实客户甲",
        message="你好",
        reply={"source": "faq", "text": "您好"},
    )
    assert bound == tid1
    t1 = q.get_task(tid1)
    assert t1 is not None
    assert t1.payload.get("sender") == "真实客户甲"
    assert t1.payload.get("session_lock_sender") == "__listen_signal__"

    with q._mutex:
        t1.status = TaskStatus.DONE
    q._maybe_resume_inbound_listen(t1)

    r2 = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={
            "sender": "__listen_signal__",
            "message": "event_triggered",
            "message_id": "sig-lock-2",
            "source": "automan_listen",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "queued", r2.json()
    assert r2.json()["task_id"] != tid1


def test_listen_event_empty_message_id_unique_across_cycles(
    mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空 message_id 用 UUID：② 终态后再 signal 须再次 queued（严格串行下一轮）."""
    _enable_wechat()
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.run_enabled.is_run_enabled",
        lambda pid: pid == "wechat",
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.module_enabled.read_module_enabled",
        lambda pid, mid: mid == "inbound_reply",
    )
    payload = {
        "sender": "__listen_signal__",
        "message": "event_triggered",
        "message_id": "",
        "source": "automan_listen",
    }
    q = get_queue()
    r1 = mxai_client.post("/api/plugins/mxai/agents/wechat/listen-event", json=payload)
    assert r1.json()["status"] == "queued"
    tid1 = r1.json()["task_id"]
    t1 = q.get_task(tid1)
    assert t1 is not None
    mid1 = str((t1.payload or {}).get("message_id") or "")
    assert mid1.startswith("sig_")

    with q._mutex:
        t1.status = TaskStatus.DONE
    q._maybe_resume_inbound_listen(t1)

    r2 = mxai_client.post("/api/plugins/mxai/agents/wechat/listen-event", json=payload)
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "queued", r2.json()
    tid2 = r2.json()["task_id"]
    assert tid2 != tid1
    t2 = q.get_task(tid2)
    assert t2 is not None
    mid2 = str((t2.payload or {}).get("message_id") or "")
    assert mid2.startswith("sig_") and mid1 != mid2


def test_listen_event_qiyeweixin_empty_message_id_queues(
    mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """企微与个微同构：空 message_id signal 可入队."""
    q = get_queue()
    q.set_agent_enabled("qiyeweixin", True)
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.module_enabled.read_module_enabled",
        lambda pid, mid: pid == "qiyeweixin" and mid == "inbound_reply",
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/qiyeweixin/listen-event",
        json={
            "sender": "__listen_signal__",
            "message": "event_triggered",
            "message_id": None,
            "source": "automan_listen",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["status"] == "queued"
    task = q.get_task(res.json()["task_id"])
    assert task is not None
    assert str((task.payload or {}).get("message_id") or "").startswith("sig_")


def test_listen_event_blocked_when_paused_without_monitor_session(
    mxai_client: TestClient,
) -> None:
    """已开工但用户暂停、且无 monitor 会话时，listen-event 不得入队。"""
    q = get_queue()
    q.arm_work()
    q.set_global_pause(True)
    q.set_agent_enabled("wechat", True)
    from plugins.mxai.orchestrator.inbound_listen_coord import clear_monitor_sessions

    clear_monitor_sessions()
    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={"sender": "paused_peer", "message": "hi", "message_id": "paused-1"},
    )
    assert res.status_code == 409


def test_listen_event_with_monitor_session_when_fail_closed(
    mxai_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """device auth fail-closed 后 automan ① 仍可 listen-event 入队 ②."""
    from plugins.mxai.orchestrator.inbound_listen_coord import mark_monitor_sessions

    _enable_wechat()
    mark_monitor_sessions(["wechat"])
    q = get_queue()
    q.fail_closed_disarm()
    assert q.is_work_armed() is False
    assert q.is_global_paused() is True

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: MagicMock(send_monitor=lambda *a, **k: True),
    )
    res = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/listen-event",
        json={"sender": "fc_peer", "message": "hi", "message_id": "fc-1"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "queued"
    task = q.get_task(body["task_id"])
    assert task is not None
    assert task.task_type == "inbound_reply"


def test_resume_listen_when_fail_closed_but_monitor_session(
    mxai_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """fail-closed（G1 关）即使 monitor 会话残留，也不得恢复听。"""
    from plugins.mxai.orchestrator.inbound_listen_coord import mark_channel_replying, mark_monitor_sessions

    q = get_queue()
    q.set_agent_enabled("wechat", True)
    mark_monitor_sessions(["wechat"])
    q.fail_closed_disarm()
    monkeypatch.setattr(q, "_drain_rpa", lambda: None)
    monkeypatch.setattr(
        "plugins.mxai.cfg.run_enabled.is_run_enabled",
        lambda pid: True,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.module_enabled.read_module_enabled",
        lambda pid, mid: True,
    )

    starts: list[tuple[str, list[str] | None]] = []
    mock_bridge = MagicMock()
    mock_bridge.send_monitor = lambda action, channels=None: starts.append((action, channels)) or True
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.get_rpa_worker_bridge",
        lambda: mock_bridge,
    )

    mark_channel_replying("wechat")
    task = q.enqueue(
        profile_id="wechat",
        name="t",
        task_type="inbound_reply",
        payload={"sender": "p1", "message": "hi", "hub_reply": {"text": "回"}},
        bypass_work_armed=True,
    )
    with q._mutex:
        t = q._tasks[task.task_id]
        t.status = TaskStatus.DONE
    q._maybe_resume_inbound_listen(t)

    assert all(a != "start" for a, _ in starts)
