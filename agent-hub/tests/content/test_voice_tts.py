"""同 voice_id 批量 TTS；试听只读缓存（由生成写入）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from plugins.mxai.content.voice_library import (
    _MOCK_SYSTEM_VOICES,
    clone_voice,
    list_voices,
)
from plugins.mxai.content.voice_tts import (
    DEFAULT_PREVIEW_TEXT,
    preview_voice,
    resolve_speech_model,
    synthesize_shots,
)


@pytest.mark.asyncio
async def test_ensure_preview_sample_without_viral(monkeypatch, tmp_path) -> None:
    """音色管理 ensure：无仿爆款也可生成短样片。"""
    from plugins.mxai.content.voice_tts import ensure_voice_preview_sample

    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    out = await ensure_voice_preview_sample(voice_id="sys_default_female")
    assert out["cached"] is True
    assert out.get("ensured") is True
    assert Path(out["tts_path"]).is_file()
    again = await ensure_voice_preview_sample(voice_id="sys_default_female")
    assert again.get("ensured") is False
    assert again["tts_file_id"] == out["tts_file_id"]


def _patch_system_voices(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._system_voices",
        lambda: [dict(x) for x in _MOCK_SYSTEM_VOICES],
    )


def _fake_resolve(model: str = "IndexTTS-2"):
    def _resolve(voice=None, *, override=None):
        return (override or "").strip() or model

    return _resolve


def test_resolve_speech_model_builtin_skips_indextts(monkeypatch) -> None:
    """系统预设无参考音时，忽略 IndexTTS 覆盖，改选 CosyVoice。"""
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models.list_gateway_models",
        lambda purpose=None, mode=None: {
            "items": [
                {"model_name": "IndexTTS-2"},
                {"model_name": "cosyvoice-v3-flash"},
            ]
        },
    )
    name = resolve_speech_model(
        {"clone_kind": "builtin", "voice": "longanyang"},
        override="IndexTTS-2",
    )
    assert name == "cosyvoice-v3-flash"


@pytest.mark.asyncio
async def test_preview_not_ready_without_cache(monkeypatch, tmp_path) -> None:
    """无生成缓存时，试听只读接口返回 404。"""
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    with pytest.raises(HTTPException) as ei:
        await preview_voice(voice_id="sys_default_female", text="任意文案忽略")
    assert ei.value.status_code == 404
    assert ei.value.detail["code"] == "VOICE_PREVIEW_NOT_READY"


@pytest.mark.asyncio
async def test_generate_writes_preview_cache_then_preview_reads(monkeypatch, tmp_path) -> None:
    """生成配音写入试听缓存；试听只读命中，不再合成。"""
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    out = await synthesize_shots(
        voice_id="sys_default_female",
        shots=[
            {"id": 1, "prompt": "大家好，欢迎来到本场直播"},
            {"id": 2},
        ],
    )
    assert out["items"][0]["skipped"] is False
    assert out["items"][1]["skipped"] is True

    preview = await preview_voice(voice_id="sys_default_female")
    assert preview["cached"] is True
    assert preview["source"] == "preview_cache"
    assert preview["text"] == DEFAULT_PREVIEW_TEXT
    assert Path(preview["tts_path"]).is_file()
    assert preview["tts_url"].startswith("/content/voice-media/")
    # 试听样片 ≠ 分镜配音（禁止 copy 第一镜）
    assert Path(preview["tts_path"]).resolve() != Path(out["items"][0]["tts_path"]).resolve()
    assert preview["tts_file_id"] != out["items"][0]["tts_file_id"]

    # 列表应带上 preview_url
    listed = list_voices()
    female = next(v for v in listed["items"] if v["id"] == "sys_default_female")
    assert female.get("preview_url")


@pytest.mark.asyncio
async def test_preview_cache_hit_idempotent(monkeypatch, tmp_path) -> None:
    """二次试听同一缓存文件，mtime 不变。"""
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    await synthesize_shots(
        voice_id="sys_default_female",
        shots=[{"id": 1, "prompt": "缓存试听"}],
    )
    first = await preview_voice(voice_id="sys_default_female")
    mtime1 = Path(first["tts_path"]).stat().st_mtime_ns
    second = await preview_voice(voice_id="sys_default_female")
    assert second.get("cached") is True
    assert second["tts_file_id"] == first["tts_file_id"]
    assert Path(second["tts_path"]).stat().st_mtime_ns == mtime1


@pytest.mark.asyncio
async def test_mock_tts_batch(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    out = await synthesize_shots(
        voice_id="sys_default_female",
        shots=[
            {"id": 1, "prompt": "大家好，欢迎来到本场直播"},
            {"id": 2, "audio": {"dialogue_timeline": "这款鸭货真的很香"}},
            {"id": 3},
        ],
    )
    assert out["voice_id"] == "sys_default_female"
    assert out["mock"] is True
    assert len(out["items"]) == 3
    assert out["items"][0]["skipped"] is False
    assert out["items"][0]["tts_url"].startswith("/content/voice-media/")
    assert out["items"][0]["source"] == "mock_tone"
    assert out["items"][2]["skipped"] is True


@pytest.mark.asyncio
async def test_generate_uses_gateway_speech(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TTS_DIRECT", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    _patch_system_voices(monkeypatch)

    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts._require_speech_gateway",
        lambda: ("http://gw.test", "jwt-test"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("cosyvoice-v3-flash"),
    )

    captured: dict = {}

    def _fake_speech(**kwargs):
        captured.update(kwargs)
        return b"ID3fake-mp3-bytes-xxxxxxxx"

    monkeypatch.setattr(
        "tools.official_media_gateway.audio_speech",
        _fake_speech,
    )
    out = await synthesize_shots(
        voice_id="sys_default_female",
        shots=[{"id": 1, "prompt": "生成网关配音"}],
        tts_model="cosyvoice-v3-flash",
    )
    assert out["mock"] is False
    assert out["source"] == "gateway_speech"
    assert captured["base_url"] == "http://gw.test"
    assert captured["jwt"] == "jwt-test"
    assert captured["voice"] == "alloy"
    assert captured["model"] == "cosyvoice-v3-flash"
    assert Path(out["items"][0]["tts_path"]).read_bytes().startswith(b"ID3")

    preview = await preview_voice(
        voice_id="sys_default_female", tts_model="cosyvoice-v3-flash"
    )
    assert preview["source"] == "preview_cache"
    assert preview["cached"] is True


@pytest.mark.asyncio
async def test_generate_passes_prompt_audio_url(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TTS_DIRECT", raising=False)
    _patch_system_voices(monkeypatch)

    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts._require_speech_gateway",
        lambda: ("http://gw.test", "jwt-test"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("IndexTTS-2"),
    )

    captured: dict = {}

    def _fake_speech(**kwargs):
        captured.update(kwargs)
        return b"mp3-bytes"

    monkeypatch.setattr(
        "tools.official_media_gateway.audio_speech",
        _fake_speech,
    )

    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._upload_ref_to_public_url",
        lambda *_a, **_k: ("https://oss.example.com/ref.wav", "uploads/t/ref.wav"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._prepare_ref_audio",
        lambda raw, filename=None: (raw, filename or "ref.wav", 1.0),
    )
    row = await clone_voice(
        name="克隆",
        audio_bytes=b"RIFF....fake",
        filename="ref.wav",
    )
    out = await synthesize_shots(
        voice_id=row["id"],
        shots=[{"id": 1, "prompt": "生成克隆配音"}],
        tts_model="IndexTTS-2",
    )
    assert out["items"][0]["skipped"] is False
    extra = captured.get("extra_body") or {}
    assert extra.get("prompt_audio_url") == "https://oss.example.com/ref.wav"

    preview = await preview_voice(voice_id=row["id"], tts_model="IndexTTS-2")
    assert preview["cached"] is True


@pytest.mark.asyncio
async def test_generate_requires_login(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("TTS_DIRECT", raising=False)
    _patch_system_voices(monkeypatch)

    def _boom():
        raise HTTPException(
            status_code=401,
            detail={"code": "TTS_NOT_LOGGED_IN", "message": "未登录"},
        )

    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts._require_speech_gateway",
        _boom,
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("cosyvoice-v3-flash"),
    )
    with pytest.raises(HTTPException) as ei:
        await synthesize_shots(
            voice_id="sys_default_male",
            shots=[{"id": 1, "prompt": "x"}],
        )
    assert ei.value.status_code == 401
