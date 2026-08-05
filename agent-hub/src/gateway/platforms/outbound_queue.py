"""Platform outbound send queue — FIFO delivery with rate-limit pacing."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional

from gateway.platforms.base import SendResult

logger = logging.getLogger(__name__)

DeliverFn = Callable[[], Awaitable[SendResult]]
_RATE_LIMIT_BACKOFF_RE = re.compile(r"cooldown active for ([0-9.]+)s", re.IGNORECASE)
_WECOM_RATE_LIMIT_ERRCODES = frozenset({45009, 45033})


def is_rate_limit_error(error: str) -> bool:
    """Detect iLink / WeCom / generic rate-limit failures."""
    lowered = (error or "").lower()
    if "rate limited" in lowered or "cooldown active" in lowered:
        return True
    if "too many requests" in lowered:
        return True
    if "frequency" in lowered and "limit" in lowered:
        return True
    if "freq" in lowered and "limit" in lowered:
        return True
    for code in _WECOM_RATE_LIMIT_ERRCODES:
        if f"errcode {code}" in lowered:
            return True
        if f"errcode': {code}" in lowered or f'errcode": {code}' in lowered:
            return True
        if f"errcode':{code}" in lowered or f'errcode":{code}' in lowered:
            return True
    return False


def rate_limit_backoff_seconds(error: str, *, default: float = 30.0) -> float:
    """Parse rate-limit errors into a sleep duration."""
    match = _RATE_LIMIT_BACKOFF_RE.search(error or "")
    if match:
        return max(0.5, float(match.group(1)) + 0.5)
    if is_rate_limit_error(error):
        return default
    return 0.0


@dataclass
class _OutboundJob:
    chat_id: str
    deliver: DeliverFn
    future: asyncio.Future
    attempts: int = 0


class OutboundSendQueue:
    """Serialize proactive sends through a single FIFO worker."""

    def __init__(
        self,
        *,
        min_interval_seconds: float = 2.0,
        max_attempts: int = 8,
        name: str = "outbound",
    ) -> None:
        self._min_interval = max(0.0, float(min_interval_seconds))
        self._max_attempts = max(1, int(max_attempts))
        self._name = name
        self._queue: asyncio.Queue[_OutboundJob | None] = asyncio.Queue()
        self._worker: Optional[asyncio.Task] = None
        self._last_send_at = 0.0

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    async def start(self) -> None:
        if self._worker and not self._worker.done():
            return
        self._worker = asyncio.create_task(self._run(), name=self._name)

    async def stop(self) -> None:
        worker = self._worker
        if worker is None:
            return
        await self._queue.put(None)
        try:
            await asyncio.wait_for(worker, timeout=60.0)
        except asyncio.TimeoutError:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        self._worker = None
        while True:
            try:
                job = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if job is None:
                continue
            if not job.future.done():
                job.future.set_result(SendResult(success=False, error="outbound queue stopped"))

    async def enqueue(self, deliver: DeliverFn, *, chat_id: str) -> SendResult:
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        await self._queue.put(_OutboundJob(chat_id=chat_id, deliver=deliver, future=future))
        return await future

    async def _pace(self) -> None:
        if self._min_interval <= 0:
            return
        elapsed = time.monotonic() - self._last_send_at
        wait = self._min_interval - elapsed
        if wait > 0:
            await asyncio.sleep(wait)

    async def _run(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                if job is None:
                    break
                await self._pace()
                try:
                    result = await job.deliver()
                except Exception as exc:
                    result = SendResult(success=False, error=str(exc))

                if not result.success and is_rate_limit_error(str(result.error or "")):
                    job.attempts += 1
                    if job.attempts >= self._max_attempts:
                        if not job.future.done():
                            job.future.set_result(result)
                        continue
                    backoff = rate_limit_backoff_seconds(str(result.error or ""))
                    logger.warning(
                        "%s outbound queue: rate limited for %s; retry %d/%d in %.1fs",
                        self._name,
                        job.chat_id,
                        job.attempts,
                        self._max_attempts,
                        backoff,
                    )
                    await asyncio.sleep(backoff)
                    await self._queue.put(job)
                    continue

                self._last_send_at = time.monotonic()
                if not job.future.done():
                    job.future.set_result(result)
            finally:
                self._queue.task_done()
