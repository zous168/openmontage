"""无声底片：同 file_id 幂等复用；keep_audio 跳过去音。"""

from __future__ import annotations

import pytest
from pathlib import Path

from plugins.mxai.content.video_audio import strip_audio_to_silent
from plugins.mxai.content.video_generate import _attach_silent_plate, poll_video_status


def test_strip_audio_reuses_existing_file(monkeypatch, tmp_path: Path) -> None:
    silent_dir = tmp_path / "silent"
    silent_dir.mkdir()
    out = silent_dir / "task-abc.mp4"
    out.write_bytes(b"already-silent")

    monkeypatch.setattr(
        "plugins.mxai.content.video_audio.silent_media_dir",
        lambda: silent_dir,
    )
    monkeypatch.setattr(
        "plugins.mxai.content.video_audio._find_ffmpeg",
        lambda: None,  # 若未短路会因缺 ffmpeg 失败
    )

    result = strip_audio_to_silent(
        "https://example.com/v.mp4",
        file_id="task-abc",
    )
    assert result["silent_file_id"] == "task-abc.mp4"
    assert Path(result["silent_path"]) == out.resolve()


def test_attach_silent_plate_skips_when_present() -> None:
    payload = {
        "task_id": "t1",
        "video_url": "https://example.com/v.mp4",
        "silent_video_url": "/content/voice-media/t1.mp4",
        "silent_path": "/tmp/t1.mp4",
    }
    out = _attach_silent_plate(payload)
    assert out["silent_video_url"] == "/content/voice-media/t1.mp4"


def test_attach_silent_plate_stable_file_id(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_strip(video_url, *, file_id=None):
        calls.append(str(file_id))
        return {
            "silent_path": f"/tmp/{file_id}.mp4",
            "silent_file_id": f"{file_id}.mp4",
            "silent_video_url": f"/content/voice-media/{file_id}.mp4",
        }

    monkeypatch.setattr(
        "plugins.mxai.content.video_audio.strip_audio_to_silent",
        _fake_strip,
    )
    p1 = _attach_silent_plate(
        {"task_id": "vid-99", "video_url": "https://example.com/a.mp4"}
    )
    p2 = _attach_silent_plate(
        {
            "task_id": "vid-99",
            "video_url": "https://example.com/a.mp4",
            "silent_video_url": p1["silent_video_url"],
            "silent_path": p1["silent_path"],
        }
    )
    assert calls == ["vid-99"]
    assert p2["silent_video_url"] == "/content/voice-media/vid-99.mp4"
    assert p1["silent_file_id"] == "vid-99.mp4"


def test_attach_silent_plate_skips_when_keep_audio(monkeypatch) -> None:
    calls: list[str] = []

    def _fake_strip(video_url, *, file_id=None):
        calls.append(str(file_id))
        return {
            "silent_path": f"/tmp/{file_id}.mp4",
            "silent_file_id": f"{file_id}.mp4",
            "silent_video_url": f"/content/voice-media/{file_id}.mp4",
        }

    monkeypatch.setattr(
        "plugins.mxai.content.video_audio.strip_audio_to_silent",
        _fake_strip,
    )
    out = _attach_silent_plate(
        {
            "task_id": "keep-1",
            "video_url": "https://example.com/a.mp4",
            "keep_audio": True,
        }
    )
    assert calls == []
    assert out.get("strip_skipped") is True
    assert "silent_video_url" not in out


@pytest.mark.asyncio
async def test_poll_mock_skips_silent_when_keep_audio(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = await poll_video_status("mock-task", keep_audio=True)
    assert out["keep_audio"] is True
    assert out.get("strip_skipped") is True
    assert "silent_video_url" not in out
    assert out["video_url"]


@pytest.mark.asyncio
async def test_poll_mock_still_silent_by_default(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    out = await poll_video_status("mock-task", keep_audio=False)
    assert out.get("silent_video_url")
