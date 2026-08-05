"""Shared [model-trace] logging for profile / PTY / config model debugging."""

from __future__ import annotations

import logging

_log = logging.getLogger(__name__)


def log_model_trace(event: str, **fields: object) -> None:
    """Emit one grep-friendly INFO line: ``[model-trace] <event> key='value' ...``."""
    suffix = " ".join(
        f"{k}={v!r}" for k, v in fields.items() if v is not None and v != ""
    )
    _log.info("[model-trace] %s%s", event, f" {suffix}" if suffix else "")
