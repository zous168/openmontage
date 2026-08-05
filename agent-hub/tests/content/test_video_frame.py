"""上一镜尾帧 → 下一镜首帧参考（模型无关）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from plugins.mxai.content.video_frame import (
    extract_last_frame_data_url,
    resolve_reference_image,
)
from plugins.mxai.content.video_generate import submit_video_clip


def test_extract_last_frame_local(tmp_path: Path) -> None:
    ffmpeg = __import__("shutil").which("ffmpeg")
    if not ffmpeg:
        pytest.skip("ffmpeg not installed")
    video = tmp_path / "tiny.mp4"
    import subprocess

    subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=red:s=320x240:d=0.5",
            "-pix_fmt",
            "yuv420p",
            str(video),
        ],
        check=True,
        timeout=30,
    )
    data_url = extract_last_frame_data_url(str(video))
    assert data_url.startswith("data:image/jpeg;base64,")
    assert len(data_url) > 80


def test_resolve_prev_overrides_img(monkeypatch) -> None:
    called: dict[str, str] = {}

    def _fake(url: str) -> str:
        called["url"] = url
        return "data:image/jpeg;base64,abc"

    monkeypatch.setattr(
        "plugins.mxai.content.video_frame.extract_last_frame_data_url",
        _fake,
    )
    out = resolve_reference_image(
        img_url="https://cdn.example.com/a.png",
        prev_video_url="https://cdn.example.com/prev.mp4",
    )
    assert out == "data:image/jpeg;base64,abc"
    assert called["url"] == "https://cdn.example.com/prev.mp4"


@pytest.mark.asyncio
async def test_submit_with_prev_video_switches_i2v(monkeypatch) -> None:
    monkeypatch.setenv("MXAI_MOCK", "1")
    sub = await submit_video_clip(
        prompt="续拍口播",
        model="demo-t2v",
        prev_video_url="https://cdn.example.com/prev.mp4",
    )
    assert sub["mock"] is True
    assert sub["model"] == "demo-i2v"
    assert sub["has_reference"] is True
    assert sub["img_url"]
    assert "首帧" in (sub.get("prompt") or "")
