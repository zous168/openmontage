"""find_ffmpeg：env 最高；imageio 随包优先于 PATH。"""

from __future__ import annotations

import sys


def test_find_ffmpeg_prefers_imageio_over_path(monkeypatch, tmp_path) -> None:
    path_ff = tmp_path / "path-ffmpeg.exe"
    path_ff.write_bytes(b"x")
    imageio_ff = tmp_path / "imageio-ffmpeg.exe"
    imageio_ff.write_bytes(b"x")

    monkeypatch.delenv("MXAI_FFMPEG_EXE", raising=False)
    monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: str(path_ff) if name == "ffmpeg" else None)

    class _Fake:
        @staticmethod
        def get_ffmpeg_exe():
            return str(imageio_ff)

    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", _Fake())

    import plugins.mxai.content.ffmpeg_bin as mod

    mod.find_ffmpeg.cache_clear()
    assert mod.find_ffmpeg() == str(imageio_ff)


def test_find_ffmpeg_falls_back_to_path(monkeypatch, tmp_path) -> None:
    path_ff = tmp_path / "path-ffmpeg.exe"
    path_ff.write_bytes(b"x")
    monkeypatch.delenv("MXAI_FFMPEG_EXE", raising=False)
    monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: str(path_ff) if name == "ffmpeg" else None)

    class _Broken:
        @staticmethod
        def get_ffmpeg_exe():
            raise RuntimeError("imageio unavailable")

    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", _Broken())

    import plugins.mxai.content.ffmpeg_bin as mod

    mod.find_ffmpeg.cache_clear()
    assert mod.find_ffmpeg() == str(path_ff)


def test_find_ffmpeg_falls_back_to_imageio(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"x")
    monkeypatch.delenv("MXAI_FFMPEG_EXE", raising=False)
    monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)

    class _Fake:
        @staticmethod
        def get_ffmpeg_exe():
            return str(fake)

    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", _Fake())

    import plugins.mxai.content.ffmpeg_bin as mod

    mod.find_ffmpeg.cache_clear()
    assert mod.find_ffmpeg() == str(fake)


def test_resolve_ffmpeg_bins_derives_ffprobe(monkeypatch, tmp_path) -> None:
    ff = tmp_path / "ffmpeg.exe"
    probe = tmp_path / "ffprobe.exe"
    ff.write_bytes(b"x")
    probe.write_bytes(b"x")
    monkeypatch.delenv("MXAI_FFMPEG_EXE", raising=False)
    monkeypatch.delenv("IMAGEIO_FFMPEG_EXE", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)

    import plugins.mxai.content.ffmpeg_bin as mod

    mod.find_ffmpeg.cache_clear()
    mod.find_ffprobe.cache_clear()
    resolved_ff, resolved_fp = mod.resolve_ffmpeg_bins(str(ff))
    assert resolved_ff == str(ff)
    assert resolved_fp == str(probe)


def test_find_ffmpeg_env_override(monkeypatch, tmp_path) -> None:
    fake = tmp_path / "custom-ffmpeg"
    fake.write_text("x", encoding="utf-8")
    monkeypatch.setenv("MXAI_FFMPEG_EXE", str(fake))
    monkeypatch.setattr("shutil.which", lambda name: str(tmp_path / "other.exe"))

    import plugins.mxai.content.ffmpeg_bin as mod

    mod.find_ffmpeg.cache_clear()
    assert mod.find_ffmpeg() == str(fake)
