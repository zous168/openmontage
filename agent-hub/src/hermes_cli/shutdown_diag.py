"""Hub 关停诊断 — Ctrl+C 卡住时打印 WS / 在途 HTTP 快照（验证用）."""

from __future__ import annotations

import logging
import signal
import threading
from collections import Counter
from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger("hermes_cli.shutdown_diag")

_lock = threading.Lock()
_in_flight_http = 0
_in_flight_paths: Counter[str] = Counter()
_wired = False


def note_http_start(path: str) -> None:
    global _in_flight_http
    with _lock:
        _in_flight_http += 1
        _in_flight_paths[path] += 1


def note_http_end(path: str) -> None:
    global _in_flight_http
    with _lock:
        _in_flight_http = max(0, _in_flight_http - 1)
        _in_flight_paths[path] -= 1
        if _in_flight_paths[path] <= 0:
            del _in_flight_paths[path]


def log_shutdown_snapshot(reason: str) -> None:
    """打印关停瞬间的 WS 数 + 在途 HTTP（用于验证 uvicorn drain 卡点）."""
    ws_count = 0
    try:
        from plugins.mxai.cfg.ws_hub import connection_count

        ws_count = connection_count()
    except Exception:  # noqa: BLE001
        pass
    with _lock:
        http_n = _in_flight_http
        paths = dict(_in_flight_paths)
    logger.info(
        "[diag] hub shutdown snapshot reason=%s ws_connections=%d "
        "http_in_flight=%d http_paths=%s",
        reason,
        ws_count,
        http_n,
        paths or None,
    )


class ShutdownDiagMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        path = request.url.path
        note_http_start(path)
        try:
            return await call_next(request)
        finally:
            note_http_end(path)


def _chain_signal_handler(sig: signal.Signals, handler) -> None:
    previous = signal.getsignal(sig)

    def chained(signum, frame):
        try:
            handler(signum, frame)
        finally:
            if callable(previous) and previous is not chained:
                previous(signum, frame)

    try:
        signal.signal(sig, chained)
    except (ValueError, OSError):
        pass


def wire_shutdown_diag(app: FastAPI) -> None:
    """注册在途 HTTP 计数 + Ctrl+C 快照（链式调用 uvicorn 原 handler）."""
    global _wired
    if _wired:
        return
    _wired = True

    app.add_middleware(ShutdownDiagMiddleware)

    def _on_shutdown_signal(signum, _frame) -> None:
        sig_name = getattr(signal.Signals(signum), "name", str(signum))
        log_shutdown_snapshot(f"signal:{sig_name}")

    _chain_signal_handler(signal.SIGINT, _on_shutdown_signal)
    if hasattr(signal, "SIGBREAK"):
        _chain_signal_handler(signal.SIGBREAK, _on_shutdown_signal)

    logger.info("[diag] hub shutdown diagnostics enabled (SIGINT snapshot + HTTP in-flight)")
