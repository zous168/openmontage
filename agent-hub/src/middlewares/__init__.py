"""组合根 HTTP 中间件（鉴权已迁至 ``hermes_cli.dashboard_auth``）."""

from src.middlewares.trace_middleware import TraceMiddleware

__all__ = [
    "TraceMiddleware",
]
