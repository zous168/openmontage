"""CR-154：scheduled_msg（含 delivery_id）WorkLog 须写「客户 · 话术」，禁止仅 locator 掩码。"""

from __future__ import annotations

from plugins.mxai.orchestrator.models import Task, TaskStatus
from plugins.mxai.orchestrator.queue_manager import _worklog_op_object


def _task(payload: dict) -> Task:
    return Task(
        task_id="tsk_test",
        profile_id="wechat",
        name="分段触达",
        task_type="scheduled_msg",
        status=TaskStatus.RUNNING,
        payload=payload,
    )


def test_delivery_op_object_uses_display_name_and_message() -> None:
    op = _worklog_op_object(
        _task(
            {
                "delivery_id": "tdl_1",
                "display_name": "Test",
                "customer_uid": "cuid_1",
                "message": "你好，请问有什么能帮您？",
                "recipient": "wxid_secret",
                "recipient_locator_type": "remark",
                "recipient_locator_masked": "***",
                "recipient_locator_value": "Test",
            }
        ),
        {},
    )
    assert op == "Test · 你好，请问有什么能帮您？"
    assert "wxid_secret" not in op
    assert "remark:***" not in op


def test_delivery_op_object_falls_back_to_customer_uid() -> None:
    op = _worklog_op_object(
        _task(
            {
                "delivery_id": "tdl_2",
                "customer_uid": "cuid_abc",
                "message": "回访一下",
                "recipient_locator_type": "remark",
                "recipient_locator_masked": "***",
            }
        ),
        {},
    )
    assert op == "cuid_abc · 回访一下"


def test_delivery_op_object_mask_only_when_no_peer_or_message() -> None:
    op = _worklog_op_object(
        _task(
            {
                "delivery_id": "tdl_3",
                "recipient_locator_type": "remark",
                "recipient_locator_masked": "***",
            }
        ),
        {},
    )
    assert op == "remark:***"


def test_single_mode_op_object_unchanged() -> None:
    op = _worklog_op_object(
        _task({"recipient": "售后", "message": "回访话术"}),
        {},
    )
    assert op == "售后 · 回访话术"
