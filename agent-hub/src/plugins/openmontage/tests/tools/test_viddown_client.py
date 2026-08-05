"""Tests for VidDown Douyin fallback client."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from plugins.openmontage.tools.analysis.viddown_client import (
    VidDownError,
    _pick_format,
    fetch_douyin_via_viddown,
)


def test_pick_format_prefers_720p_cap():
    formats = [
        {"format_id": "ratio_1080p", "resolution": "1080p", "vcodec": "h264"},
        {"format_id": "ratio_720p", "resolution": "720p", "vcodec": "h264"},
    ]
    picked = _pick_format(formats, 720)
    assert picked["format_id"] == "ratio_720p"


def test_fetch_douyin_via_viddown_happy_path():
    home_html = '<input name="csrfmiddlewaretoken" value="abc123">'
    info_payload = {
        "title": "demo",
        "formats": [
            {"format_id": "ratio_720p", "resolution": "720p", "vcodec": "h264", "ext": "mp4"},
        ],
    }

    def fake_http(url, *, method="GET", data=None, headers=None, timeout=60):
        if method == "POST" and url.rstrip("/").endswith("viddown.cn"):
            return json.dumps({"task_id": 99}).encode()
        if url.endswith("viddown.cn/") or url.endswith("www.viddown.cn/"):
            return home_html.encode()
        if url.endswith("/task/99/info/"):
            return json.dumps(info_payload).encode()
        if "/task/99/download/" in url:
            return b"\x00\x00\x00\x18ftypmp42" + b"x" * 2048
        raise AssertionError(f"unexpected url {url} {method}")

    with patch("plugins.openmontage.tools.analysis.viddown_client._http", side_effect=fake_http):
        result = fetch_douyin_via_viddown("https://v.douyin.com/example/")

    assert result["task_id"] == 99
    assert result["metadata"]["title"] == "demo"
    assert len(result["video_bytes"]) > 1024


def test_fetch_douyin_via_viddown_parse_failure():
    home_html = '<input name="csrfmiddlewaretoken" value="abc123">'

    def fake_http(url, *, method="GET", data=None, headers=None, timeout=60):
        if method == "POST" and url.rstrip("/").endswith("viddown.cn"):
            return json.dumps({"task_id": 1}).encode()
        if url.endswith("viddown.cn/") or url.endswith("www.viddown.cn/"):
            return home_html.encode()
        if url.endswith("/task/1/info/"):
            return json.dumps({"status": "failed", "error": "bad link"}).encode()
        raise AssertionError(url)

    with patch("plugins.openmontage.tools.analysis.viddown_client._http", side_effect=fake_http):
        with pytest.raises(VidDownError, match="bad link"):
            fetch_douyin_via_viddown("https://v.douyin.com/example/")


def test_normalize_media_url_from_bootstrap():
    from plugins.openmontage.backlot.bootstrap import normalize_media_url

    share = "复制打开抖音 https://v.douyin.com/tyV7nsNEpOw/ 看看"
    assert normalize_media_url(share) == "https://v.douyin.com/tyV7nsNEpOw/"
