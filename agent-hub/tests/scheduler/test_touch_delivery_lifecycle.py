from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from plugins.mxai.orchestrator.models import TaskStatus
from plugins.mxai.orchestrator.queue_manager import QueueManager
from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge
from plugins.mxai.scheduler.touch_delivery_service import (
    TouchDeliveryService,
    beijing_business_date,
)


def _reserve(service: TouchDeliveryService, *, suffix: str = "") -> dict:
    return service.reserve(
        profile_id="wechat",
        channel_account_id="acct",
        subtask_id=f"sub{suffix}",
        customer_identity_key=f"cid_v1_{suffix or 'one'}",
        business_date=beijing_business_date(),
        threshold_sec=60,
        silence_sec=120,
        last_inbound_at_snapshot="2026-07-14T00:00:00+00:00",
        identity_revision=1,
        decision_hash=f"hash{suffix}",
        identity_confidence="high",
    )


def _payload(delivery: dict, **extra) -> dict:
    payload = {
        "delivery_id": delivery["delivery_id"],
        "subtask_id": delivery["subtask_id"],
        "customer_identity_key": delivery["customer_identity_key"],
        "identity_revision": delivery["identity_revision"],
        "decision_hash": delivery["decision_hash"],
        "matched_threshold_sec": delivery["threshold_sec"],
        "silence_sec": delivery["silence_sec"],
        "recipient": "wxid-demo",
        "display_name": "演示客户",
        "message": "您好",
        "source": "manual",
        "recipient_locator_type": "wxid",
        "recipient_locator_masked": "wx***mo",
        "recipient_locator_value": "wxid-demo",
    }
    payload.update(extra)
    return payload


@pytest.fixture
def ready_queue(mxai_env: Path, monkeypatch: pytest.MonkeyPatch) -> QueueManager:
    del mxai_env
    queue = QueueManager()
    queue._work_armed = True
    queue._global_paused = False
    queue._agents_enabled["wechat"] = True
    monkeypatch.setattr(queue, "_rpa_online", lambda: True)
    monkeypatch.setattr(get_rpa_worker_bridge(), "is_connected", lambda: True)
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.queue_manager.check_execute",
        lambda *_args, **_kwargs: SimpleNamespace(allowed=True, reason=""),
    )
    monkeypatch.setattr(
        "plugins.mxai.orchestrator.queue_manager._read_rpa_integrate_settings",
        lambda: ("ws", ""),
    )
    return queue


@pytest.mark.parametrize(
    ("send_status", "expected_delivery", "expected_task"),
    [
        ("sent", "success", TaskStatus.DONE),
        ("not_sent", "failed", TaskStatus.FAILED),
        ("unknown", "uncertain", TaskStatus.FAILED),
    ],
)
def test_queue_maps_send_status_terminal(
    ready_queue: QueueManager,
    monkeypatch: pytest.MonkeyPatch,
    send_status: str,
    expected_delivery: str,
    expected_task: TaskStatus,
) -> None:
    service = TouchDeliveryService()
    delivery = _reserve(service, suffix=send_status)["delivery"]

    def execute(task, timeout=600.0, *, on_accepted=None):
        assert service.get(delivery["delivery_id"])["dispatch_state"] == "dispatching"
        on_accepted("exec-real-42")
        assert service.get(delivery["delivery_id"])["dispatch_state"] == "accepted"
        return {
            "send_status": send_status,
            "execution_id": "exec-real-42",
            "mode": "automan",
        }

    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge

    monkeypatch.setattr(get_rpa_worker_bridge(), "execute_via_worker", execute)
    task = ready_queue.enqueue(
        profile_id="wechat",
        name="定时触达",
        task_type="scheduled_msg",
        payload=_payload(delivery),
        skip_risk=True,
    )
    done = ready_queue.wait_task(task.task_id, timeout_sec=2)

    row = service.get(delivery["delivery_id"])
    assert done.status == expected_task
    assert row["status"] == expected_delivery, (done.steps, done.payload, row)
    assert row["execution_id"] == "exec-real-42"
    assert row["dispatch_state"] == "terminal"
    with service._connect() as conn:
        logs = conn.execute(
            """
            SELECT exec_status, task_id, op_object, display_name, fail_reason
            FROM work_logs WHERE delivery_id = ?
            """,
            (delivery["delivery_id"],),
        ).fetchall()
    assert len(logs) == 1
    assert logs[0]["task_id"] == task.task_id
    # CR-154：台账写客户名 + 话术；禁止 locator 原值（CR-155）
    assert logs[0]["op_object"] == "演示客户 · 您好"
    assert logs[0]["display_name"] == "演示客户"
    assert "wxid-demo" not in str(logs[0]["op_object"])
    assert "wx***mo" not in str(logs[0]["op_object"])


