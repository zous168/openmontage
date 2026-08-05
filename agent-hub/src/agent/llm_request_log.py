"""Persist raw LLM API request/response payloads for dashboard debugging."""

from __future__ import annotations

import json
import logging
from copy import deepcopy
from typing import Any, Optional

logger = logging.getLogger(__name__)

MAX_JSON_BYTES = 10 * 1024 * 1024
_REDACT_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "x-api-key",
        "x-auth-token",
        "openai_api_key",
        "anthropic_api_key",
    }
)


def _cap_json_text(text: str) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= MAX_JSON_BYTES:
        return text
    truncated = encoded[:MAX_JSON_BYTES].decode("utf-8", errors="ignore")
    return truncated + "\n... [truncated for storage limit] ..."


def _should_redact_key(key: str) -> bool:
    lower = (key or "").lower()
    if lower in _REDACT_KEYS:
        return True
    return lower.endswith("_api_key") or lower.endswith("_secret")


def _redact_value(key: str, value: Any) -> Any:
    if not _should_redact_key(key):
        return value
    if isinstance(value, str) and value:
        if value.lower().startswith("bearer "):
            return "Bearer …[redacted]"
        return value[:8] + "…[redacted]" if len(value) > 8 else "[redacted]"
    return "[redacted]"


def _redact_structure(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 24:
        return "[max depth]"
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            redacted = _redact_value(str(key), item)
            if redacted is item and isinstance(item, (dict, list)):
                out[str(key)] = _redact_structure(item, _depth=_depth + 1)
            else:
                out[str(key)] = redacted
        return out
    if isinstance(value, list):
        return [_redact_structure(item, _depth=_depth + 1) for item in value]
    return value


def _to_plain(value: Any) -> Any:
    from agent.anthropic_adapter import _to_plain_data

    return _to_plain_data(value)


def serialize_request_payload(api_kwargs: Optional[dict[str, Any]]) -> str:
    body = deepcopy(api_kwargs or {})
    body.pop("timeout", None)
    body = {k: v for k, v in body.items() if v is not None}
    plain = _redact_structure(_to_plain(body))
    return _cap_json_text(json.dumps(plain, ensure_ascii=False, default=str))


def serialize_response_payload(response: Any) -> Optional[str]:
    if response is None:
        return None
    plain = _redact_structure(_to_plain(response))
    return _cap_json_text(json.dumps(plain, ensure_ascii=False, default=str))


def serialize_error_payload(error: Any, *, details: Optional[str] = None) -> Optional[str]:
    if error is None and not details:
        return None
    payload: dict[str, Any] = {}
    if details:
        payload["details"] = details
    if error is not None:
        payload["type"] = type(error).__name__
        payload["message"] = str(error)
        for attr in ("status_code", "request_id", "code", "param", "type"):
            value = getattr(error, attr, None)
            if value is not None:
                payload[attr] = value
        body = getattr(error, "body", None)
        if body is not None:
            payload["body"] = _to_plain(body)
        response_obj = getattr(error, "response", None)
        if response_obj is not None:
            try:
                payload["response_status"] = getattr(response_obj, "status_code", None)
                payload["response_text"] = getattr(response_obj, "text", None)
            except Exception:
                pass
    plain = _redact_structure(payload)
    return _cap_json_text(json.dumps(plain, ensure_ascii=False, default=str))


def record_llm_api_request_from_agent(
    agent,
    *,
    api_request_id: str,
    turn_id: str,
    api_call_count: int,
    attempt: int,
    api_kwargs: Optional[dict[str, Any]],
    response: Any = None,
    error: Any = None,
    error_details: Optional[str] = None,
    status: str,
    latency_ms: Optional[float],
    input_tokens: Optional[int] = None,
    output_tokens: Optional[int] = None,
    cache_read_tokens: Optional[int] = None,
    cache_write_tokens: Optional[int] = None,
    reasoning_tokens: Optional[int] = None,
    estimated_cost_usd: Optional[float] = None,
) -> None:
    session_db = getattr(agent, "_session_db", None)
    session_id = getattr(agent, "session_id", None) or ""
    if not session_db or not session_id:
        return
    try:
        if not getattr(agent, "_session_db_created", False):
            agent._ensure_db_session()
        session_db.insert_llm_api_request(
            session_id=session_id,
            api_request_id=api_request_id,
            attempt=max(1, int(attempt or 1)),
            turn_id=turn_id or None,
            api_call_number=int(api_call_count or 0) or None,
            provider=getattr(agent, "provider", None),
            base_url=getattr(agent, "base_url", None),
            model=getattr(agent, "model", None),
            api_mode=getattr(agent, "api_mode", None),
            status=status,
            latency_ms=latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            reasoning_tokens=reasoning_tokens,
            estimated_cost_usd=estimated_cost_usd,
            request_json=serialize_request_payload(api_kwargs),
            response_json=serialize_response_payload(response),
            error_json=serialize_error_payload(error, details=error_details),
        )
    except Exception as exc:
        logger.debug(
            "LLM request log persist failed (session=%s, api_request_id=%s): %s",
            session_id,
            api_request_id,
            exc,
        )
