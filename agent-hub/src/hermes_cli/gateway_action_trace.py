"""Shared [gateway-restart] logging for dashboard gateway actions."""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


def log_gateway_trace(event: str, **fields: object) -> None:
    """Emit one grep-friendly INFO line: ``[gateway-restart] <event> ...``."""
    suffix = " ".join(
        f"{k}={v!r}" for k, v in fields.items() if v is not None and v != ""
    )
    _log.info("[gateway-restart] %s%s", event, f" {suffix}" if suffix else "")
