"""LT-045.06.01 / .06.02：官方媒体网关辅助 + 图片/视频走网关（mock，无真 FAL）。"""
from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# official_media_gateway helpers
# ---------------------------------------------------------------------------


def test_resolve_official_skips_when_byok_fal_key(monkeypatch):
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://gw:4000")
    monkeypatch.setenv("FAL_KEY", "fal-byok")
    monkeypatch.setattr(
        "tools.official_media_gateway.current_device_jwt",
        lambda: "jwt-token",
    )
    from tools.official_media_gateway import resolve_official_media_gateway

    assert resolve_official_media_gateway() is None


def test_resolve_official_requires_gateway_and_jwt(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://gw:4000")
    monkeypatch.setattr(
        "tools.official_media_gateway.current_device_jwt",
        lambda: "device.jwt.here",
    )
    # fal_key_is_configured may also check config store — stub it
    monkeypatch.setattr(
        "tools.tool_backend_helpers.fal_key_is_configured",
        lambda: False,
    )
    from tools.official_media_gateway import resolve_official_media_gateway

    assert resolve_official_media_gateway() == ("http://gw:4000", "device.jwt.here")


def test_resolve_official_none_without_jwt(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setenv("LLM_GATEWAY_BASE_URL", "http://gw:4000")
    monkeypatch.setattr(
        "tools.official_media_gateway.current_device_jwt",
        lambda: "",
    )
    monkeypatch.setattr(
        "tools.tool_backend_helpers.fal_key_is_configured",
        lambda: False,
    )
    from tools.official_media_gateway import resolve_official_media_gateway

    assert resolve_official_media_gateway() is None


def test_images_generations_402_friendly(monkeypatch):
    import httpx
    from tools.official_media_gateway import images_generations

    class FakeResp:
        status_code = 402
        text = '{"error":"insufficient_credits"}'

        def json(self):
            return {"error": "insufficient_credits"}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    monkeypatch.setattr(
        "tools.official_media_gateway.credits_insufficient_message",
        lambda: "算力点不足。请在管理后台充值后再试。",
    )
    with pytest.raises(ValueError, match="算力点不足"):
        images_generations(
            base_url="http://gw:4000",
            jwt="jwt",
            model="fal-ai/flux-2-pro",
            prompt="a cat",
        )


def test_images_generations_ok(monkeypatch):
    import httpx
    from tools.official_media_gateway import images_generations

    class FakeResp:
        status_code = 200
        text = "{}"

        def json(self):
            return {"data": [{"url": "https://cdn.example/a.png"}]}

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            assert url.endswith("/v1/images/generations")
            assert headers["Authorization"] == "Bearer jwt"
            assert json["model"] == "fal-ai/flux-2-pro"
            return FakeResp()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    out = images_generations(
        base_url="http://gw:4000",
        jwt="jwt",
        model="fal-ai/flux-2-pro",
        prompt="a cat",
        n=1,
    )
    assert out["data"][0]["url"].endswith("a.png")


def test_fal_queue_submit_and_result(monkeypatch):
    import httpx
    from tools.official_media_gateway import fal_queue_result, fal_queue_submit

    calls = []

    class FakeResp:
        def __init__(self, status_code, body):
            self.status_code = status_code
            self.text = json.dumps(body)
            self.content = self.text.encode()
            self._body = body

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, json=None, headers=None):
            calls.append(("POST", url))
            assert "/fal/fal-ai/pixverse/v6/text-to-video" in url
            return FakeResp(200, {"request_id": "rid-abc", "status": "IN_QUEUE"})

        def get(self, url, headers=None):
            calls.append(("GET", url))
            if url.endswith("/status"):
                return FakeResp(200, {"status": "COMPLETED"})
            return FakeResp(
                200,
                {"video": {"url": "https://cdn.fal.ai/v.mp4"}, "request_id": "rid-abc"},
            )

    monkeypatch.setattr(httpx, "Client", FakeClient)
    sub = fal_queue_submit(
        base_url="http://gw:4000",
        jwt="jwt",
        endpoint="fal-ai/pixverse/v6/text-to-video",
        arguments={"prompt": "wave", "duration": "5"},
    )
    assert sub["request_id"] == "rid-abc"
    result = fal_queue_result(
        base_url="http://gw:4000",
        jwt="jwt",
        endpoint="fal-ai/pixverse/v6/text-to-video",
        request_id="rid-abc",
        poll_interval=0.01,
        timeout=5.0,
    )
    assert result["video"]["url"].endswith("v.mp4")
    assert any(c[0] == "GET" and c[1].endswith("/status") for c in calls)


# ---------------------------------------------------------------------------
# image_generation_tool official path
# ---------------------------------------------------------------------------


def test_image_generate_via_official_gateway(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(
        "tools.tool_backend_helpers.fal_key_is_configured",
        lambda: False,
    )
    monkeypatch.setattr(
        "tools.image_generation_tool._resolve_managed_fal_gateway",
        lambda: None,
    )
    monkeypatch.setattr(
        "tools.image_generation_tool._resolve_official_image_gateway",
        lambda: ("http://gw:4000", "jwt"),
    )
    monkeypatch.setattr(
        "tools.image_generation_tool._generate_via_official_image_gateway",
        lambda model_id, prompt, arguments, base_url, jwt: {
            "images": [{"url": "https://cdn.example/out.png", "width": 1, "height": 1}]
        },
    )
    # avoid upscaler / debug side effects
    import tools.image_generation_tool as it

    monkeypatch.setattr(it, "_resolve_fal_model", lambda: ("fal-ai/flux-2-pro", it.FAL_MODELS["fal-ai/flux-2-pro"]))

    raw = it.image_generate_tool(prompt="sunset over ocean")
    data = json.loads(raw)
    assert data["success"] is True
    assert data["image"] == "https://cdn.example/out.png"


def test_image_generate_402_surfaces_message(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(
        "tools.tool_backend_helpers.fal_key_is_configured",
        lambda: False,
    )
    monkeypatch.setattr(
        "tools.image_generation_tool._resolve_managed_fal_gateway",
        lambda: None,
    )
    monkeypatch.setattr(
        "tools.image_generation_tool._resolve_official_image_gateway",
        lambda: ("http://gw:4000", "jwt"),
    )

    def boom(*a, **k):
        raise ValueError("算力点不足。请在管理后台充值后再试。")

    monkeypatch.setattr(
        "tools.image_generation_tool._generate_via_official_image_gateway",
        boom,
    )
    import tools.image_generation_tool as it

    monkeypatch.setattr(
        it,
        "_resolve_fal_model",
        lambda: ("fal-ai/flux-2-pro", it.FAL_MODELS["fal-ai/flux-2-pro"]),
    )
    raw = it.image_generate_tool(prompt="x")
    data = json.loads(raw)
    assert data["success"] is False
    assert "算力点不足" in data["error"]


def test_check_fal_api_key_true_with_official(monkeypatch):
    monkeypatch.setattr(
        "tools.tool_backend_helpers.fal_key_is_configured",
        lambda: False,
    )
    monkeypatch.setattr(
        "tools.image_generation_tool._resolve_managed_fal_gateway",
        lambda: None,
    )
    monkeypatch.setattr(
        "tools.image_generation_tool._resolve_official_image_gateway",
        lambda: ("http://gw:4000", "jwt"),
    )
    import tools.image_generation_tool as it

    assert it.check_fal_api_key() is True


# ---------------------------------------------------------------------------
# video_gen/fal official path
# ---------------------------------------------------------------------------


def test_video_generate_via_official_gateway(monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    monkeypatch.setattr(
        "tools.tool_backend_helpers.fal_key_is_configured",
        lambda: False,
    )

    import plugins.video_gen.fal as fal_video

    monkeypatch.setattr(fal_video, "_resolve_managed_fal_video_gateway", lambda: None)
    monkeypatch.setattr(
        fal_video,
        "_resolve_official_video_gateway",
        lambda: ("http://gw:4000", "jwt"),
    )

    class Ready:
        def get(self):
            return {"video": {"url": "https://cdn.fal.ai/out.mp4"}}

    monkeypatch.setattr(
        fal_video,
        "_submit_fal_video_request",
        lambda endpoint, arguments: Ready(),
    )

    provider = fal_video.FALVideoGenProvider()
    out = provider.generate(prompt="ocean waves", duration=5)
    assert out["success"] is True
    assert out["video"] == "https://cdn.fal.ai/out.mp4"
    assert out["provider"] == "fal"

def test_video_check_available_with_official(monkeypatch):
    monkeypatch.setattr(
        "tools.tool_backend_helpers.fal_key_is_configured",
        lambda: False,
    )
    import plugins.video_gen.fal as fal_video

    monkeypatch.setattr(fal_video, "_resolve_managed_fal_video_gateway", lambda: None)
    monkeypatch.setattr(
        fal_video,
        "_resolve_official_video_gateway",
        lambda: ("http://gw:4000", "jwt"),
    )
    assert fal_video._check_fal_video_available() is True

def test_humanize_speech_freetier():
    from tools.official_media_gateway import humanize_speech_error

    msg = humanize_speech_error(
        "Free quota exhausted. AllocationQuota.FreeTierOnly"
    )
    assert "免费额度" in msg


def test_humanize_speech_access_denied():
    from tools.official_media_gateway import humanize_speech_error

    msg = humanize_speech_error(
        "403 Forbidden AccessDenied prompt_audio http://x:8900/a.wav"
    )
    assert "参考音频" in msg


def test_humanize_speech_indextts_url_not_valid_minio():
    from tools.official_media_gateway import humanize_speech_error

    msg = humanize_speech_error(
        "prompt_audio_url http://8.156.87.157:8900/mxai-dev/x.m4a is not valid"
    )
    assert "内网" in msg or "私有" in msg or "开放链" in msg


def test_humanize_speech_indextts_cs_ref_not_valid():
    from tools.official_media_gateway import humanize_speech_error

    msg = humanize_speech_error(
        "prompt_audio_url http://srv.zerohalu.com:8080/api/public/v1/voice/ref-audio"
        "?key=x.m4a is not valid"
    )
    assert "废弃" in msg or "重新克隆" in msg or "OSS" in msg


def test_humanize_speech_internal_server_error():
    from tools.official_media_gateway import humanize_speech_error

    msg = humanize_speech_error("Internal server error", status_code=500)
    assert "HTTP 500" in msg
    assert "网关" in msg


def test_extract_gateway_error_message_nested():
    from tools.official_media_gateway import extract_gateway_error_message

    assert (
        extract_gateway_error_message(
            {"error": {"message": "Free quota exhausted", "code": "x"}}
        )
        == "Free quota exhausted"
    )
    assert (
        extract_gateway_error_message(
            {"detail": {"message": "音色试听合成失败"}}
        )
        == "音色试听合成失败"
    )


def test_audio_speech_surfaces_humanized_error(monkeypatch):
    from tools import official_media_gateway as mod

    class FakeResp:
        status_code = 502
        text = '{"error":{"message":"Free quota exhausted","code":"AllocationQuota.FreeTierOnly"}}'
        content = b""

        def json(self):
            return {
                "error": {
                    "message": "Free quota exhausted",
                    "code": "AllocationQuota.FreeTierOnly",
                }
            }

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, *a, **k):
            return FakeResp()

    import httpx

    monkeypatch.setattr(httpx, "Client", FakeClient)

    with pytest.raises(ValueError) as ei:
        mod.audio_speech(
            base_url="http://gw",
            jwt="t",
            model="cosyvoice-v3-flash",
            input_text="hi",
            voice="alloy",
        )
    assert "免费额度" in str(ei.value)
