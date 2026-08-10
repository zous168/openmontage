"""Tests for project media path resolution (no LLM path guessing)."""

from __future__ import annotations

from pathlib import Path

from plugins.openmontage.lib.project_media import (
    list_subtitle_candidates,
    resolve_project_media_path,
    rewrite_path_params,
)
from plugins.openmontage.tools.publishers.export_bundle import ExportBundle


def _make_video(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x00\x00\x00\x18ftypmp42fakevideo")


def test_resolve_projects_prefixed_path(tmp_path, monkeypatch):
    data = tmp_path / "montage"
    projects = data / "projects"
    video = projects / "demo" / "renders" / "final.mp4"
    _make_video(video)
    monkeypatch.setattr("plugins.openmontage.lib.paths.DATA_ROOT", data)
    monkeypatch.setattr("plugins.openmontage.lib.paths.PROJECTS_DIR", projects)

    resolved = resolve_project_media_path(
        "projects/demo/renders/final.mp4",
        project_id="demo",
    )
    assert resolved == video.resolve()


def test_resolve_project_relative_renders(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    video = projects / "demo" / "renders" / "final.mp4"
    _make_video(video)
    monkeypatch.setattr("plugins.openmontage.lib.paths.DATA_ROOT", tmp_path)
    monkeypatch.setattr("plugins.openmontage.lib.paths.PROJECTS_DIR", projects)

    resolved = resolve_project_media_path(
        "renders/final.mp4",
        project_id="demo",
    )
    assert resolved == video.resolve()


def test_resolve_subtitle_under_assets_audio(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    srt = projects / "demo" / "assets" / "audio" / "narration_full_srt.srt"
    srt.parent.mkdir(parents=True)
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    monkeypatch.setattr("plugins.openmontage.lib.paths.DATA_ROOT", tmp_path)
    monkeypatch.setattr("plugins.openmontage.lib.paths.PROJECTS_DIR", projects)

    resolved = resolve_project_media_path(
        "assets/audio/narration_full_srt.srt",
        project_id="demo",
    )
    assert resolved == srt.resolve()
    assert list_subtitle_candidates(projects / "demo") == [
        "assets/audio/narration_full_srt.srt"
    ]


def test_export_bundle_accepts_contract_video_path(tmp_path, monkeypatch):
    data = tmp_path / "montage"
    projects = data / "projects"
    video = projects / "demo" / "renders" / "final.mp4"
    _make_video(video)
    srt = projects / "demo" / "assets" / "audio" / "narration_full_srt.srt"
    srt.parent.mkdir(parents=True)
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    monkeypatch.setattr("plugins.openmontage.lib.paths.DATA_ROOT", data)
    monkeypatch.setattr("plugins.openmontage.lib.paths.PROJECTS_DIR", projects)

    result = ExportBundle().execute(
        {
            "project_id": "demo",
            "video_path": "projects/demo/renders/final.mp4",
            "title": "T",
            "export_dir": str(tmp_path / "out"),
            "subtitles_path": "assets/audio/narration_full_srt.srt",
        }
    )
    assert result.success is True, result.error
    assert (Path(result.data["export_path"]) / "video" / "subtitles.srt").is_file()


def test_export_bundle_missing_subs_lists_candidates(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    video = projects / "demo" / "renders" / "final.mp4"
    _make_video(video)
    srt = projects / "demo" / "assets" / "audio" / "narration_full_srt.srt"
    srt.parent.mkdir(parents=True)
    srt.write_text("1\n00:00:00,000 --> 00:00:01,000\nhi\n", encoding="utf-8")
    monkeypatch.setattr("plugins.openmontage.lib.paths.DATA_ROOT", tmp_path)
    monkeypatch.setattr("plugins.openmontage.lib.paths.PROJECTS_DIR", projects)

    result = ExportBundle().execute(
        {
            "project_id": "demo",
            "video_path": "renders/final.mp4",
            "title": "T",
            "export_dir": str(tmp_path / "out"),
            "subtitles_path": "renders/subtitles.srt",
        }
    )
    assert result.success is False
    assert "subtitles_path provided but not found" in (result.error or "")
    assert "assets/audio/narration_full_srt.srt" in (result.error or "")


def test_rewrite_path_params_absolutizes_existing(tmp_path, monkeypatch):
    projects = tmp_path / "projects"
    video = projects / "demo" / "renders" / "final.mp4"
    _make_video(video)
    monkeypatch.setattr("plugins.openmontage.lib.paths.DATA_ROOT", tmp_path)
    monkeypatch.setattr("plugins.openmontage.lib.paths.PROJECTS_DIR", projects)

    out = rewrite_path_params(
        {"video_path": "projects/demo/renders/final.mp4", "title": "x"},
        project_id="demo",
    )
    assert Path(out["video_path"]).is_file()
    assert out["title"] == "x"
