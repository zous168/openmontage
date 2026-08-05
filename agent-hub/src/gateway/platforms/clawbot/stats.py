"""ClawBot 消息统计（独立 JSON 文件，避免每条消息 rewrite config.yaml）."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_STATS_FILE = "clawbot_message_stats.json"
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
    }
    if stats_date != today_str:
        stats["today"] = 0
        stats["stats_date"] = today_str
    return stats


def _read_stats_file() -> dict[str, int | str]:
    path = _stats_path()
    if not path.is_file():
        seeded = _seed_from_legacy_config()
        if seeded is not None:
            return seeded
        return _empty_stats()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.debug("clawbot stats: failed to read %s", path, exc_info=True)
        return _empty_stats()
    return _normalize_stats(raw if isinstance(raw, dict) else None)


def _seed_from_legacy_config() -> dict[str, int | str] | None:
    """一次性从 ``platforms.clawbot.extra.stats`` 迁移旧占位数据."""
    try:
        from gateway.platforms.clawbot.config import load_clawbot_config

        cfg = load_clawbot_config()
        legacy = cfg.get("stats")
        if not isinstance(legacy, dict):
            return None
        received = int(legacy.get("received") or 0)
        replied = int(legacy.get("replied") or 0)
        today = int(legacy.get("today") or 0)
        if received == replied == today == 0:
            return None
        stats = _normalize_stats(
            {"received": received, "replied": replied, "today": today}
        )
        _write_stats_file(stats)
        return stats
    except Exception:
        return None


def _write_stats_file(stats: dict[str, int | str]) -> None:
    from utils import atomic_replace

    path = _stats_path()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    atomic_replace(tmp, path)


def load_clawbot_message_stats() -> dict[str, int]:
    """供 Channels / PlatformView 展示."""
    stats = _read_stats_file()
    return {
        "received": int(stats["received"]),
        "replied": int(stats["replied"]),
        "today": int(stats["today"]),
    }


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
            logger.debug("clawbot stats: persist failed", exc_info=True)


def get_last_clawbot_inbound_peer() -> str:
    """最近一次 ClawBot 入站微信用户 id（供素材回发等工具默认收件人）."""
    return str(_read_stats_file().get("last_inbound_peer") or "").strip()


def record_clawbot_received(*, sender_id: str | None = None) -> None:
    """ClawBot 入站 +1（累计接收 & 今日）；可选记录发信人 id."""
    peer = str(sender_id or "").strip()
    if peer:
        with _lock:
            stats = _read_stats_file()
            stats["last_inbound_peer"] = peer
            try:
                _write_stats_file(stats)
            except Exception:
                logger.debug("clawbot stats: persist peer failed", exc_info=True)
    _record(received=1)


def record_clawbot_replied() -> None:
    """ClawBot 出站回复 +1（累计回复 & 今日）."""
    _record(replied=1)
