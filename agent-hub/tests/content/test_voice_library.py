"""声音库 list / mock 克隆 / 删除。"""

from __future__ import annotations

import io
import math
import struct
import wave

import pytest
from fastapi import HTTPException

from plugins.mxai.content.voice_library import (
    _MOCK_SYSTEM_VOICES,
    _prepare_ref_audio,
    _public_voice_row,
    clone_voice,
    delete_voice,
    extract_oss_key_from_url,
    get_voice,
    list_voices,
)


def _tiny_wav_bytes(duration_sec: float = 0.3) -> bytes:
    """可解码的短 wav，供非 Mock 克隆校验。"""
    rate = 16000
    n = max(256, int(rate * duration_sec))
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        for i in range(n):
            val = int(6000 * math.sin(2 * math.pi * 440 * i / rate))
            wf.writeframes(struct.pack("<h", val))
    return buf.getvalue()


def _fake_resolve(model: str = "IndexTTS-2"):
    def _resolve(voice=None, *, override=None):
        return (override or "").strip() or model

    return _resolve


def _fake_enroll(model: str | None = None):
    def _resolve(*, override=None):
        if (override or "").strip():
            return override.strip()
        return model

    return _resolve


def _patch_system_voices(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._system_voices",
        lambda: [dict(x) for x in _MOCK_SYSTEM_VOICES],
    )


def test_extract_oss_key_from_minio_url() -> None:
    url = (
        "http://8.156.87.157:8900/mxai-dev/uploads/"
        "00000000-0000-0000-0000-000000000002/abc.mp3"
    )
    assert (
        extract_oss_key_from_url(url)
        == "uploads/00000000-0000-0000-0000-000000000002/abc.mp3"
    )


def test_extract_oss_key_from_oss_public_url() -> None:
    key = "uploads/00000000-0000-0000-0000-000000000002/abc.wav"
    url = f"https://oss.example.com/mxai-dev/{key}"
    assert extract_oss_key_from_url(url) == key


def test_public_voice_row_preview_not_ref_audio() -> None:
    """列表 preview_url 不得用参考音冒充试听。"""
    row = _public_voice_row(
        {
            "id": "u1",
            "name": "x",
            "ref_file_id": "ref_a.wav",
            "preview_file_id": "preview_u1_abc.mp3",
        }
    )
    assert row["ref_url"] == "/content/voice-media/ref_a.wav"
    assert row["preview_url"] == "/content/voice-media/preview_u1_abc.mp3"
    bare = _public_voice_row({"id": "u2", "name": "y", "ref_file_id": "ref_b.wav"})
    assert bare["ref_url"] == "/content/voice-media/ref_b.wav"
    assert bare.get("preview_url") in (None, "")


def test_prepare_ref_audio_always_normalizes_wav(monkeypatch) -> None:
    """即便源已是 wav，也走 ffmpeg 规范化（截取目标时长）。"""
    raw = _tiny_wav_bytes(0.4)
    normalized = _tiny_wav_bytes(0.35)

    def _fake_convert(audio_bytes, *, filename=None, max_sec=30.0):
        assert max_sec == 30.0
        assert audio_bytes == raw
        return normalized

    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._convert_ref_audio_to_wav",
        _fake_convert,
    )
    out, name, dur = _prepare_ref_audio(raw, "a.wav")
    assert name == "ref.wav"
    assert out == normalized
    assert dur > 0.2


