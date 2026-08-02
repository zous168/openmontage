"""Tests for storyboard prompt assembly."""

from lib.shot_prompt_builder import (
    build_scene_storyboard_prompt,
    scene_plan_index_from_id,
)


def test_scene_plan_index_from_id():
    assert scene_plan_index_from_id("sc1") == 0
    assert scene_plan_index_from_id("SC8") == 7
    assert scene_plan_index_from_id("scene-3") == 2


def test_build_scene_storyboard_prompt_merges_reference():
    scene = {
        "id": "sc1",
        "description": "回购钩子",
        "shot_intent": "回购钩子",
        "overlay_notes": "上次买的花椒馍片我又回购了",
        "framing": "9:16竖屏CU/ECU，主体居中",
        "movement": "ken-burns-slow-zoom",
        "shot_language": {
            "shot_size": "close_up",
            "camera_movement": "handheld",
            "lighting_key": "tungsten_warm",
            "depth_of_field": "shallow",
            "color_temperature": "warm",
        },
        "required_assets": [{"type": "image", "description": "参考关键帧 sc1", "source": "provided"}],
    }
    reference_scene = {
        "scene_index": 0,
        "description": "Subject: yellow snack bag pouring chips | Camera: handheld CU",
    }
    reference_keyframe = {
        "scene_index": 0,
        "description": "Yellow bag pouring chips into palm",
    }
    prompt = build_scene_storyboard_prompt(
        scene,
        reference_scene=reference_scene,
        reference_keyframe=reference_keyframe,
    )
    assert "Intent: 回购钩子" in prompt
    assert "yellow snack bag" in prompt.lower()
    assert "Yellow bag pouring chips" in prompt
    assert "上次买的花椒馍片我又回购了" in prompt
    assert "9:16" in prompt
