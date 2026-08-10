"""Clearer tool lines in headless ``runs/*.log`` (not a new audit system).

Existing audit stays in ``events.jsonl`` / ``production_audit`` / ``decision_log``.
This only makes each Hermes tool call easy to skim in the stage run log.
"""

from __future__ import annotations

import json
from typing import Any


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {}
            if isinstance(parsed, dict):
                return parsed
    return {}


def _short(value: Any, limit: int = 160) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


def _result_ok(parsed: dict[str, Any], *, is_error: bool) -> bool:
    if is_error:
        return False
    if parsed.get("ok") is False:
        return False
    if parsed.get("success") is False:
        return False
    if parsed.get("error"):
        return False
    nested = parsed.get("result")
    if isinstance(nested, dict) and nested.get("success") is False:
        return False
    if isinstance(nested, dict) and nested.get("error"):
        return False
    return True


def _error_text(parsed: dict[str, Any], raw: Any) -> str:
    for key in ("error", "message"):
        if parsed.get(key):
            return _short(parsed[key], 240)
    nested = parsed.get("result")
    if isinstance(nested, dict) and nested.get("error"):
        return _short(nested["error"], 240)
    return _short(raw, 240)


def summarize_tool_call(
    name: str,
    args: Any,
    result: Any,
    *,
    is_error: bool = False,
) -> dict[str, Any]:
    """One-line description of what a tool call did (for run log skimming)."""
    tool = str(name or "tool").strip() or "tool"
    params = args if isinstance(args, dict) else {}
    label = str(params.get("label") or "").strip() or None
    parsed = _as_dict(result)
    ok = _result_ok(parsed, is_error=is_error)

    detail: dict[str, Any] = {}
    summary: str

    if tool == "om_registry":
        action = str(params.get("action") or "execute").strip()
        inner = str(params.get("tool") or "").strip()
        detail = {"action": action}
        if inner:
            detail["registry_tool"] = inner
        if action == "execute" and isinstance(params.get("params"), dict):
            p = params["params"]
            paths = {
                k: p[k]
                for k in (
                    "video_path",
                    "subtitles_path",
                    "thumbnail_path",
                    "output_path",
                    "export_dir",
                )
                if p.get(k)
            }
            if paths:
                detail["paths"] = paths
            if p.get("title"):
                detail["title"] = _short(p.get("title"), 80)
        summary = f"om_registry {action}" + (f" → {inner}" if inner else "")
        if ok:
            nested = parsed.get("result") if isinstance(parsed.get("result"), dict) else {}
            data = nested.get("data") if isinstance(nested, dict) else None
            if isinstance(data, dict) and data.get("export_path"):
                detail["export_path"] = data["export_path"]
                summary += " · exported"
            elif isinstance(nested, dict) and nested.get("success") is True:
                summary += " · ok"
        else:
            summary += f" · FAIL {_error_text(parsed, result)}"

    elif tool == "om_checkpoint":
        status = str(params.get("status") or "").strip()
        arts = params.get("artifacts")
        art_keys = sorted(arts.keys()) if isinstance(arts, dict) else []
        detail = {"status": status, "artifacts": art_keys}
        summary = f"om_checkpoint status={status or '?'}"
        if art_keys:
            summary += f" artifacts={','.join(art_keys)}"
        if not ok:
            summary += f" · FAIL {_error_text(parsed, result)}"

    elif tool == "om_artifact_write":
        path = str(params.get("path") or "").strip()
        detail = {"path": path}
        if parsed.get("bytes") is not None:
            detail["bytes"] = parsed.get("bytes")
        summary = f"om_artifact_write {path or '?'}"
        if parsed.get("bytes") is not None:
            summary += f" ({parsed.get('bytes')} B)"
        if not ok:
            summary += f" · FAIL {_error_text(parsed, result)}"

    elif tool == "om_artifact_read":
        path = str(params.get("path") or "").strip()
        detail = {"path": path}
        summary = f"om_artifact_read {path or '?'}"
        if not ok:
            summary += f" · FAIL {_error_text(parsed, result)}"

    elif tool == "om_decision_append":
        decisions = params.get("decisions")
        n = len(decisions) if isinstance(decisions, list) else 0
        detail = {"count": n}
        summary = f"om_decision_append ×{n}"
        if not ok:
            summary += f" · FAIL {_error_text(parsed, result)}"

    elif tool == "skill_view":
        skill = str(params.get("name") or params.get("skill") or "").strip()
        detail = {"skill": skill} if skill else {}
        summary = f"skill_view {skill or '?'}"
        if not ok:
            summary += f" · FAIL {_error_text(parsed, result)}"

    else:
        keys = [k for k in ("path", "tool", "action", "command", "query") if params.get(k)]
        bits = [f"{k}={_short(params[k], 60)}" for k in keys[:3]]
        summary = tool + (f" ({', '.join(bits)})" if bits else "")
        if label:
            summary = f"{summary} · {label}"
        if not ok:
            summary += f" · FAIL {_error_text(parsed, result)}"
        detail = {k: params[k] for k in keys}

    if label and tool.startswith("om_"):
        detail["label"] = label

    return {
        "tool": tool,
        "ok": ok,
        "label": label,
        "summary": summary,
        "detail": detail,
    }


def truncate_tool_result_body(body: str, *, limit: int = 8000) -> str:
    """Keep run logs readable when tool results are huge JSON blobs."""
    text = body if isinstance(body, str) else str(body or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[truncated {len(text) - limit} chars]"
