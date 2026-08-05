"""Hub → Gateway signal to connect a platform without full gateway restart."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)

_NUDGE_FILE = "platform_connect_nudges.json"


def _nudge_path() -> Path:
    path = get_hermes_home() / "device" / _NUDGE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def write_platform_connect_nudge(platform: str) -> None:
    """Record that ``platform`` became ready and should connect ASAP."""
    name = str(platform or "").strip().lower()
    if not name:
        return
    path = _nudge_path()
    payload: dict[str, Any] = {}
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                payload = raw
        except Exception:
            payload = {}
    payload[name] = time.time()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def consume_platform_connect_nudges() -> set[str]:
    """Return nudged platform ids and clear the file."""
    path = _nudge_path()
    if not path.is_file():
        return set()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.debug("Failed to read platform connect nudges: %s", exc)
        return set()
    try:
        path.unlink()
    except OSError:
        pass
    if not isinstance(raw, dict):
        return set()
    return {str(k).strip().lower() for k in raw if str(k).strip()}