def test_prepare_ref_audio_converts_m4a(monkeypatch) -> None:
    wav = _tiny_wav_bytes(0.4)

    def _fake_convert(audio_bytes, *, filename=None, max_sec=30.0):
        assert str(filename).endswith(".m4a")
        assert max_sec == 30.0
        return wav

    calls = {"n": 0}

    def _probe(audio_bytes, filename=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return (0.0, 0, 0, True)
        return (0.4, 1, 16000, True)

    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._convert_ref_audio_to_wav",
        _fake_convert,
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._probe_ref_audio",
        _probe,
    )
    out, name, dur = _prepare_ref_audio(b"\x00\x00\x00\x18ftyp" + b"x" * 400, "x.m4a")
    assert name == "ref.wav"
    assert out == wav
    assert dur == 0.4
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_list_voices_includes_system(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    out = list_voices()
    assert out["system"]
    assert any(v["id"].startswith("sys_") for v in out["items"])


@pytest.mark.asyncio
async def test_list_voices_cosyvoice_seeds(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._resolve_builtin_tts_model",
        lambda wait=True: "cosyvoice-v3-flash",
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._load_preset_voices",
        lambda: [],
    )
    out = list_voices()
    assert any(v.get("tts_model") == "cosyvoice-v3-flash" for v in out["system"])
    assert any(v.get("voice") == "longanyang" for v in out["system"])


@pytest.mark.asyncio
async def test_mock_clone_and_delete(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("IndexTTS-2"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_enroll_model",
        _fake_enroll(None),
    )
    row = await clone_voice(
        name="测试音色",
        audio_bytes=b"RIFF....fake",
        filename="ref.wav",
    )
    assert row["id"].startswith("clone_")
    assert row["clone_kind"] == "ref_prompt"
    assert get_voice(row["id"])["name"] == "测试音色"
    assert delete_voice(row["id"])["ok"] is True
    with pytest.raises(HTTPException) as ei:
        get_voice(row["id"])
    assert ei.value.status_code == 404


@pytest.mark.asyncio
async def test_cannot_delete_system(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as ei:
        delete_voice("sys_default_female")
    assert ei.value.status_code == 422


@pytest.mark.asyncio
async def test_clone_local_file_uses_ref_prompt(monkeypatch, tmp_path) -> None:
    """非 Mock：默认 ref_prompt，只存 prompt_audio_url，不 enroll。"""
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("IndexTTS-2"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_enroll_model",
        _fake_enroll(None),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._upload_ref_to_public_url",
        lambda *_a, **_k: ("https://oss.example.com/ref.wav", "uploads/t/ref.wav"),
    )

    row = await clone_voice(
        name="文件克隆",
        audio_bytes=_tiny_wav_bytes(),
        filename="ref.wav",
    )
    assert row["mock"] is False
    assert row["clone_kind"] == "ref_prompt"
    assert row["prompt_audio_url"] == "https://oss.example.com/ref.wav"
    assert row["voice"] == "alloy"
    assert row["tts_model"] == "IndexTTS-2"


@pytest.mark.asyncio
async def test_clone_tts_model_override(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("IndexTTS-2"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_enroll_model",
        _fake_enroll(None),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.gateway_models.list_gateway_models",
        lambda **_k: {"items": [{"model_name": "IndexTTS-2", "mode": "audio_speech"}]},
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._upload_ref_to_public_url",
        lambda *_a, **_k: ("https://oss.example.com/ref.wav", None),
    )
    row = await clone_voice(
        name="指定模型",
        audio_bytes=_tiny_wav_bytes(),
        filename="ref.wav",
        tts_model="IndexTTS-2-pro",
    )
    assert row["tts_model"] == "IndexTTS-2-pro"
    assert row["clone_kind"] == "ref_prompt"


@pytest.mark.asyncio
async def test_clone_from_materials_asset(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("IndexTTS-2"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_enroll_model",
        _fake_enroll(None),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._load_materials_audio_bytes",
        lambda _aid: (_tiny_wav_bytes(), "mat-ref.wav"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_library._upload_ref_to_public_url",
        lambda *_a, **_k: ("https://oss.example.com/mat.wav", "uploads/t/mat.wav"),
    )
    row = await clone_voice(
        name="素材克隆",
        audio_bytes=b"",
        mat_asset_id=42,
    )
    assert row["mat_asset_id"] == 42
    assert row["prompt_audio_url"] == "https://oss.example.com/mat.wav"


@pytest.mark.asyncio
async def test_clone_without_bytes_or_url_fails(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as ei:
        await clone_voice(name="空", audio_bytes=b"", filename="ref.wav")
    assert ei.value.status_code == 422
    assert ei.value.detail["code"] == "AUDIO_REQUIRED"


@pytest.mark.asyncio
async def test_clone_name_required(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    with pytest.raises(HTTPException) as ei:
        await clone_voice(name="  ", audio_bytes=b"x", filename="a.wav")
    assert ei.value.status_code == 422
    assert ei.value.detail["code"] == "VOICE_NAME_REQUIRED"


@pytest.mark.asyncio
async def test_clone_name_duplicate(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("IndexTTS-2"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_enroll_model",
        _fake_enroll(None),
    )
    await clone_voice(name="星姐", audio_bytes=b"RIFF....fake", filename="a.wav")
    with pytest.raises(HTTPException) as ei:
        await clone_voice(name=" 星姐 ", audio_bytes=b"RIFF....fake", filename="b.wav")
    assert ei.value.status_code == 409
    assert ei.value.detail["code"] == "VOICE_NAME_DUPLICATE"


@pytest.mark.asyncio
async def test_mock_clone_sets_mock_flag(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("mock-tts"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_enroll_model",
        _fake_enroll(None),
    )
    row = await clone_voice(
        name="联调音色",
        audio_bytes=b"RIFF....fake",
        filename="ref.wav",
    )
    assert row["mock"] is True
    assert str(row["voice"]).startswith("mock-")


@pytest.mark.asyncio
async def test_clone_via_gateway_enroll(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("cosyvoice-v3-flash"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_enroll_model",
        _fake_enroll("cosyvoice-v3-flash-enroll"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts._require_speech_gateway",
        lambda: ("http://gw.test", "jwt-test"),
    )

    def _fake_speech(**kwargs):
        assert kwargs["model"] == "cosyvoice-v3-flash-enroll"
        assert kwargs["extra_body"]["mxai_enroll"] is True
        assert kwargs["extra_body"]["target_model"] == "cosyvoice-v3-flash"
        assert kwargs["extra_body"]["audio_url"].startswith("https://")
        return b'{"voice":"cosy-clone-xyz","voice_id":"cosy-clone-xyz","mxai_enroll":true}'

    monkeypatch.setattr(
        "tools.official_media_gateway.audio_speech",
        _fake_speech,
    )
    row = await clone_voice(
        name="网关克隆",
        audio_bytes=_tiny_wav_bytes(),
        filename="ref.wav",
        audio_url="https://example.com/ref.wav",
    )
    assert row["mock"] is False
    assert row["clone_kind"] == "enroll"
    assert row["voice"] == "cosy-clone-xyz"
    assert row["tts_model"] == "cosyvoice-v3-flash"
    assert row["enroll_model"] == "cosyvoice-v3-flash-enroll"


@pytest.mark.asyncio
async def test_clone_enroll_requires_enroll_model(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MXAI_MOCK", "0")
    monkeypatch.setenv("HUB_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_speech_model",
        _fake_resolve("cosyvoice-v3-flash"),
    )
    monkeypatch.setattr(
        "plugins.mxai.content.voice_tts.resolve_enroll_model",
        _fake_enroll(None),
    )
    with pytest.raises(HTTPException) as ei:
        await clone_voice(
            name="缺复刻模型",
            audio_bytes=_tiny_wav_bytes(),
            filename="ref.wav",
            audio_url="https://example.com/ref.wav",
        )
    assert ei.value.status_code == 503
    assert ei.value.detail["code"] == "ENROLL_MODEL_NOT_CONFIGURED"
