"""Contract tests: generated image/video assets MUST record their prompt.

Every `image` / `video` asset in an asset_manifest is driven by a text
prompt (generation prompt, or search term for stock). The schema enforces
that `prompt` is present for these types — unless the asset was produced
by a derivation tool (`video_trimmer`, `frame_sampler`, `ffmpeg`,
`character_rig_renderer`) that transforms existing media rather than
generating from a prompt.

These tests pin the enforcement and the derivation exclusion list so the
rule cannot drift silently.

Run: pytest tests/contracts/test_asset_prompt_contract.py -v
"""

import json
from pathlib import Path

import pytest

from plugins.openmontage.schemas.artifacts import validate_artifact

SCHEMA_PATH = Path(__file__).resolve().parent.parent.parent / "schemas" / "artifacts" / "asset_manifest.schema.json"

DERIVATION_TOOLS = ["ffmpeg", "video_trimmer", "frame_sampler", "character_rig_renderer"]


def _asset(**overrides):
    asset = {
        "id": "a1",
        "type": "image",
        "path": "assets/images/a1.png",
        "source_tool": "image_selector",
        "scene_id": "scene-1",
        "prompt": "a test prompt",
    }
    asset.update(overrides)
    if asset.get("prompt") is None:
        # prompt=None means "omit the key" (a null value fails type: string)
        asset.pop("prompt", None)
    return asset


def _manifest(assets):
    return {"version": "1.0", "assets": assets}


class TestPromptRequiredForImageVideo:

    @pytest.mark.parametrize("tool", ["image_selector", "dashscope_image", "zhipu_image", "flux_image", "pexels_image"])
    def test_image_without_prompt_rejected(self, tool):
        with pytest.raises(Exception):
            validate_artifact("asset_manifest", _manifest([_asset(source_tool=tool, prompt=None)]))

    @pytest.mark.parametrize("tool", ["video_selector", "kling_video", "seedance_video", "pixabay_video", "pexels_video"])
    def test_video_without_prompt_rejected(self, tool):
        with pytest.raises(Exception):
            validate_artifact("asset_manifest", _manifest([_asset(type="video", path="assets/video/a1.mp4", source_tool=tool, prompt=None)]))

    def test_image_with_prompt_validates(self):
        validate_artifact("asset_manifest", _manifest([_asset()]))

    def test_video_with_prompt_validates(self):
        validate_artifact("asset_manifest", _manifest([_asset(type="video", path="assets/video/a1.mp4", prompt="a video prompt")]))

    def test_stock_search_term_counts_as_prompt(self):
        # Stock: the search term IS the prompt.
        validate_artifact("asset_manifest", _manifest([_asset(source_tool="pixabay_image", prompt="sunset sky")]))

    def test_empty_prompt_rejected(self):
        with pytest.raises(Exception):
            validate_artifact("asset_manifest", _manifest([_asset(prompt="")]))


class TestDerivationToolsExempt:

    @pytest.mark.parametrize("tool", DERIVATION_TOOLS)
    def test_derivation_tools_exempt(self, tool):
        """Media transformed from existing sources needs no prompt."""
        validate_artifact("asset_manifest", _manifest([_asset(type="video", path="assets/video/a1.mp4", source_tool=tool, prompt=None)]))
        validate_artifact("asset_manifest", _manifest([_asset(source_tool=tool, prompt=None)]))


class TestNonVisualNotForced:

    @pytest.mark.parametrize("atype", ["audio", "narration", "music", "sfx", "subtitle"])
    def test_audio_subtitle_not_forced(self, atype):
        validate_artifact("asset_manifest", _manifest([_asset(type=atype, path=f"assets/{atype}/a1.bin", prompt=None)]))

    @pytest.mark.parametrize("atype", ["animation", "diagram", "code_snippet", "font", "lut"])
    def test_other_visual_types_not_forced(self, atype):
        validate_artifact("asset_manifest", _manifest([_asset(type=atype, path=f"assets/{atype}/a1", prompt=None)]))


class TestDerivationExclusionListPinned:

    def test_exclusion_list_matches_pinned_set(self):
        """Guard against silently growing the derivation blacklist."""
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        item = schema["properties"]["assets"]["items"]
        conds = item.get("allOf", [])
        assert conds, "conditional prompt requirement missing from schema"
        source_tool_cond = conds[0]["if"]["properties"]["source_tool"]
        excluded = source_tool_cond["not"]["enum"]
        assert sorted(excluded) == sorted(DERIVATION_TOOLS)

    def test_prompt_has_min_length(self):
        schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        item = schema["properties"]["assets"]["items"]
        assert item["properties"]["prompt"].get("minLength") == 1
