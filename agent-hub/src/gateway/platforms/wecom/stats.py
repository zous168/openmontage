"""企微 AI Bot 消息统计（独立 JSON 文件，对齐 ClawBot stats.py）."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STATS_FILE = "wecom_message_stats.json"
_lock = threading.Lock()


def _stats_path() -> Path:
    from runtime_paths import resolve_hub_data_dir_path

    path = resolve_hub_data_dir_path() / "device" / _STATS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _empty_stats(*, stats_date: str | None = None) -> dict[str, int | str]:
    from core.timeutil import beijing_today_str

    return {
        "received": 0,
        "replied": 0,
        "today": 0,
        "stats_date": stats_date or beijing_today_str(),
        "last_inbound_peer": "",
        "last_inbound_chat_type": "",
    }


def _normalize_stats(raw: dict[str, Any] | None) -> dict[str, int | str]:
    from core.timeutil import beijing_today_str

    today_str = beijing_today_str()
    if not isinstance(raw, dict):
        return _empty_stats(stats_date=today_str)
    stats_date = str(raw.get("stats_date") or "").strip() or today_str
    stats = {
        "received": max(0, int(raw.get("received") or 0)),
        "replied": max(0, int(raw.get("replied") or 0)),
        "today": max(0, int(raw.get("today") or 0)),
        "stats_date": stats_date,
        "last_inbound_peer": str(raw.get("last_inbound_peer") or "").strip(),
        "last_inbound_chat_type": str(raw.get("last_inbound_chat_type") or "").strip(),
    }
    if stats_date != today_str:
        stats["today"] = 0
        stats["stats_date"] = today_str
    return stats


def _read_stats_file() -> dict[str, int | str]:
    path = _stats_path()
    if not path.is_file():
        return _empty_stats()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("wecom stats: failed to read %s", path, exc_info=True)
        return _empty_stats()
    return _normalize_stats(raw if isinstance(raw, dict) else None)


def _write_stats_file(stats: dict[str, int | str]) -> None:
    from utils import atomic_replace

    path = _stats_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    atomic_replace(tmp, path)


def _record(*, received: int = 0, replied: int = 0) -> None:
    if received <= 0 and replied <= 0:
        return
    with _lock:
        stats = _read_stats_file()
        stats["received"] = int(stats["received"]) + received
        stats["replied"] = int(stats["replied"]) + replied
        stats["today"] = int(stats["today"]) + received + replied
        try:
            _write_stats_file(stats)
        except Exception:
            logger.debug("wecom stats: persist failed", exc_info=True)


def load_wecom_message_stats() -> dict[str, int]:
    """供 Channels / PlatformView 展示."""
    stats = _read_stats_file()
    return {
        "received": int(stats["received"]),
        "replied": int(stats["replied"]),
        "today": int(stats["today"]),
    }


def record_wecom_received(*, sender_id: str | None = None, chat_type: str | None = None) -> None:
    """企微入站 +1；可选记录发信人 id / 会话类型."""
    peer = str(sender_id or "").strip()
    ctype = str(chat_type or "").strip()
    if peer or ctype:
        with _lock:
            stats = _read_stats_file()
            if peer:
                stats["last_inbound_peer"] = peer
            if ctype:
                stats["last_inbound_chat_type"] = ctype
            try:
                _write_stats_file(stats)
            except Exception:
                logger.debug("wecom stats: persist peer failed", exc_info=True)
    _record(received=1)


def get_last_wecom_inbound_peer() -> str:
    """最近一次企微入站用户/群 id（供素材回发等工具默认收件人）."""
    return str(_read_stats_file().get("last_inbound_peer") or "").strip()


def get_last_wecom_inbound_chat_type() -> str:
    """最近一次企微入站会话类型（dm / group）."""
    return str(_read_stats_file().get("last_inbound_chat_type") or "").strip()


def record_wecom_replied() -> None:
    """企微出站回复 +1."""
    _record(replied=1)
