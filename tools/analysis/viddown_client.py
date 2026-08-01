"""VidDown (viddown.cn) client — primary Douyin reference download provider.

VidDown parses share URLs server-side and exposes a task API. OpenMontage uses
it as the **primary** downloader for Douyin links (not a yt-dlp fallback).

Disable with ``VIDDOWN_ENABLED=0``. Override base URL with ``VIDDOWN_BASE_URL``.
Legacy alias: ``VIDDOWN_FALLBACK=0`` also disables.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

_DEFAULT_BASE = "https://www.viddown.cn"
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_CSRF_RE = re.compile(r'name="csrfmiddlewaretoken" value="([^"]+)"')


class VidDownError(RuntimeError):
    """VidDown parse or download failed."""


def viddown_enabled() -> bool:
    raw = os.environ.get("VIDDOWN_ENABLED")
    if raw is None:
        raw = os.environ.get("VIDDOWN_FALLBACK", "1")
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


def viddown_base_url() -> str:
    return (os.environ.get("VIDDOWN_BASE_URL") or _DEFAULT_BASE).rstrip("/")


def _http(
    url: str,
    *,
    method: str = "GET",
    data: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 60,
) -> bytes:
    hdrs = {"User-Agent": _USER_AGENT}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _fetch_csrf(base: str) -> str:
    html = _http(f"{base}/").decode("utf-8", errors="replace")
    match = _CSRF_RE.search(html)
    if not match:
        raise VidDownError("VidDown CSRF token not found")
    return match.group(1)


def _start_task(base: str, video_url: str, csrf: str) -> int:
    form = urllib.parse.urlencode(
        {"csrfmiddlewaretoken": csrf, "url": video_url},
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": f"{base}/",
        "Origin": base,
        "Cookie": f"csrftoken={csrf}",
        "X-CSRFToken": csrf,
        "X-Requested-With": "XMLHttpRequest",
    }
    raw = _http(f"{base}/", method="POST", data=form, headers=headers, timeout=30)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise VidDownError(f"VidDown parse response was not JSON: {raw[:120]!r}") from exc
    task_id = payload.get("task_id")
    if not isinstance(task_id, int):
        raise VidDownError(f"VidDown did not return task_id: {payload}")
    return task_id


def _poll_task(base: str, task_id: int, *, max_wait_seconds: float = 120) -> dict[str, Any]:
    info_url = f"{base}/task/{task_id}/info/"
    headers = {
        "Referer": f"{base}/download/{task_id}/",
        "X-Requested-With": "XMLHttpRequest",
    }
    deadline = time.time() + max_wait_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
        raw = _http(info_url, headers=headers, timeout=30)
        last = json.loads(raw.decode("utf-8"))
        status = last.get("status")
        if status == "failed":
            msg = last.get("error_message") or last.get("error") or "parse failed"
            raise VidDownError(f"VidDown parse failed: {msg}")
        if status in (None, "completed", "complete", "success"):
            if last.get("formats"):
                return last
        time.sleep(1.5)
    raise VidDownError(f"VidDown parse timed out after {max_wait_seconds:.0f}s")


def _pick_format(formats: list[dict[str, Any]], max_height: int) -> dict[str, Any]:
    scored: list[tuple[int, dict[str, Any]]] = []
    for fmt in formats:
        res = str(fmt.get("resolution") or fmt.get("format_note") or "")
        height = 0
        m = re.search(r"(\d+)p", res, re.I)
        if m:
            height = int(m.group(1))
        has_video = (fmt.get("vcodec") not in (None, "none")) or (
            fmt.get("video_ext") not in (None, "none")
        )
        if not has_video:
            continue
        if height and height > max_height:
            continue
        scored.append((height or 720, fmt))
    if not scored:
        for fmt in formats:
            if fmt.get("vcodec") not in (None, "none"):
                return fmt
        return formats[0]
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def _download_task_file(base: str, task_id: int, format_id: str) -> bytes:
    query = urllib.parse.urlencode({"format_id": format_id})
    url = f"{base}/task/{task_id}/download/?{query}"
    headers = {
        "Referer": f"{base}/download/{task_id}/",
        "X-Requested-With": "XMLHttpRequest",
    }
    return _http(url, headers=headers, timeout=180)


def fetch_douyin_via_viddown(
    video_url: str,
    *,
    max_height: int = 720,
    max_wait_seconds: float = 120,
) -> dict[str, Any]:
    """Parse *video_url* on VidDown and return metadata + raw mp4 bytes."""
    if not viddown_enabled():
        raise VidDownError("VidDown disabled (VIDDOWN_ENABLED=0)")

    base = viddown_base_url()
    csrf = _fetch_csrf(base)
    task_id = _start_task(base, video_url, csrf)
    info = _poll_task(base, task_id, max_wait_seconds=max_wait_seconds)
    formats = info.get("formats") or []
    if not formats:
        raise VidDownError("VidDown returned no downloadable formats")

    picked = _pick_format(formats, max_height)
    format_id = picked.get("format_id") or picked.get("id")
    if not format_id:
        raise VidDownError("VidDown format missing format_id")

    blob = _download_task_file(base, task_id, str(format_id))
    if len(blob) < 1024:
        raise VidDownError("VidDown download returned an unexpectedly small file")

    return {
        "task_id": task_id,
        "provider": "viddown",
        "metadata": {
            "title": info.get("title") or "",
            "duration": info.get("duration") or 0,
            "uploader": info.get("uploader") or "",
            "upload_date": "",
            "description": "",
            "view_count": 0,
            "like_count": 0,
            "resolution": picked.get("resolution") or "",
        },
        "video_bytes": blob,
        "format_id": str(format_id),
    }
