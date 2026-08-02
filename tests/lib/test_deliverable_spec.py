"""Tests for lib.deliverable_spec."""

import json

import pytest

from lib.deliverable_spec import (
    DELIVERABLE_KEYS,
    normalize_deliverable_field,
    resolve_deliverable,
)


class TestResolveDeliverable:
    def test_douyin_defaults_when_fields_empty(self):
        spec = resolve_deliverable({"target_platform": "douyin"})
        assert spec["aspect_ratio"] == "9:16"
        assert spec["quality_tier"] == "1080p"
        assert spec["fps"] == 30
        assert spec["resolution"] == "1080x1920"
        assert spec["width"] == 1080
        assert spec["height"] == 1920
        assert spec["media_profile"] == "tiktok"

    def test_youtube_defaults_landscape(self):
        spec = resolve_deliverable({"target_platform": "youtube"})
        assert spec["aspect_ratio"] == "16:9"
        assert spec["resolution"] == "1920x1080"

    def test_explicit_overrides(self):
        spec = resolve_deliverable({
            "target_platform": "douyin",
            "aspect_ratio": "16:9",
            "quality_tier": "720p",
            "fps": "24",
        })
        assert spec["aspect_ratio"] == "16:9"
        assert spec["quality_tier"] == "720p"
        assert spec["fps"] == 24
        assert spec["resolution"] == "1280x720"

    def test_square_profile(self):
        spec = resolve_deliverable({
            "target_platform": "instagram",
            "aspect_ratio": "1:1",
            "quality_tier": "1080p",
        })
        assert spec["resolution"] == "1080x1080"
        assert spec["media_profile"] == "instagram_feed"

    def test_configured_tracks_raw_inputs(self):
        spec = resolve_deliverable({
            "target_platform": "douyin",
            "aspect_ratio": "9:16",
        })
        assert spec["configured"]["aspect_ratio"] == "9:16"
        assert spec["configured"]["quality_tier"] is None


class TestNormalizeDeliverableField:
    def test_valid_aspect(self):
        assert normalize_deliverable_field("aspect_ratio", "9:16") == "9:16"

    def test_invalid_aspect_raises(self):
        with pytest.raises(ValueError, match="画幅"):
            normalize_deliverable_field("aspect_ratio", "4:3")

    def test_fps_coercion(self):
        assert normalize_deliverable_field("fps", "30") == 30
        assert normalize_deliverable_field("fps", 24) == 24

    def test_empty_raises_empty(self):
        with pytest.raises(ValueError, match="empty"):
            normalize_deliverable_field("fps", "")


class TestEnrichProjectDeliverable:
    def test_enrich_render_inputs_from_project_meta(self, tmp_path, monkeypatch):
        from lib import events

        projects = tmp_path / "projects"
        proj = projects / "demo"
        (proj / "renders").mkdir(parents=True)
        (proj / "meta.json").write_text(
            json.dumps({
                "version": "1.0",
                "production_inputs": {
                    "target_platform": "douyin",
                    "quality_tier": "720p",
                },
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(events, "PROJECTS_DIR", projects)

        from lib.deliverable_spec import enrich_render_inputs

        inputs = enrich_render_inputs({
            "output_path": str(proj / "renders" / "out.mp4"),
            "edit_decisions": {"cuts": [{"source": "x"}]},
        })
        assert inputs["profile"] == "tiktok"
        assert inputs["fps"] == 30
        ct = inputs["edit_decisions"]["metadata"]["compose_target"]
        assert ct["width"] == 720
        assert ct["height"] == 1280
        assert ct["fit"] == "cover"

    def test_enrich_generation_inputs_sets_aspect_ratio(self, tmp_path, monkeypatch):
        from lib import paths

        projects = tmp_path / "projects"
        proj = projects / "demo"
        proj.mkdir(parents=True)
        (proj / "meta.json").write_text(
            json.dumps({
                "production_inputs": {"target_platform": "youtube"},
            }),
            encoding="utf-8",
        )
        monkeypatch.setattr(paths, "PROJECTS_DIR", projects)

        from lib.deliverable_spec import enrich_generation_inputs

        inputs = enrich_generation_inputs({"project_dir": str(proj), "prompt": "test"})
        assert inputs["aspect_ratio"] == "16:9"
        assert inputs["width"] == 1920
        assert inputs["height"] == 1080


class TestDeliverableKeys:
    def test_keys_match_bootstrap_fields(self):
        assert DELIVERABLE_KEYS == frozenset({"aspect_ratio", "quality_tier", "fps"})
