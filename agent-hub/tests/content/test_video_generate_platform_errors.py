"""视频生成主路径错误：平台网关优先，不引导去配 DASHSCOPE_API_KEY。"""

from __future__ import annotations

import pytest
import httpx
from fastapi import HTTPException

from plugins.mxai.content.video_generate import is_transient_http_error, submit_video_clip


@pytest.mark.asyncio
async def test_platform_path_missing_gateway_url(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)
    monkeypatch.delenv("WAN_T2V_DIRECT", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: None,
    )
    monkeypatch.setattr(
        "core.platform.gateway_base_url.resolve_llm_gateway_base_url",
        lambda: "",
    )
    monkeypatch.setattr(
        "tools.official_media_gateway.current_device_jwt",
        lambda: "jwt-ok",
    )

    with pytest.raises(HTTPException) as ei:
        await submit_video_clip(prompt="近景口播测试足够长", model="wan2.7-t2v", duration_sec=5)
    assert ei.value.status_code == 503
    assert ei.value.detail["code"] == "VIDEO_GATEWAY_UNCONFIGURED"
    assert "DASHSCOPE" not in ei.value.detail["message"]


@pytest.mark.asyncio
async def test_platform_path_missing_login(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.delenv("VIDEO_GEN_DIRECT", raising=False)
    monkeypatch.setattr(
        "plugins.mxai.content.video_generate._resolve_gateway",
        lambda: None,
    )
    monkeypatch.setattr(
        "core.platform.gateway_base_url.resolve_llm_gateway_base_url",
        lambda: "http://gw.example.com",
    )
    monkeypatch.setattr(
        "tools.official_media_gateway.current_device_jwt",
        lambda: "",
    )

    with pytest.raises(HTTPException) as ei:
        await submit_video_clip(prompt="近景口播测试足够长", model="wan2.7-t2v", duration_sec=5)
    assert ei.value.status_code == 401
    assert ei.value.detail["code"] == "VIDEO_NOT_LOGGED_IN"
    assert "DASHSCOPE" not in ei.value.detail["message"]


def test_is_transient_http_error_detects_disconnect_phrase() -> None:
    assert is_transient_http_error(
        httpx.RemoteProtocolError("Server disconnected without sending a response.")
    )
    assert not is_transient_http_error(ValueError("bad prompt"))
