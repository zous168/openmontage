"""compose effect_subtitles 字幕轨合并（VC-T24）。"""

from __future__ import annotations

from plugins.mxai.content.compose_plan import merge_effect_subtitles


def test_merge_effect_subtitles_appends_track() -> None:
    plan = {"tracks": {"subtitle": [{"text": "主字幕", "start_sec": 0, "duration_sec": 2}]}}
    shots = [
        {
            "id": 1,
            "duration_sec": 5,
            "effect_subtitles": [
                {"text": "特效字", "time": {"start_sec": 1, "duration_sec": 2}, "style": {"type": "pop"}},
            ],
        },
    ]
    out = merge_effect_subtitles(plan, shots)
    subs = out["tracks"]["subtitle"]
    assert len(subs) == 2
    assert subs[-1]["text"] == "特效字"
    assert subs[-1]["source"] == "effect_subtitles"
