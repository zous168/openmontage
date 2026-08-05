"""Tests for UGC video prompt validation."""

from plugins.openmontage.lib.video_prompt_validator import validate_ugc_video_prompt

_GOOD_PROMPT = (
    "9:16 vertical smartphone handheld UGC. Messy kitchen counter clutter, warm tungsten "
    "key from window left, visible sensor grain and room noise floor. "
    "[00:00-00:03] subject shifts weight left over 3 seconds, fingers adjust on mug. "
    "[00:03-00:06] slight blink, chest breath rise. "
    "real-time physics, constant speed, no time-lapse, no dead frames. "
    "Handheld micro-shake, focus breathing, uneven exposure, natural skin texture."
)


def test_validate_ugc_video_prompt_passes_complete_prompt():
    assert validate_ugc_video_prompt(_GOOD_PROMPT, aspect_ratio="9:16") == []


def test_validate_ugc_video_prompt_rejects_shorthand():
    bad = _GOOD_PROMPT + " same as above for lighting."
    errors = validate_ugc_video_prompt(bad, aspect_ratio="9:16")
    assert any("Forbidden shorthand" in e for e in errors)


def test_validate_ugc_video_prompt_rejects_missing_control_tokens():
    bad = _GOOD_PROMPT.replace("real-time physics, constant speed,", "")
    errors = validate_ugc_video_prompt(bad, aspect_ratio="9:16")
    assert any("real-time physics" in e or "constant speed" in e for e in errors)


def test_validate_ugc_video_prompt_rejects_forbidden_aesthetic():
    bad = _GOOD_PROMPT + " gimbal smooth cinematic studio lighting."
    errors = validate_ugc_video_prompt(bad, aspect_ratio="9:16")
    assert any("forbidden aesthetic" in e for e in errors)
