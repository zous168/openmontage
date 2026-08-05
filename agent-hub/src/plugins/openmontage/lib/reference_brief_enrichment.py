"""Agent vision enrichment for video_analysis_brief after video_analyzer skeleton."""

from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plugins.openmontage.lib.generation_spec import attach_generation_spec_to_brief
from plugins.openmontage.lib.paths import PROJECTS_DIR
from plugins.openmontage.schemas.artifacts import validate_artifact

CONTROL_TOKENS = (
    "Smartphone handheld, real-time physics, constant speed, no time-lapse, "
    "no dead frames, native HDR, maintain exact product and scene consistency"
)


def _scene(
    *,
    scene_index: int,
    start: float,
    end: float,
    description: str,
    narration_text: str = "",
    on_screen_text: str = "",
    beats: list[dict[str, Any]] | None = None,
    visual_type: str = "product_shot",
    energy_level: str = "medium",
    motion_type: str = "animated_still",
    flow_variance: float = 0.08,
    shot_language: dict[str, str] | None = None,
    dominant_colors: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "scene_index": scene_index,
        "start_time": start,
        "end_time": end,
        "description": description,
        "visual_type": visual_type,
        "energy_level": energy_level,
        "motion_type": motion_type,
        "flow_variance": flow_variance,
        "narration_text": narration_text,
        "on_screen_text": on_screen_text,
        "beats": beats or [],
        "shot_language": shot_language or {
            "shot_size": "close_up",
            "camera_movement": "handheld_static",
            "lighting_key": "warm_tungsten",
            "depth_of_field": "shallow",
        },
        "dominant_colors": dominant_colors or ["#FFD700", "#8B4513", "#FF4500"],
    }


