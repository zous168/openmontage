"""Remotion render must honor compose_target dimensions and normalize narration."""

from __future__ import annotations

import json
import sys
import wave
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from tools.video.video_compose import VideoCompose  # noqa: E402


def test_remotion_output_size_prefers_compose_target():
    data = {
        "metadata": {"compose_target": {"width": 1080, "height": 1920}},
    }
    w, h = VideoCompose._remotion_output_size(data, "generic_hd")
    assert (w, h) == (1080, 1920)


def test_remotion_output_size_falls_back_to_profile():
    w, h = VideoCompose._remotion_output_size({}, "tiktok")
    assert (w, h) == (1080, 1920)


def test_prepare_remotion_props_resolves_audio_and_cuts(tmp_path):
    project = tmp_path / "demo"
    (project / "assets" / "audio").mkdir(parents=True)
    (project / "assets" / "images").mkdir(parents=True)
    (project / "project.json").write_text("{}", encoding="utf-8")

    narr = project / "assets" / "audio" / "narration.wav"
    img = project / "assets" / "images" / "sc1.jpg"
    img.write_bytes(b"\xff\xd8\xff\xd9")
    with wave.open(str(narr), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * 22050)

    out = project / "renders" / "out.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)

    props = {
        "cuts": [{"source": "assets/images/sc1.jpg"}],
        "audio": {"narration": {"src": "assets/audio/narration.wav", "volume": 1}},
    }
    tool = VideoCompose()
    tool._prepare_remotion_props(props, out)

    assert props["cuts"][0]["source"] == "assets/images/sc1.jpg"
    assert props["audio"]["narration"]["src"].endswith(".wav")
    assert "assets/" in props["audio"]["narration"]["src"]


def test_remotion_render_passes_compose_target_dimensions(tool, tmp_path, monkeypatch):
    seen = {}

    def fake_run_command(cmd, *a, **k):
        seen["cmd"] = cmd
        return None

    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/npx")
    monkeypatch.setattr(tool, "run_command", fake_run_command)

    out = tmp_path / "renders" / "out.mp4"
    out.parent.mkdir(parents=True)
    tool._remotion_render(
        {
            "composition_data": {
                "cuts": [],
                "metadata": {"compose_target": {"width": 1080, "height": 1920}},
            },
            "output_path": str(out),
        }
    )
    assert "--width" in seen["cmd"]
    assert "1080" in seen["cmd"]
    assert "1920" in seen["cmd"]


@pytest.fixture
def tool():
    return VideoCompose()
