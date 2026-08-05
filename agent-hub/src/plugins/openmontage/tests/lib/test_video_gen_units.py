from plugins.openmontage.lib.video_gen_units import (
    DEFAULT_VIDEO_GEN_CLIP_SECONDS,
    resolve_video_gen_clip_duration,
    scene_count_for_duration,
    video_gen_unit_ranges,
)


def test_resolve_default():
    assert resolve_video_gen_clip_duration({}) == DEFAULT_VIDEO_GEN_CLIP_SECONDS
    assert resolve_video_gen_clip_duration(None) == DEFAULT_VIDEO_GEN_CLIP_SECONDS


def test_resolve_from_production_inputs():
    assert resolve_video_gen_clip_duration({"video_gen_clip_duration_seconds": 15}) == 15.0
    assert resolve_video_gen_clip_duration({"video_gen_clip_duration_seconds": 99}) == 30.0
    assert resolve_video_gen_clip_duration({"video_gen_clip_duration_seconds": 2}) == 5.0


def test_unit_ranges():
    assert video_gen_unit_ranges(15, 15) == [(0.0, 15.0)]
    assert video_gen_unit_ranges(30, 15) == [(0.0, 15.0), (15.0, 30.0)]
    assert video_gen_unit_ranges(22, 15) == [(0.0, 15.0), (15.0, 22.0)]


def test_scene_count():
    assert scene_count_for_duration(15, 15) == 1
    assert scene_count_for_duration(30, 15) == 2
    assert scene_count_for_duration(31, 15) == 3
