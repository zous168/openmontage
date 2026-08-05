"""Trace ID 中间件：从 header 读入或生成 UUIDv4，贯穿全链路."""

import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

HEADER_TRACE_ID = "X-Trace-Id"


class TraceMiddleware(BaseHTTPMiddleware):
    """TraceMiddleware 从请求读取/生成 trace_id 并绑定到 structlog 上下文."""

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        trace_id = request.headers.get(HEADER_TRACE_ID) or str(uuid.uuid4())
        request.state.trace_id = trace_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id, path=request.url.path)
        response: Response = await call_next(request)
        response.headers[HEADER_TRACE_ID] = trace_id
        return response
