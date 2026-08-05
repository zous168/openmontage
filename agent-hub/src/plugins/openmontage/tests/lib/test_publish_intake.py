"""Tests for lib.publish_intake."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from plugins.openmontage.lib.publish_intake import (
    COVER_KEYS,
    DEFAULT_FRAME_CAPTURE_SECONDS,
    build_thumbnail_concept,
    build_thumbnail_prompt,
    default_frame_capture_seconds,
    generate_cover_thumbnail,
    normalize_cover_field,
    resolve_cover_brief,
)
from plugins.openmontage.tools.base_tool import ToolResult, ToolStatus


class TestResolveCoverBrief:
    def test_defaults(self):
        brief = resolve_cover_brief({"target_platform": "douyin"})
        assert brief["source"] == "auto_frame"
        assert brief["text_hook"] == ""
        assert "capture_seconds" not in brief

    def test_explicit_values(self):
        brief = resolve_cover_brief({
            "thumbnail_text_hook": "又回购了",
            "thumbnail_style_notes": "产品特写+字幕",
            "thumbnail_source": "concept_only",
        })
        assert brief["text_hook"] == "又回购了"
        assert brief["style_notes"] == "产品特写+字幕"
        assert brief["source"] == "concept_only"

    def test_text_to_image_source(self):
        brief = resolve_cover_brief({"thumbnail_source": "text_to_image"})
        assert brief["source"] == "text_to_image"


class TestNormalizeCoverField:
    def test_hook_length_limit(self):
        with pytest.raises(ValueError, match="封面文案"):
            normalize_cover_field("thumbnail_text_hook", "x" * 121)

    def test_invalid_source(self):
        with pytest.raises(ValueError, match="无效封面来源"):
            normalize_cover_field("thumbnail_source", "magic")


class TestBuildThumbnailConcept:
    def test_from_intake(self):
        concept = build_thumbnail_concept(
            resolve_cover_brief({
                "thumbnail_text_hook": "又回购了",
                "thumbnail_style_notes": "竖屏产品特写",
            }),
            title="Demo",
            style_playbook="clean-professional",
        )
        assert concept["text_overlay"] == "又回购了"
        assert "竖屏产品特写" in concept["concept"]
        assert concept["source"] == "auto_frame"
        assert "又回购了" in concept["prompt"]
        assert "capture_seconds" not in concept

    def test_auto_prompt_from_intake(self):
        prompt = build_thumbnail_prompt(
            resolve_cover_brief({
                "thumbnail_text_hook": "又回购了",
                "thumbnail_style_notes": "竖屏产品特写",
            }),
            title="Demo",
            style_playbook="clean-professional",
            deliverable={"aspect_ratio": "9:16"},
        )
        assert "又回购了" in prompt
        assert "竖屏产品特写" in prompt


class TestDefaultFrameCapture:
    def test_constant(self):
        assert default_frame_capture_seconds() == DEFAULT_FRAME_CAPTURE_SECONDS


class TestGenerateCoverThumbnail:
    @patch("plugins.openmontage.tools.graphics.image_selector.ImageSelector")
    def test_success(self, mock_cls, tmp_path):
        out = tmp_path / "thumb.png"
        out.write_bytes(b"png")
        mock_selector = MagicMock()
        mock_selector.get_status.return_value = ToolStatus.AVAILABLE
        mock_selector.execute.return_value = ToolResult(
            success=True,
            artifacts=[str(out)],
            data={"selected_provider": "bfl", "selected_tool": "flux_api"},
        )
        mock_cls.return_value = mock_selector

        path, meta, err = generate_cover_thumbnail(
            "test prompt",
            tmp_path / "dest.png",
            width=1080,
            height=1920,
            aspect_ratio="9:16",
        )
        assert err is None
        assert path == out
        assert meta["provider"] == "bfl"


class TestCoverKeys:
    def test_keys(self):
        assert COVER_KEYS == frozenset({
            "thumbnail_text_hook",
            "thumbnail_style_notes",
            "thumbnail_source",
        })