def test_sent_with_cleanup_failure_stays_success(
    ready_queue: QueueManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TouchDeliveryService()
    delivery = _reserve(service, suffix="cleanup")["delivery"]

    def execute(task, timeout=600.0, *, on_accepted=None):
        on_accepted("exec-cleanup")
        return {
            "send_status": "sent",
            "workflow_status": "failed",
            "cleanup_warning": "窗口最小化失败",
            "execution_id": "exec-cleanup",
        }

    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge

    monkeypatch.setattr(get_rpa_worker_bridge(), "execute_via_worker", execute)
    task = ready_queue.enqueue(
        profile_id="wechat",
        name="定时触达",
        task_type="scheduled_msg",
        payload=_payload(delivery),
        skip_risk=True,
    )
    done = ready_queue.wait_task(task.task_id, timeout_sec=2)
    assert done.status == TaskStatus.DONE
    assert service.get(delivery["delivery_id"])["status"] == "success"
    assert any(step["status"] == "warning" for step in done.steps)
    assert _reserve(service, suffix="cleanup")["reason"] == "already_success"


def test_structured_exception_preserves_accepted_evidence(
    ready_queue: QueueManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugins.mxai.rpa_worker.bridge import WorkflowExecutionError

    service = TouchDeliveryService()
    delivery = _reserve(service, suffix="structured-error")["delivery"]

    def execute(task, timeout=600.0, *, on_accepted=None):
        raise WorkflowExecutionError(
            "cleanup failed",
            outputs={"send_status": "sent"},
            execution_id="exec-error",
            workflow_status="failed",
        )

    monkeypatch.setattr(get_rpa_worker_bridge(), "execute_via_worker", execute)
    task = ready_queue.enqueue(
        profile_id="wechat",
        name="定时触达",
        task_type="scheduled_msg",
        payload=_payload(delivery),
        skip_risk=True,
    )
    done = ready_queue.wait_task(task.task_id, timeout_sec=2)
    row = service.get(delivery["delivery_id"])
    assert done.status == TaskStatus.DONE
    assert done.payload["result"]["execution_id"] == "exec-error"
    assert row["execution_id"] == "exec-error"
    assert row["status"] == "success"


def test_rejected_before_accepted_is_failed_and_retryable(
    ready_queue: QueueManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugins.mxai.rpa_worker.bridge import WorkflowExecutionError

    service = TouchDeliveryService()
    delivery = _reserve(service, suffix="rejected")["delivery"]

    def execute(task, timeout=600.0, *, on_accepted=None):
        raise WorkflowExecutionError(
            "no automan workflow",
            workflow_status="rejected",
            outcome_hint="failed",
        )

    monkeypatch.setattr(get_rpa_worker_bridge(), "execute_via_worker", execute)
    task = ready_queue.enqueue(
        profile_id="wechat",
        name="定时触达",
        task_type="scheduled_msg",
        payload=_payload(delivery),
        skip_risk=True,
    )
    done = ready_queue.wait_task(task.task_id, timeout_sec=2)
    row = service.get(delivery["delivery_id"])
    assert done.status == TaskStatus.FAILED
    assert row["status"] == "failed"
    assert row["fail_code"] == "rpa_not_sent"
    assert _reserve(service, suffix="rejected")["reserved"] is True


def test_transport_lost_before_accepted_is_uncertain(
    ready_queue: QueueManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from plugins.mxai.rpa_worker.bridge import WorkflowExecutionError

    service = TouchDeliveryService()
    delivery = _reserve(service, suffix="transport-lost")["delivery"]

    def execute(task, timeout=600.0, *, on_accepted=None):
        raise WorkflowExecutionError(
            "RPA worker disconnected",
            workflow_status="",
            outcome_hint="uncertain",
        )

    monkeypatch.setattr(get_rpa_worker_bridge(), "execute_via_worker", execute)
    task = ready_queue.enqueue(
        profile_id="wechat",
        name="定时触达",
        task_type="scheduled_msg",
        payload=_payload(delivery),
        skip_risk=True,
    )
    done = ready_queue.wait_task(task.task_id, timeout_sec=2)
    row = service.get(delivery["delivery_id"])
    assert done.status == TaskStatus.FAILED
    assert row["status"] == "uncertain"
    assert _reserve(service, suffix="transport-lost")["reason"] == "uncertain"


def test_dispatch_preflight_failure_has_no_worklog(
    ready_queue: QueueManager,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TouchDeliveryService()
    delivery = _reserve(service, suffix="preflight")["delivery"]
    called: list[bool] = []
    from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge

    monkeypatch.setattr(
        get_rpa_worker_bridge(),
        "execute_via_worker",
        lambda *a, **k: called.append(True),
    )
    task = ready_queue.enqueue(
        profile_id="wechat",
        name="定时触达",
        task_type="scheduled_msg",
        payload=_payload(delivery, decision_hash="changed"),
        skip_risk=True,
    )
    done = ready_queue.wait_task(task.task_id, timeout_sec=2)

    assert done.status == TaskStatus.DONE
    assert done.payload["result"]["skipped_before_dispatch"] is True
    assert service.get(delivery["delivery_id"])["fail_code"] == "dispatch_preflight_changed"
    assert called == []
    with service._connect() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM work_logs WHERE delivery_id = ?",
            (delivery["delivery_id"],),
        ).fetchone()[0]
    assert count == 0


def test_startup_recovery_matrix(mxai_env: Path) -> None:
    del mxai_env
    service = TouchDeliveryService()
    states: dict[str, str] = {}
    for state in ("preparing", "queued", "dispatching", "accepted"):
        delivery = _reserve(service, suffix=state)["delivery"]
        delivery_id = delivery["delivery_id"]
        if state != "preparing":
            service.mark_queued(delivery_id, f"task-{state}")
        if state in {"dispatching", "accepted"}:
            service.mark_dispatching(delivery_id, f"task-{state}")
        if state == "accepted":
            service.mark_accepted(delivery_id, f"task-{state}", "exec-accepted")
        states[state] = delivery_id

    report = service.recover_incomplete(lambda _eid: None, accepted_timeout_sec=0)
    assert report == {"failed": 2, "uncertain": 2, "success": 0, "pending": 0}
    assert service.get(states["preparing"])["status"] == "failed"
    assert service.get(states["queued"])["fail_code"] == "recovered_before_dispatch"
    assert service.get(states["dispatching"])["status"] == "uncertain"
    assert service.get(states["accepted"])["status"] == "uncertain"


def test_accepted_recovery_waits_for_timeout(mxai_env: Path) -> None:
    del mxai_env
    service = TouchDeliveryService()
    delivery = _reserve(service, suffix="accepted-running")["delivery"]
    delivery_id = delivery["delivery_id"]
    service.mark_queued(delivery_id, "task-running")
    service.mark_dispatching(delivery_id, "task-running")
    service.mark_accepted(delivery_id, "task-running", "exec-running")

    pending = service.recover_incomplete(
        lambda _eid: {"status": "running", "outputs": {}},
    )
    assert pending == {"failed": 0, "uncertain": 0, "success": 0, "pending": 1}
    assert service.get(delivery_id)["dispatch_state"] == "accepted"

    timed_out = service.recover_incomplete(
        lambda _eid: {"status": "running", "outputs": {}},
        accepted_timeout_sec=0,
    )
    assert timed_out == {"failed": 0, "uncertain": 1, "success": 0, "pending": 0}
    assert service.get(delivery_id)["status"] == "uncertain"


def test_accepted_terminal_recovery_sanitizes_error(mxai_env: Path) -> None:
    del mxai_env
    service = TouchDeliveryService()
    delivery = _reserve(service, suffix="accepted-terminal")["delivery"]
    delivery_id = delivery["delivery_id"]
    service.mark_queued(delivery_id, "task-terminal")
    service.mark_dispatching(delivery_id, "task-terminal")
    service.mark_accepted(delivery_id, "task-terminal", "exec-terminal")

    report = service.recover_incomplete(
        lambda _eid: {
            "status": "failed",
            "outputs": {},
            "error": "wxid-secret 原消息正文",
        },
    )
    assert report == {"failed": 0, "uncertain": 1, "success": 0, "pending": 0}
    row = service.get(delivery_id)
    assert row["status"] == "uncertain"
    assert row["fail_reason"] == "AutoMan 发送结果无法确认"

