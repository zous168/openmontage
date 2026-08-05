"""ClawBot outbound queue — re-exports shared implementation."""

from gateway.platforms.outbound_queue import (
    OutboundSendQueue as ClawbotOutboundQueue,
    is_rate_limit_error,
    rate_limit_backoff_seconds,
)

__all__ = [
    "ClawbotOutboundQueue",
    "is_rate_limit_error",
    "rate_limit_backoff_seconds",
]
