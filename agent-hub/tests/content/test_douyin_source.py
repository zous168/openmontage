"""抖音分享链接解析（viddown）单元测试。"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import HTTPException

from plugins.mxai.content.douyin_source import (
    extract_douyin_url,
    is_douyin_url,
    pick_best_mp4_url,
    resolve_douyin_direct_url,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("https://v.douyin.com/iAbc123/", "https://v.douyin.com/iAbc123/"),
        (
            "8- 长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/cZrGrGkT5VI/ 7@8.com :1pm",
            "https://v.douyin.com/cZrGrGkT5VI/",
        ),
        (
            "看了吗 https://www.douyin.com/video/7123456789012345678 真好看",
            "https://www.douyin.com/video/7123456789012345678",
        ),
        ("https://cdn.example.com/a.mp4", None),
        ("没有链接的分享文案", None),
        ("", None),
    ],
)
def test_extract_douyin_url(text: str, expected: str | None) -> None:
    assert extract_douyin_url(text) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://v.douyin.com/iAbc123/", True),
        ("http://v.douyin.com/xyz", True),
        (
            "8- 长按复制此条消息，打开抖音搜索，查看TA的更多作品。 https://v.douyin.com/cZrGrGkT5VI/ 7@8.com :1pm",
            True,
        ),
        ("https://www.douyin.com/video/7123456789012345678", True),
        ("https://www.iesdouyin.com/share/video/7123456789012345678/", True),
        ("https://cdn.example.com/a.mp4", False),
        ("https://www.douyin.com/user/self", False),
        ("https://www.kuaishou.com/short-video/xxx", False),
        ("", False),
        ("  ", False),
        ("C:\\\\Videos\\\\demo.mp4", False),
    ],
)
def test_is_douyin_url(url: str, expected: bool) -> None:
    assert is_douyin_url(url) is expected


def test_pick_best_mp4_prefers_highest_resolution() -> None:
    url, res = pick_best_mp4_url(
        [
            {"ext": "mp4", "url": "https://cdn.example.com/720.mp4", "resolution": "720p"},
            {"ext": "mp4", "url": "https://cdn.example.com/1080.mp4", "resolution": "1080p"},
            {"ext": "m4a", "url": "https://cdn.example.com/audio.m4a", "resolution": "audio"},
        ]
    )
    assert url == "https://cdn.example.com/1080.mp4"
    assert res == "1080p"


def test_pick_best_mp4_empty_raises() -> None:
    with pytest.raises(HTTPException) as ei:
        pick_best_mp4_url([])
    assert ei.value.status_code == 502
    assert ei.value.detail["code"] == "DOUYIN_PARSE_FAILED"


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        text: str = "",
        json_data: Any = None,
    ) -> None:
        self.status_code = status_code
        self.text = text
        self._json = json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=httpx.Request("GET", "https://www.viddown.cn/"),
                response=httpx.Response(self.status_code),
            )

    def json(self) -> Any:
        if self._json is None:
            raise json.JSONDecodeError("no", "", 0)
        return self._json


class _FakeClient:
    """模拟 viddown：GET / → CSRF；POST / → task_id；GET /task/{id}/info/ 按序返回。"""

    def __init__(self, info_sequence: list[_FakeResponse], *, submit: _FakeResponse | None = None) -> None:
        self._info_sequence = list(info_sequence)
        self._submit = submit or _FakeResponse(json_data={"task_id": 99})
        self.poll_count = 0

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get(self, path: str, **kwargs: Any) -> _FakeResponse:
        if path == "/":
            return _FakeResponse(
                text='<input type="hidden" name="csrfmiddlewaretoken" value="tok123">'
            )
        if path.startswith("/task/") and path.endswith("/info/"):
            self.poll_count += 1
            if not self._info_sequence:
                return _FakeResponse(json_data={"status": "processing"})
            return self._info_sequence.pop(0)
        return _FakeResponse(status_code=404, text="missing")

    async def post(self, path: str, **kwargs: Any) -> _FakeResponse:
        return self._submit


@pytest.mark.asyncio
async def test_resolve_success_picks_1080p(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.content.douyin_source.POLL_INTERVAL_SEC",
        0.01,
    )
    client = _FakeClient(
        [
            _FakeResponse(json_data={"status": "processing"}),
            _FakeResponse(
                json_data={
                    "formats": [
                        {
                            "ext": "mp4",
                            "url": "https://aweme.snssdk.com/play?ratio=720p",
                            "resolution": "720p",
                            "format_id": "ratio_720p",
                        },
                        {
                            "ext": "mp4",
                            "url": "https://aweme.snssdk.com/play?ratio=1080p",
                            "resolution": "1080p",
                            "format_id": "ratio_1080p",
                        },
                    ]
                }
            ),
        ]
    )
    monkeypatch.setattr(
        "plugins.mxai.content.douyin_source.httpx.AsyncClient",
        lambda **kwargs: client,
    )
    out = await resolve_douyin_direct_url("https://v.douyin.com/iTest/")
    assert out == "https://aweme.snssdk.com/play?ratio=1080p"
    assert client.poll_count >= 2


@pytest.mark.asyncio
async def test_resolve_task_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("plugins.mxai.content.douyin_source.POLL_INTERVAL_SEC", 0.01)
    client = _FakeClient(
        [
            _FakeResponse(
                json_data={"status": "failed", "error_message": "平台接口变动"}
            )
        ]
    )
    monkeypatch.setattr(
        "plugins.mxai.content.douyin_source.httpx.AsyncClient",
        lambda **kwargs: client,
    )
    with pytest.raises(HTTPException) as ei:
        await resolve_douyin_direct_url("https://v.douyin.com/iFail/")
    assert ei.value.status_code == 502
    assert ei.value.detail["code"] == "DOUYIN_PARSE_FAILED"
    assert "平台接口变动" in ei.value.detail["message"]


@pytest.mark.asyncio
async def test_resolve_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("plugins.mxai.content.douyin_source.POLL_INTERVAL_SEC", 0.01)
    monkeypatch.setattr("plugins.mxai.content.douyin_source.POLL_TIMEOUT_SEC", 0.05)
    client = _FakeClient(
        [
            _FakeResponse(json_data={"status": "processing"}),
            _FakeResponse(json_data={"status": "processing"}),
            _FakeResponse(json_data={"status": "processing"}),
            _FakeResponse(json_data={"status": "processing"}),
            _FakeResponse(json_data={"status": "processing"}),
            _FakeResponse(json_data={"status": "processing"}),
            _FakeResponse(json_data={"status": "processing"}),
            _FakeResponse(json_data={"status": "processing"}),
        ]
    )
    monkeypatch.setattr(
        "plugins.mxai.content.douyin_source.httpx.AsyncClient",
        lambda **kwargs: client,
    )
    with pytest.raises(HTTPException) as ei:
        await resolve_douyin_direct_url("https://v.douyin.com/iSlow/")
    assert ei.value.status_code == 504
    assert ei.value.detail["code"] == "DOUYIN_PARSE_TIMEOUT"
