from __future__ import annotations

from fastapi.testclient import TestClient

from plugins.mxai.scheduler.touch_delivery_service import TouchDeliveryService


def _uncertain_delivery(suffix: str = "api") -> dict:
    service = TouchDeliveryService()
    reserved = service.reserve(
        profile_id="wechat",
        channel_account_id="acct",
        subtask_id=f"sub-{suffix}",
        customer_identity_key=f"cid_v1_{suffix}_{'x' * 24}",
        business_date="2026-07-14",
        threshold_sec=60,
        silence_sec=120,
        last_inbound_at_snapshot="2026-07-14T00:00:00+00:00",
        identity_revision=1,
        decision_hash=f"hash-{suffix}",
        identity_confidence="high",
    )["delivery"]
    task_id = f"task-{suffix}"
    service.mark_queued(reserved["delivery_id"], task_id)
    service.mark_dispatching(reserved["delivery_id"], task_id)
    return service.complete(
        reserved["delivery_id"],
        status="uncertain",
        fail_code="dispatch_unknown",
        fail_reason="回执超时",
        task_id=task_id,
    )


def test_list_uncertain_deliveries_masks_identity(mxai_client: TestClient) -> None:
    delivery = _uncertain_delivery()

    response = mxai_client.get(
        "/api/plugins/mxai/agents/wechat/scheduled-touch/deliveries",
        params={"business_date": "2026-07-14", "status": "uncertain"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["page"]["total"] == 1
    item = body["items"][0]
    assert item["delivery_id"] == delivery["delivery_id"]
    assert item["customer_identity_masked"].startswith("cid_v1_api")
    assert "customer_identity_key" not in item


def test_resolve_uncertain_delivery_is_profile_scoped(mxai_client: TestClient) -> None:
    delivery = _uncertain_delivery("resolve")
    path = (
        "/api/plugins/mxai/agents/wechat/scheduled-touch/deliveries/"
        f"{delivery['delivery_id']}/resolve"
    )

    assert (
        mxai_client.post(
            path,
            json={"resolution": "sent", "note": "   "},
        ).status_code
        == 422
    )
    response = mxai_client.post(
        path,
        json={"resolution": "sent", "note": "人工确认平台已发送"},
    )

    assert response.status_code == 200
    resolved = response.json()["delivery"]
    assert resolved["status"] == "success"
    assert "customer_identity_key" not in resolved
    assert resolved["customer_identity_masked"]
    assert (
        mxai_client.post(
            path,
            json={"resolution": "not_sent", "note": "重复核查"},
        ).status_code
        == 409
    )
    other_profile = path.replace("/wechat/", "/qiyeweixin/")
    assert (
        mxai_client.post(
            other_profile,
            json={"resolution": "sent", "note": "越权核查"},
        ).status_code
        == 404
    )