def enrich_snack_desk_reference(skeleton: dict[str, Any]) -> dict[str, Any]:
    """Enrich a video_analyzer skeleton for the my-copy-01 Douyin snack reference."""
    brief = deepcopy(skeleton)
    source = brief.setdefault("source", {})
    source["type"] = "tiktok"
    source["url"] = source.get("url") or "https://v.douyin.com/tyV7nsNEpOw/"
    source["local_path"] = source.get("local_path") or "projects/my-copy-01/reference/reference_video.mp4"
    source["title"] = (
        source.get("title")
        or "又回购了这个花椒馍片！打开就闻到浓浓的花椒味，口感酥脆，好吃到停不下来"
    )
    source["duration_seconds"] = float(source.get("duration_seconds") or 10.966667)
    source["resolution"] = source.get("resolution") or "720x1280"
    source["platform_note"] = "douyin mapped to tiktok for schema"
    source.setdefault("platform_metadata", {}).update({
        "description": "零食推荐 #追剧小零食 #花椒馍片",
    })

    brief["content_analysis"] = {
        "summary": (
            "11秒竖屏抖音零食种草：回购社会证明开场，快切展示倒袋、双口味、花椒粒ECU、"
            "酥脆特写与满盘收尾；无真人出镜，burn-in字幕驱动。"
        ),
        "topics": ["零食种草", "花椒馍片", "回购推荐", "双口味", "酥脆质感"],
        "key_claims": [
            "上次购买后又回购",
            "有椒香和麻辣两种口味",
            "表面撒满花椒粒",
            "口感特别酥脆",
            "越嚼越香",
        ],
        "target_audience": "追剧/办公零食消费者，18-35岁",
        "tone": "casual",
        "hook_technique": "回购前置社会证明",
        "call_to_action": "implicit purchase via appetite close",
    }

    brief["structure_analysis"]["scenes"] = [
        _scene(
            scene_index=0,
            start=0.0,
            end=1.367,
            description=(
                "[00:00-00:01.4] CU handheld top-down. Subject: left hand red manicure tilts "
                "yellow pepper-flatbread snack bag (~28% frame width, matte plastic, golden chips visible through "
                "opening); chips pour into cupped right palm (~12% frame width). Scene: woven straw "
                "mat, warm tungsten key upper-left. Framing: product + hands only, no face."
            ),
            narration_text="上次购买的花椒馍片我又回购了",
            on_screen_text="上次购买的花椒馍片我又回购了",
            beats=[
                {
                    "start_seconds": 0.0,
                    "end_seconds": 0.6,
                    "kind": "object_interaction",
                    "description": (
                        "Yellow snack bag (~28% frame width, matte plastic) tilts 35° over palm; "
                        "real-time pour begins, duration 0.6s, constant velocity."
                    ),
                },
                {
                    "start_seconds": 0.6,
                    "end_seconds": 1.4,
                    "kind": "micro_motion",
                    "description": (
                        "Chips (~3.5cm squares, ~6% frame width each) land in cupped palm; thumb "
                        "stabilizes bag lip; subtle finger micro-adjustment; bag crinkle SFX implied."
                    ),
                },
            ],
            energy_level="high",
            flow_variance=0.12,
        ),
        _scene(
            scene_index=1,
            start=1.367,
            end=3.6,
            description=(
                "Top-down MS on round bamboo basket (~45% frame width) filling with golden chips; "
                "red calendar block '08 SEPTEMBER' prop upper-left; festive desk with red lucky bags."
            ),
            narration_text="有椒香和麻辣两种口味",
            beats=[
                {
                    "start_seconds": 1.4,
                    "end_seconds": 1.5,
                    "kind": "cut",
                    "description": "[Cut @ 00:01.4] Hard cut from pour to basket top-down.",
                },
                {
                    "start_seconds": 1.5,
                    "end_seconds": 3.6,
                    "kind": "action",
                    "description": (
                        "Hands blur at frame edges dropping chips into basket; chips cascade with "
                        "real-time physics; subtle handheld micro-shake; quiet chip rustle room tone."
                    ),
                },
            ],
            shot_language={
                "shot_size": "medium",
                "camera_movement": "handheld_static",
                "lighting_key": "warm_tungsten",
                "depth_of_field": "medium",
            },
        ),
        _scene(
            scene_index=2,
            start=3.6,
            end=4.833,
            description=(
                "Dual packaging hero: green 椒香 bag left, yellow 麻辣 bag right; red manicured "
                "fingers grip left edge; shallow DOF locks product labels."
            ),
            on_screen_text="椒香和麻辣两种口味",
            beats=[
                {
                    "start_seconds": 3.6,
                    "end_seconds": 4.8,
                    "kind": "action",
                    "description": (
                        "Two 128g bags side-by-side (~35% frame width each); locked framing; "
                        "micro handheld breathing; packaging matte finish with specular highlights."
                    ),
                },
            ],
            motion_type="static_image",
            flow_variance=0.02,
        ),
        _scene(
            scene_index=3,
            start=4.833,
            end=6.6,
            description=(
                "ECU chip surface between fingers; peppercorn specks and green herb flakes visible; "
                "shallow DOF, focus hunt subtle."
            ),
            narration_text="上面撒满了花椒粒",
            on_screen_text="上面撒满了花椒粒",
            beats=[
                {
                    "start_seconds": 4.8,
                    "end_seconds": 6.6,
                    "kind": "action",
                    "description": (
                        "Two chips (~4cm, ~22% frame width combined) pinched between thumb and index; "
                        "seasoning texture tack-sharp; fingers red gloss manicure; shadow cast lower-left 45°."
                    ),
                },
            ],
            energy_level="high",
        ),
        _scene(
            scene_index=4,
            start=6.6,
            end=7.633,
            description=(
                "Hands squeeze two chips showing layered crisp interior; peak appetite beat."
            ),
            narration_text="口感特别的酥脆",
            on_screen_text="口感特别的酥脆",
            beats=[
                {
                    "start_seconds": 6.6,
                    "end_seconds": 7.6,
                    "kind": "object_interaction",
                    "description": (
                        "Fingers apply gentle squeeze over 1.0s; audible crisp fracture implied; "
                        "real-time physics, no time compression."
                    ),
                },
                {
                    "start_seconds": 7.6,
                    "end_seconds": 8.2,
                    "kind": "micro_motion",
                    "description": (
                        "Hold chips in frame; subtle wrist tremor; light flicker on golden crust."
                    ),
                },
            ],
            energy_level="peak",
            flow_variance=0.06,
        ),
        _scene(
            scene_index=5,
            start=7.633,
            end=8.167,
            description="Quick ECU transition beat — chip edge texture flash before chew implication.",
            visual_type="transition",
            beats=[
                {
                    "start_seconds": 7.63,
                    "end_seconds": 7.75,
                    "kind": "cut",
                    "description": "[Cut @ 00:07.6] Hard cut to tighter chip edge ECU.",
                },
                {
                    "start_seconds": 7.75,
                    "end_seconds": 8.17,
                    "kind": "camera",
                    "description": (
                        "Motion blur whip on chip surface; handheld bump; duration 0.42s real-time."
                    ),
                },
            ],
            energy_level="high",
            flow_variance=0.15,
        ),
        _scene(
            scene_index=6,
            start=8.167,
            end=9.467,
            description="Implied chew — pour repeat micro-beat with handheld shake.",
            narration_text="越嚼越香",
            on_screen_text="越嚼越香",
            beats=[
                {
                    "start_seconds": 8.2,
                    "end_seconds": 9.5,
                    "kind": "cut",
                    "description": (
                        "Quick ECU bag-to-palm pour repeat; motion blur on falling chips; "
                        "handheld micro-shake; chip rustle SFX."
                    ),
                },
            ],
            flow_variance=0.1,
        ),
        _scene(
            scene_index=7,
            start=9.467,
            end=10.967,
            description=(
                "Full bamboo basket hero (~50% frame); slow ken-burns push; tiger figurine, "
                "calendar 08, money tree props in soft bokeh."
            ),
            narration_text="真的太好吃了",
            on_screen_text="真的太好吃了",
            beats=[
                {
                    "start_seconds": 9.5,
                    "end_seconds": 11.0,
                    "kind": "camera",
                    "description": (
                        "Slow dolly-in top-down over 1.5s; basket rim stays centered; "
                        "appetizing warm grade; no dead frames — subtle prop shadow drift."
                    ),
                },
            ],
            shot_language={
                "shot_size": "medium",
                "camera_movement": "dolly_in",
                "lighting_key": "warm_tungsten",
                "depth_of_field": "medium",
            },
            energy_level="high",
            flow_variance=0.04,
        ),
    ]

    keyframes = brief.get("keyframes") or []
    kf_desc = [
        "Yellow bag pouring chips, 回购 hook burn-in",
        "Basket full of chips, red calendar 08",
        "Dual flavor packaging green/yellow",
        "Pepper speck ECU between fingers",
        "Hands holding two crispy chips, squeeze",
        "Crispy texture ECU edge flash",
        "Quick cut chip pour chew beat",
        "Full basket hero, 真的太好吃了 burn-in",
    ]
    for i, kf in enumerate(keyframes):
        if isinstance(kf, dict) and i < len(kf_desc):
            kf["description"] = kf_desc[i]

    brief["style_profile"] = {
        "color_palette": {
            "primary_colors": ["#FFD700", "#FF4500", "#228B22"],
            "accent_colors": ["#DC143C", "#8B4513"],
            "overall_mood": "warm appetizing festive snack desk",
        },
        "typography_observed": "White bold Chinese sans-serif, black outline, bottom-center burn-in",
        "transition_types": ["hard_cut"],
        "music_style": "light upbeat snack promo bed ~45dB under room tone",
        "narration_style": {
            "has_narration": False,
            "speaker_count": 0,
            "delivery_style": "text-only burn-in in reference; no spoken VO",
            "words_per_minute": 0,
        },
        "subtitle_style": "burn-in bottom-center, no karaoke — exclude from generation prompts",
        "production_quality": "prosumer",
        "closest_playbook": "flat-motion-graphics",
        "playbook_delta": "Upgrade to clean-professional typography; keep rapid_fire rhythm",
        "audio_energy_profile": (brief.get("style_profile") or {}).get("audio_energy_profile"),
    }

    brief["replication_guidance"] = {
        "suggested_pipeline": "reference-driven",
        "suggested_playbook": "clean-professional",
        "key_elements_to_replicate": [
            "回购钩子第一镜",
            "8镜 rapid_fire 快切",
            "双口味包装并列",
            "花椒粒/酥脆 ECU",
            "满盘 hero 收尾",
        ],
        "elements_requiring_custom_work": [
            "产品实拍或授权素材",
            "Piper TTS 口播（用户版）",
            "字幕层级升级",
        ],
        "estimated_complexity": "simple",
        "motion_required": True,
        "creative_differentiation_seeds": [
            "口播+字幕 vs 参考纯 burn-in",
            "clean-professional 字体",
            "CTA 评论区互动",
        ],
        "playbook_customizations": {
            "dna_lock": {
                "subject": (
                    "Hands red manicure only; yellow/green pepper-flatbread snack bags (128g matte plastic); "
                    "golden chips ~3.5cm with pepper specks"
                ),
                "scene": (
                    "Warm snack desk: woven straw mat, red calendar 08 SEPTEMBER, duck/tiger figurines, "
                    "money tree, green plant, YEAR BOOK prop"
                ),
                "lighting": "Warm tungsten key upper-left, soft fill, appetizing grade LUT",
                "control_tokens": CONTROL_TOKENS,
            }
        },
    }

    brief["generation"] = {
        "prompt_profile": "ugc_native",
        "delivery": {
            "aspect_ratio": "9:16",
            "orientation": "vertical",
            "capture_mode": (
                "One-hand smartphone POV, slight handheld micro-shake, native Douyin product demo"
            ),
        },
        "environment": {
            "setting": "Warm indoor snack desk with woven mat and festive props",
            "lighting": "Warm tungsten practical upper-left",
            "clutter_and_props": "Calendar 08, tiger figurine, lucky bags, plant visible in bokeh",
            "ambient_floor": (
                "Visible sensor grain, quiet room tone, subtle chip rustle; "
                "warm appetizing native HDR grade, not beauty-polished"
            ),
        },
        "capture_character": {
            "polish_level": "raw_native",
            "notes": (
                "Handheld micro-shake, natural skin on hands, slight focus hunt on ECU — "
                "not studio polished."
            ),
        },
        "control_tokens": CONTROL_TOKENS,
    }

    meta = brief.setdefault("_analysis_meta", {})
    meta.update({
        "depth": "deep",
        "steps_completed": [
            "metadata",
            "scene_detect",
            "motion_classification",
            "keyframes",
            "audio_energy",
            "agent_vision_enrichment",
            "dna_lock",
            "scene_beats",
            "generation_spec_assembled",
        ],
        "steps_failed": skeleton.get("_analysis_meta", {}).get("steps_failed") or [],
        "keyframe_count": len(keyframes),
        "scene_count": 8,
        "has_transcript": False,
        "duration_seconds": source["duration_seconds"],
        "rerun_at": datetime.now(timezone.utc).isoformat(),
    })

    attach_generation_spec_to_brief(brief)
    return brief


