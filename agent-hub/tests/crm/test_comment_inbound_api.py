"""CR-133 · comment-inbound 路由：入库 / 去重 / 渠道校验 / 隔离."""

from __future__ import annotations

_BASE = "/api/plugins/mxai/agents/douyin"


def test_comment_inbound_insert_and_list(mxai_client) -> None:
    r = mxai_client.post(
        f"{_BASE}/comment-inbound",
        json={"nickname": "小王", "douyin_id": "dy_1", "comment": "价格多少",
              "intent": "高", "time": "2026-07-05T02:00:00+00:00"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["inserted"] is True
    leads = mxai_client.get(f"{_BASE}/leads").json()["items"]
    assert len(leads) == 1
    l = leads[0]
    assert l["author"] == "小王" and l["douyin_id"] == "dy_1" and l["intent_level"] == "高"
    assert l["created_at"] == "2026-07-05T02:00:00+00:00"


def test_comment_inbound_dedup_skips(mxai_client) -> None:
    body = {"nickname": "小王", "douyin_id": "dy_dup", "comment": "a", "intent": "高"}
    mxai_client.post(f"{_BASE}/comment-inbound", json=body)
    r2 = mxai_client.post(f"{_BASE}/comment-inbound", json={**body, "comment": "b", "intent": "低"})
    assert r2.status_code == 200
    assert r2.json()["skipped"] is True and r2.json()["reason"] == "duplicate_douyin_id"
    assert mxai_client.get(f"{_BASE}/leads").json()["total"] == 1


def test_comment_inbound_rejects_private_channel(mxai_client) -> None:
    r = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/comment-inbound",
        json={"nickname": "x", "douyin_id": "dy_x", "comment": "c", "intent": "高"},
    )
    assert r.status_code == 400


def test_comment_inbound_missing_douyin_id(mxai_client) -> None:
    r = mxai_client.post(
        f"{_BASE}/comment-inbound",
        json={"nickname": "x", "douyin_id": "  ", "comment": "c", "intent": "高"},
    )
    assert r.status_code == 422


def test_comment_inbound_channel_isolation(mxai_client) -> None:
    mxai_client.post(
        f"{_BASE}/comment-inbound",
        json={"nickname": "a", "douyin_id": "shared", "comment": "c", "intent": "中"},
    )
    r = mxai_client.post(
        "/api/plugins/mxai/agents/xiaohongshu/comment-inbound",
        json={"nickname": "b", "douyin_id": "shared", "comment": "c", "intent": "中"},
    )
    assert r.json()["inserted"] is True  # 不同渠道同 douyin_id 各存
    assert mxai_client.get(f"{_BASE}/leads").json()["total"] == 1
    assert mxai_client.get("/api/plugins/mxai/agents/xiaohongshu/leads").json()["total"] == 1


def test_comment_inbound_with_reply_text_marks_sent(mxai_client) -> None:
    r = mxai_client.post(
        f"{_BASE}/comment-inbound",
        json={
            "nickname": "小美",
            "douyin_id": "dy_reply",
            "comment": "求联系",
            "intent": "高",
            "reply_text": "好的，已私信",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] is True
    assert body["reply_recorded"] is True
    assert body["comment_reply_status"] == "sent"
    lead = mxai_client.get(f"{_BASE}/leads").json()["items"][0]
    assert lead["comment_reply_status"] == "sent"
    assert int(lead["comment_reply_count"]) == 1
