"""Tests for reference-driven scene_plan builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lib.generation_spec import (
    _word_count,
    compile_executable_prompt,
    prompt_for_time_range,
)
from lib.reference_scene_plan import build_reference_driven_scene_plan, sync_asset_manifest_prompts
from lib.video_prompt_validator import validate_executable_video_prompt
from schemas.artifacts import validate_artifact

PROJECT = Path(__file__).resolve().parents[2] / "projects" / "my-copy-01" / "artifacts"


@pytest.fixture
def fixtures():
    if not (PROJECT / "script.json").is_file():
        pytest.skip("my-copy-01 fixtures missing")
    script = json.loads((PROJECT / "script.json").read_text(encoding="utf-8"))
    brief = json.loads((PROJECT / "video_analysis_brief.json").read_text(encoding="utf-8"))
    return script, brief


def test_build_reference_driven_scene_plan_validates(fixtures):
    script, brief = fixtures
    plan = build_reference_driven_scene_plan(
        script,
        brief,
        production_inputs={"video_gen_clip_duration_seconds": 10},
        composition_strategy="ugc_native",
    )
    validate_artifact("scene_plan", plan)
    assert len(plan["scenes"]) == 2
    assert plan["metadata"]["pacing_style"] == "executable_gen_unit"
    assert plan["metadata"]["generation_unit_seconds"] == 10
    assert plan["metadata"]["edit_internal_beats"]
    for scene in plan["scenes"]:
        asset = next(a for a in scene["required_assets"] if a["type"] == "video")
        assert asset.get("duration") == "10"


def test_scene_plan_executable_prompts_are_compact(fixtures):
    script, brief = fixtures
    plan = build_reference_driven_scene_plan(
        script,
        brief,
        production_inputs={"video_gen_clip_duration_seconds": 10},
        composition_strategy="ugc_native",
    )
    for scene in plan["scenes"]:
        asset = next(a for a in scene["required_assets"] if a["type"] == "video")
        executable = asset["description"]
        assert "analysis_prompt" not in scene
        assert "analysis_prompt" not in asset
        assert len(executable) > 0
        assert _word_count(executable) <= 120
        assert "[00:" not in executable
        assert "Second-level timed actions" not in executable
        assert "诸葛卧龙" not in executable
        errors = validate_executable_video_prompt(executable, aspect_ratio="9:16")
        assert not errors, errors


def test_generation_prompt_from_brief_beats(fixtures):
    script, brief = fixtures
    plan = build_reference_driven_scene_plan(
        script,
        brief,
        production_inputs={"video_gen_clip_duration_seconds": 10},
        composition_strategy="ugc_native",
    )
    scene = plan["scenes"][0]
    start = float(scene["start_seconds"])
    end = float(scene["end_seconds"])
    expected = prompt_for_time_range(brief, start, end, establish_dna=(start == 0))
    assert expected
    assert "Second-level timed actions" in expected
    assert "analysis_prompt" not in scene


def test_compile_executable_prompt_montage_for_gen_unit():
    brief = {
        "generation": {
            "prompt_profile": "ugc_native",
            "delivery": {"aspect_ratio": "9:16", "orientation": "vertical"},
            "environment": {
                "setting": "Warm desk",
                "lighting": "Tungsten",
                "clutter_and_props": "woven mat, calendar",
                "ambient_floor": "grain",
            },
        },
        "structure_analysis": {
            "scenes": [{
                "start_time": 0,
                "end_time": 10,
                "beats": [
                    {
                        "start_seconds": 0,
                        "end_seconds": 2,
                        "kind": "action",
                        "description": "Pour chips into palm.",
                    },
                    {
                        "start_seconds": 2,
                        "end_seconds": 5,
                        "kind": "action",
                        "description": "Drop chips into basket.",
                    },
                    {
                        "start_seconds": 5,
                        "end_seconds": 8,
                        "kind": "action",
                        "description": "Show two flavor bags side by side.",
                    },
                ],
                "shot_language": {"shot_size": "close_up", "camera_movement": "handheld_static"},
            }],
        },
    }
    prompt = compile_executable_prompt(brief, 0, 10, establish_dna=True)
    assert "Montage:" in prompt
    assert _word_count(prompt) <= 120


def test_sync_asset_manifest_prompts(fixtures):
    script, brief = fixtures
    plan = build_reference_driven_scene_plan(script, brief, composition_strategy="ugc_native")
    manifest = {
        "version": "1.0",
        "assets": [
            {
                "id": "img_sc1",
                "type": "image",
                "source_tool": "frame_sampler",
                "scene_id": "sc1",
                "prompt": "10-second vertical 9:16 Douyin snack ad, warm tungsten desk",
            }
        ],
    }
    synced = sync_asset_manifest_prompts(manifest, plan)
    assert "Aspect ratio: 9:16" in synced["assets"][0]["prompt"]
    assert "Second-level timed actions" not in synced["assets"][0]["prompt"]


def test_build_reference_driven_scene_plan_static_composition(fixtures):
    script, brief = fixtures
    plan = build_reference_driven_scene_plan(
        script,
        brief,
        production_inputs={"video_gen_clip_duration_seconds": 10},
        composition_strategy="static_composition",
    )
    validate_artifact("scene_plan", plan)
    assert plan["metadata"]["assets_composition_strategy"] == "static_composition"
    assert plan["metadata"]["forbid_video_selector"] is True
    for scene in plan["scenes"]:
        asset = next(a for a in scene["required_assets"] if a["type"] == "image")
        assert asset.get("compose_strategy") == "ffmpeg_still_loop"
        assert asset.get("prompt_profile") == "still_frame"
        assert "still photograph" in asset["description"]
        assert "Motion:" not in asset["description"]
        assert "ugc_native" not in str(asset.get("prompt_profile", ""))