def persist_reference_analysis(
    project_id: str,
    *,
    run_dir_name: str = "reference_analysis_run",
) -> dict[str, Any]:
    """Load analyzer skeleton, enrich, validate, write canonical brief + checkpoint."""
    from plugins.openmontage.lib.checkpoint import write_checkpoint

    project_dir = PROJECTS_DIR / project_id
    run_dir = project_dir / "artifacts" / run_dir_name
    skeleton_path = run_dir / "video_analysis_brief.json"
    if not skeleton_path.is_file():
        raise FileNotFoundError(f"Missing analyzer output: {skeleton_path}")

    skeleton = json.loads(skeleton_path.read_text(encoding="utf-8"))
    brief = enrich_snack_desk_reference(skeleton)
    validate_artifact("video_analysis_brief", brief)

    out_path = project_dir / "artifacts" / "video_analysis_brief.json"
    out_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    write_checkpoint(
        PROJECTS_DIR,
        project_id,
        "reference_analysis",
        "completed",
        {"video_analysis_brief": brief},
        pipeline_type="reference-driven",
        style_playbook="clean-professional",
        metadata={"enriched_at": datetime.now(timezone.utc).isoformat()},
    )
    return brief


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Enrich and persist reference analysis brief")
    parser.add_argument("project_id")
    args = parser.parse_args(argv)
    brief = persist_reference_analysis(args.project_id)
    seg = brief.get("generation_spec", {}).get("segments", [{}])[0]
    print(f"Wrote video_analysis_brief.json — assembled_prompt {len(seg.get('assembled_prompt', ''))} chars")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
