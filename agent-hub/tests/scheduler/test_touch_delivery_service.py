from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from plugins.mxai.scheduler.touch_delivery_service import (
    TouchDeliveryService,
    beijing_business_date,
)


def _reserve(service: TouchDeliveryService, **overrides):
    biz = beijing_business_date()
    values = {
        "profile_id": "wechat",
        "channel_account_id": "acct",
        "subtask_id": "sub-1",
        "customer_identity_key": "cid_v1_test",
        "business_date": biz,
        "threshold_sec": 60,
        "silence_sec": 120,
        "last_inbound_at_snapshot": f"{biz}T00:00:00+00:00",
        "identity_revision": 1,
        "decision_hash": "hash-1",
        "identity_confidence": "high",
    }
    values.update(overrides)
    return service.reserve(**values)


def _dispatch(service: TouchDeliveryService, delivery_id: str, task_id: str = "task-1"):
    service.mark_queued(delivery_id, task_id)
    service.mark_dispatching(delivery_id, task_id)
    return task_id


def test_concurrent_same_key_only_one_reserved(tmp_path: Path) -> None:
    db = tmp_path / "hub.db"

    def run():
        return _reserve(TouchDeliveryService(db_path=db))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run(), range(2)))

    assert sum(1 for item in results if item["reserved"]) == 1
    assert {item["reason"] for item in results} == {"reserved", "inflight"}


def test_failed_can_retry_and_clears_attempt_evidence(tmp_path: Path) -> None:
    service = TouchDeliveryService(db_path=tmp_path / "hub.db")
    first = _reserve(service)
    delivery_id = first["delivery"]["delivery_id"]
    task_id = _dispatch(service, delivery_id)
    service.mark_accepted(delivery_id, task_id, "exec-old")
    service.complete(
        delivery_id,
        status="failed",
        fail_code="rpa_not_sent",
        task_id=task_id,
    )

    retried = _reserve(service, decision_hash="hash-2")
    row = retried["delivery"]
    assert retried["reserved"] is True
    assert retried["reason"] == "retry_reserved"
    assert row["attempt_count"] == 2
    assert row["dispatch_state"] == "preparing"
    assert row["task_id"] is None
    assert row["execution_id"] is None
    assert row["fail_code"] is None


@pytest.mark.parametrize(
    ("terminal", "reason"),
    [
        ("success", "already_success"),
        ("uncertain", "uncertain"),
    ],
)
def test_success_and_uncertain_block_reserve(
    tmp_path: Path,
    terminal: str,
    reason: str,
) -> None:
    service = TouchDeliveryService(db_path=tmp_path / "hub.db")
    created = _reserve(service)
    delivery_id = created["delivery"]["delivery_id"]
    task_id = _dispatch(service, delivery_id)
    service.complete(delivery_id, status=terminal, task_id=task_id)

    blocked = _reserve(service)
    assert blocked["reserved"] is False
    assert blocked["reason"] == reason


def test_legacy_assumed_success_blocks_reserve(tmp_path: Path) -> None:
    service = TouchDeliveryService(db_path=tmp_path / "hub.db")
    created = _reserve(service)
    delivery_id = created["delivery"]["delivery_id"]
    with service._connect() as conn:
        conn.execute(
            """
            UPDATE wechat_touch_deliveries
            SET status = 'legacy_assumed_success', dispatch_state = 'terminal'
            WHERE delivery_id = ?
            """,
            (delivery_id,),
        )
        conn.commit()
    blocked = _reserve(service)
    assert blocked["reserved"] is False
    assert blocked["reason"] == "already_success"


def test_delivery_and_worklog_commit_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TouchDeliveryService(db_path=tmp_path / "hub.db")
    created = _reserve(service)
    delivery_id = created["delivery"]["delivery_id"]
    task_id = _dispatch(service, delivery_id)

    def fail_worklog(**_kwargs):
        raise RuntimeError("worklog failed")

    monkeypatch.setattr(
        "plugins.mxai.scheduler.touch_delivery_service.append_worklog",
        fail_worklog,
    )
    with pytest.raises(RuntimeError, match="worklog failed"):
        service.complete(delivery_id, status="success", task_id=task_id)

    row = service.get(delivery_id)
    assert row["status"] == "reserved"
    assert row["dispatch_state"] == "dispatching"


def test_manual_resolve_uncertain_is_transactional(tmp_path: Path) -> None:
    service = TouchDeliveryService(db_path=tmp_path / "hub.db")
    created = _reserve(service)
    delivery_id = created["delivery"]["delivery_id"]
    task_id = _dispatch(service, delivery_id)
    service.complete(
        delivery_id,
        status="uncertain",
        task_id=task_id,
        op_object="演示客户 · 您好",
        display_name="演示客户",
    )

    resolved = service.resolve_uncertain(
        delivery_id,
        resolution="sent",
        reason="人工核对平台已发送",
    )
    assert resolved["status"] == "success"

    with service._connect() as conn:
        logs = conn.execute(
            "SELECT exec_status, delivery_id, op_object FROM work_logs WHERE delivery_id = ? ORDER BY op_time",
            (delivery_id,),
        ).fetchall()
    assert [row["exec_status"] for row in logs] == ["失败", "成功"]
    # 人工 resolve 补记须继承首次 WorkLog 的客户/话术，避免空台账行
    assert logs[0]["op_object"] == logs[1]["op_object"] == "演示客户 · 您好"


def test_uncertain_delivery_consumes_daily_quota(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "plugins.mxai.scheduler.touch_delivery_service.get_risk_limits",
        lambda _profile_id: {"daily_dm_limit": 1},
    )
    service = TouchDeliveryService(db_path=tmp_path / "hub.db")
    first = _reserve(service)
    delivery_id = first["delivery"]["delivery_id"]
    task_id = _dispatch(service, delivery_id)
    service.complete(delivery_id, status="uncertain", task_id=task_id)

    blocked = _reserve(
        service,
        subtask_id="sub-2",
        customer_identity_key="cid_v1_other",
    )
    assert blocked["reserved"] is False
    assert blocked["reason"] == "risk_blocked"
    assert blocked["quota"]["used"] == 1
    assert blocked["quota"]["delivery_occupancy"] == 1


def test_success_delivery_is_not_double_counted_for_daily_quota(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "plugins.mxai.scheduler.touch_delivery_service.get_risk_limits",
        lambda _profile_id: {"daily_dm_limit": 1},
    )
    service = TouchDeliveryService(db_path=tmp_path / "hub.db")
    first = _reserve(service)
    delivery_id = first["delivery"]["delivery_id"]
    task_id = _dispatch(service, delivery_id)
    service.complete(delivery_id, status="success", task_id=task_id)

    blocked = _reserve(
        service,
        subtask_id="sub-2",
        customer_identity_key="cid_v1_other",
    )
    assert blocked["reserved"] is False
    assert blocked["quota"]["used"] == 1
    assert blocked["quota"]["success_worklogs"] == 1
    assert blocked["quota"]["delivery_occupancy"] == 0

