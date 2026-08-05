"""Tests for generation_spec assembly from video_analysis_brief."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from plugins.openmontage.lib.generation_spec import (
    assemble_segment_prompt,
    compile_executable_prompt,
    find_segment_for_time,
    format_timed_action_range,
    get_generation_spec,
    prompt_for_time_range,
    segment_prompt_from_brief,
    _word_count,
)
from plugins.openmontage.lib.video_prompt_validator import validate_ugc_video_prompt
from plugins.openmontage.schemas.artifacts import validate_artifact

BRIEF_JSON = (
    Path(__file__).resolve().parents[2]
    / "projects"
    / "my-copy-01"
    / "artifacts"
    / "video_analysis_brief.json"
)


def test_format_timed_action_range():
    assert format_timed_action_range(0, 1.4) == "[00:00-00:01.4]"


def test_brief_schema_validates_my_copy_01():
    if not BRIEF_JSON.is_file():
        pytest.skip("project fixture not present")
    data = json.loads(BRIEF_JSON.read_text(encoding="utf-8"))
    validate_artifact("video_analysis_brief", data)
    scenes = data.get("structure_analysis", {}).get("scenes") or []
    assert scenes
    assert any((s.get("on_screen_text") or s.get("narration_text")) for s in scenes)
    assert data.get("generation")
    spec = data.get("generation_spec")
    assert spec and spec.get("segments"), "brief must include generation_spec assembled prompts"
    assert spec["segments"][0].get("assembled_prompt")


def test_build_persisted_generation_spec_my_copy_01():
    if not BRIEF_JSON.is_file():
        pytest.skip("project fixture not present")
    from plugins.openmontage.lib.generation_spec import attach_generation_spec_to_brief, build_persisted_generation_spec

    brief = json.loads(BRIEF_JSON.read_text(encoding="utf-8"))
    brief.pop("generation_spec", None)
    spec = build_persisted_generation_spec(brief)
    assert spec
    assert len(spec["segments"]) == 1
    prompt = spec["segments"][0]["assembled_prompt"]
    assert "Aspect ratio: 9:16" in prompt
    assert "[00:00-" in prompt
    enriched = attach_generation_spec_to_brief(brief)
    validate_artifact("video_analysis_brief", enriched)


def test_segment_prompt_from_brief_passes_ugc_validator():
    if not BRIEF_JSON.is_file():
        pytest.skip("project fixture not present")
    brief = json.loads(BRIEF_JSON.read_text(encoding="utf-8"))
    prompt = segment_prompt_from_brief(brief, 0)
    assert prompt
    errors = validate_ugc_video_prompt(prompt, aspect_ratio="9:16")
    assert not errors, errors


def test_compile_executable_prompt_word_limit():
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
        "replication_guidance": {
            "playbook_customizations": {
                "dna_lock": {
                    "subject": "Hands holding snack bag",
                    "scene": "Snack desk",
                }
            }
        },
        "structure_analysis": {
            "scenes": [{
                "start_time": 0,
                "end_time": 2,
                "beats": [{
                    "start_seconds": 0,
                    "end_seconds": 2,
                    "kind": "action",
                    "description": "Pour golden chips into palm.",
                }],
                "shot_language": {"shot_size": "close_up", "camera_movement": "handheld_static"},
            }],
        },
    }
    prompt = compile_executable_prompt(brief, 0, 2, establish_dna=True)
    assert _word_count(prompt) <= 120
    assert "[00:" not in prompt


def test_get_generation_spec():
    brief = {
        "generation_spec": {
            "prompt_profile": "default",
            "segmentation": {"chunk_seconds": 13, "rule": "single_segment"},
            "segments": [
                {
                    "segment_index": 0,
                    "start_seconds": 0,
                    "end_seconds": 5,
                    "timeline": [
                        {"start_seconds": 0, "end_seconds": 5, "description": "Hold."}
                    ],
                }
            ],
        }
    }
    spec = get_generation_spec(brief)
    assert spec is not None
    seg = find_segment_for_time(spec, 2.0)
    assert seg is not None


def test_prompt_for_time_range_my_copy_01():
    if not BRIEF_JSON.is_file():
        pytest.skip("project fixture not present")
    brief = json.loads(BRIEF_JSON.read_text(encoding="utf-8"))
    sc1 = prompt_for_time_range(brief, 0, 10, establish_dna=True)
    sc2 = prompt_for_time_range(brief, 10, 15, establish_dna=False)
    assert sc1 and sc2
    assert "[INHERIT DNA LOCK]" not in sc1
    assert sc2.startswith("[INHERIT DNA LOCK]")
    assert "[00:00-" in sc1
    for prompt in (sc1, sc2):
        errors = validate_ugc_video_prompt(prompt, aspect_ratio="9:16")
        assert not errors, errors


def test_cinematic_segment_assembles():
    segment = {
        "segment_index": 0,
        "start_seconds": 0,
        "end_seconds": 13,
        "timeline": [
            {"start_seconds": 0, "end_seconds": 5, "kind": "action", "description": "Walk to mark."}
        ],
        "delivery": {"aspect_ratio": "16:9", "capture_mode": "locked-off studio camera"},
        "environment": {"setting": "White cyclorama", "lighting": "soft key"},
        "consistency": {"physics_tokens": "real-time physics, constant speed"},
        "capture_character": {"polish_level": "studio_clean", "notes": "Clean grade."},
    }
    prompt = assemble_segment_prompt(segment, prompt_profile="cinematic")
    assert "16:9" in prompt
    assert "real-time physics" in prompt


# ------------------------------------------------------------------
# canonical_generation_prompt_from_scene (image/video prompt provenance)
# ------------------------------------------------------------------

def _scene_with(assets):
    return {"id": "sc1", "type": "generated", "description": "a scene",
            "start_seconds": 0, "end_seconds": 6, "required_assets": assets}


def test_canonical_generation_prompt_returns_image_description_verbatim():
    exact = "扁平矢量插画：一束白光穿过三棱镜分解成彩虹，深蓝夜空背景"
    scene = _scene_with([
        {"type": "image", "description": exact, "source": "generate", "prompt_profile": "default"},
    ])
    from plugins.openmontage.lib.generation_spec import canonical_generation_prompt_from_scene
    assert canonical_generation_prompt_from_scene(scene) == exact


def test_canonical_generation_prompt_video_behavior_matches_old_function():
    from plugins.openmontage.lib.generation_spec import (
        canonical_generation_prompt_from_scene,
        canonical_video_prompt_from_scene,
    )
    executable = "Aspect ratio: 9:16 vertical\nscene clutter: ..."
    scene = _scene_with([
        {"type": "video", "description": executable, "source": "generate",
         "prompt_profile": "ugc_native_executable"},
    ])
    assert canonical_video_prompt_from_scene(scene) == executable
    assert canonical_generation_prompt_from_scene(scene) == executable


def test_canonical_generation_prompt_skips_non_generate_source():
    from plugins.openmontage.lib.generation_spec import canonical_generation_prompt_from_scene
    scene = _scene_with([
        {"type": "image", "description": "stock image", "source": "source"},
    ])
    assert canonical_generation_prompt_from_scene(scene) is None


def test_canonical_generation_prompt_empty_description_returns_none():
    from plugins.openmontage.lib.generation_spec import canonical_generation_prompt_from_scene
    scene = _scene_with([
        {"type": "image", "description": "   ", "source": "generate"},
    ])
    assert canonical_generation_prompt_from_scene(scene) is None


def test_video_wrapper_ignores_image_assets():
    """canonical_video_prompt_from_scene must stay video-only — the
    reference_scene_plan sync depends on that semantic."""
    from plugins.openmontage.lib.generation_spec import canonical_video_prompt_from_scene
    scene = _scene_with([
        {"type": "image", "description": "a poster prompt", "source": "generate"},
    ])
    assert canonical_video_prompt_from_scene(scene) is None


def test_canonical_generation_prompt_skips_non_executable_video_description():
    from plugins.openmontage.lib.generation_spec import canonical_generation_prompt_from_scene
    scene = _scene_with([
        {"type": "video", "description": "A cinematic walkthrough of the office",
         "source": "generate"},
    ])
    assert canonical_generation_prompt_from_scene(scene) is None
