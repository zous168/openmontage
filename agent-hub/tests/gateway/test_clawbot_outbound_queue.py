"""Platform outbound queue tests."""

from __future__ import annotations

import asyncio

import pytest

from gateway.platforms.base import SendResult
from gateway.platforms.outbound_queue import (
    OutboundSendQueue,
    is_rate_limit_error,
    rate_limit_backoff_seconds,
)


def test_rate_limit_helpers_ilink() -> None:
    err = "iLink sendmessage rate limited; cooldown active for 30.0s"
    assert is_rate_limit_error(err)
    assert rate_limit_backoff_seconds(err) == pytest.approx(30.5)


def test_rate_limit_helpers_wecom() -> None:
    err = "WeCom errcode 45009: api freq out of limit"
    assert is_rate_limit_error(err)
    assert rate_limit_backoff_seconds(err) == pytest.approx(30.0)

    callback_err = "{'errcode': 45033, 'errmsg': 'concurrent out of limit'}"
    assert is_rate_limit_error(callback_err)


@pytest.mark.asyncio
async def test_outbound_queue_preserves_order() -> None:
    queue = OutboundSendQueue(min_interval_seconds=0.0)
    await queue.start()
    order: list[int] = []

    async def deliver(value: int) -> SendResult:
        order.append(value)
        await asyncio.sleep(0.01)
        return SendResult(success=True, message_id=str(value))

    first = asyncio.create_task(
        queue.enqueue(lambda: deliver(1), chat_id="user@im.wechat")
    )
    second = asyncio.create_task(
        queue.enqueue(lambda: deliver(2), chat_id="user@im.wechat")
    )
    third = asyncio.create_task(
        queue.enqueue(lambda: deliver(3), chat_id="user@im.wechat")
    )

    results = await asyncio.gather(first, second, third)
    await queue.stop()

    assert order == [1, 2, 3]
    assert [r.message_id for r in results] == ["1", "2", "3"]


@pytest.mark.asyncio
async def test_outbound_queue_retries_rate_limit() -> None:
    queue = OutboundSendQueue(min_interval_seconds=0.0, max_attempts=3)
    await queue.start()
    attempts = {"count": 0}

    async def deliver() -> SendResult:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return SendResult(
                success=False,
                error="iLink sendmessage rate limited; cooldown active for 0.1s",
            )
        return SendResult(success=True, message_id="ok")

    result = await queue.enqueue(deliver, chat_id="user@im.wechat")
    await queue.stop()

    assert result.success is True
    assert attempts["count"] == 2
