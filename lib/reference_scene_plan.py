"""Build reference-driven scene_plan from script + video_analysis_brief."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from lib.assets_composition import (
    AssetsCompositionStrategy,
    resolve_assets_composition_strategy,
    strategy_metadata,
)
from lib.generation_spec import (
    _beats_in_range,
    _collect_scene_beats,
    canonical_generation_prompt_from_scene,
    compile_executable_prompt,
)
from lib.paths import PROJECTS_DIR
from lib.video_gen_units import (
    DEFAULT_VIDEO_GEN_CLIP_SECONDS,
    resolve_video_gen_clip_duration,
    video_gen_unit_ranges,
)


def _sections_in_range(
    sections: list[dict[str, Any]],
    start_seconds: float,
    end_seconds: float,
) -> list[dict[str, Any]]:
    start = float(start_seconds)
    end = float(end_seconds)
    hits: list[dict[str, Any]] = []
    for section in sections:
        if not isinstance(section, dict):
            continue
        sec_start = float(section.get("start_seconds", 0))
        sec_end = float(section.get("end_seconds", sec_start))
        if sec_end <= start or sec_start >= end:
            continue
        hits.append(section)
    return hits


def _editorial_description(
    *,
    unit_sections: list[dict[str, Any]],
    start_seconds: float,
    end_seconds: float,
    clip_index: int,
    clip_count: int,
    gen_clip_seconds: float,
    strategy: AssetsCompositionStrategy,
) -> str:
    labels = [
        str(s.get("label") or s.get("id") or "")
        for s in unit_sections
        if s.get("label") or s.get("id")
    ]
    label_text = " / ".join(labels) if labels else f"clip {clip_index + 1}"
    editorial = end_seconds - start_seconds
    if strategy == "static_composition":
        return (
            f"{gen_clip_seconds:.0f}s 竖屏静图单元 {clip_index + 1}/{clip_count} · {label_text} "
            f"({start_seconds:.1f}–{end_seconds:.1f}s 成片窗口，静图+ffmpeg {gen_clip_seconds:.0f}s，"
            f"快切与 {editorial:.1f}s 精剪由 edit 层处理)"
        )
    return (
        f"{gen_clip_seconds:.0f}s 竖屏生成单元 {clip_index + 1}/{clip_count} · {label_text} "
        f"({start_seconds:.1f}–{end_seconds:.1f}s 成片窗口，API 请求 {gen_clip_seconds:.0f}s，"
        f"快切与 {editorial:.1f}s 精剪由 edit 层处理)"
    )


def _shot_language_for_unit(
    *,
    start_seconds: float,
    end_seconds: float,
    brief: dict[str, Any],
    hero: bool,
) -> dict[str, str]:
    ref_scenes = ((brief.get("structure_analysis") or {}).get("scenes") or [])
    mid = (start_seconds + end_seconds) / 2
    match = None
    for scene in ref_scenes:
        if not isinstance(scene, dict):
            continue
        s0 = float(scene.get("start_time", scene.get("start_seconds", 0)))
        s1 = float(scene.get("end_time", scene.get("end_seconds", s0)))
        if s0 <= mid < s1:
            match = scene
            break
    sl = (match or {}).get("shot_language") or {}
    movement = "dolly_in" if hero else "handheld"
    if sl.get("camera_movement") == "handheld_static":
        movement = "handheld"
    shot_size = "medium" if hero else "close_up"
    if sl.get("shot_size") in {"close_up", "extreme_close_up", "medium"}:
        shot_size = sl["shot_size"].replace("extreme_close_up", "close_up")
    lighting = "tungsten_warm"
    if sl.get("lighting_key") == "warm_tungsten":
        lighting = "tungsten_warm"
    return {
        "shot_size": shot_size,
        "camera_movement": movement,
        "lighting_key": lighting,
        "depth_of_field": str(sl.get("depth_of_field") or ("medium" if hero else "shallow")),
        "color_temperature": "warm",
    }


def _load_production_inputs(project_dir: Path) -> dict[str, Any]:
    meta_path = project_dir / "meta.json"
    if not meta_path.is_file():
        return {}
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    inputs = meta.get("production_inputs")
    return inputs if isinstance(inputs, dict) else {}


def _load_proposal_packet(project_dir: Path) -> dict[str, Any] | None:
    cp_path = project_dir / "checkpoint_proposal.json"
    if not cp_path.is_file():
        return None
    try:
        cp = json.loads(cp_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    packet = cp.get("artifacts", {}).get("proposal_packet")
    return packet if isinstance(packet, dict) else None


def _required_asset_for_unit(
    *,
    strategy: AssetsCompositionStrategy,
    brief: dict[str, Any],
    start: float,
    end: float,
    index: int,
    unit_beats: list[dict[str, Any]],
    gen_clip: float,
    editorial_seconds: float,
) -> dict[str, Any]:
    if strategy == "static_composition":
        description = compile_executable_prompt(
            brief,
            start,
            end,
            asset_type="image",
            establish_dna=(index == 0),
            inherit_dna=(index > 0),
            beats=unit_beats,
        )
        if not description:
            raise ValueError(f"Could not assemble image prompt for {start}-{end}s")
        return {
            "type": "image",
            "description": description,
            "source": "generate",
            "prompt_profile": "still_frame",
            "editorial_duration_seconds": round(editorial_seconds, 3),
            "compose_strategy": "ffmpeg_still_loop",
        }
    executable = compile_executable_prompt(
        brief,
        start,
        end,
        asset_type="video",
        establish_dna=(index == 0),
        inherit_dna=(index > 0),
        beats=unit_beats,
    )
    if not executable:
        raise ValueError(f"Could not assemble executable prompt for {start}-{end}s")
    return {
        "type": "video",
        "description": executable,
        "source": "generate",
        "prompt_profile": "ugc_native_executable",
        "duration": str(int(gen_clip)),
        "editorial_duration_seconds": round(editorial_seconds, 3),
    }


def build_reference_driven_scene_plan(
    script: dict[str, Any],
    brief: dict[str, Any],
    *,
    clip_duration_seconds: float | None = None,
    style_playbook: str | None = None,
    production_inputs: dict[str, Any] | None = None,
    proposal: dict[str, Any] | None = None,
    composition_strategy: AssetsCompositionStrategy | None = None,
) -> dict[str, Any]:
    """Assemble scene_plan: one storyboard scene per gen unit (~10s default).

    When ``composition_strategy`` / env resolution is ``static_composition``,
    units emit ``type: image`` for image_selector + ffmpeg/remotion — never
    ``ugc_native_executable`` video prompts.
    """
    total = float(
        script.get("total_duration_seconds")
        or (brief.get("source") or {}).get("duration_seconds")
        or 0
    )
    sections = [s for s in (script.get("sections") or []) if isinstance(s, dict)]
    gen_clip = float(
        clip_duration_seconds
        or resolve_video_gen_clip_duration(production_inputs)
        or DEFAULT_VIDEO_GEN_CLIP_SECONDS
    )
    ranges = video_gen_unit_ranges(total, gen_clip)

    strategy = composition_strategy or resolve_assets_composition_strategy(
        production_inputs=production_inputs,
        proposal=proposal,
    )
    meta_fields = strategy_metadata(strategy)

    playbook = (
        style_playbook
        or (script.get("metadata") or {}).get("playbook")
        or (brief.get("replication_guidance") or {}).get("suggested_playbook")
        or "clean-professional"
    )
    all_beats = _collect_scene_beats(brief)
    gen_profile = (brief.get("generation") or {}).get("prompt_profile")

    scenes: list[dict[str, Any]] = []
    for index, (start, end) in enumerate(ranges):
        unit_sections = _sections_in_range(sections, start, end)
        unit_beats = _beats_in_range(all_beats, start, end)
        hero = index == len(ranges) - 1
        editorial_seconds = end - start

        primary_section = unit_sections[0] if unit_sections else {}
        section_labels = [
            str(s.get("label") or s.get("id") or "")
            for s in unit_sections
            if s.get("label") or s.get("id")
        ]
        edit_internal_beats = [
            {
                "at_seconds": float(sec.get("start_seconds", 0)),
                "script_section_id": sec.get("id"),
                "beat": sec.get("label") or sec.get("id"),
            }
            for sec in unit_sections
        ]

        if strategy == "static_composition":
            shot_intent = (
                f"image_selector 静图 + ffmpeg {gen_clip:.0f}s · "
                f"{' / '.join(section_labels) if section_labels else f'unit {index + 1}'}"
            )
        else:
            shot_intent = (
                f"video_selector 生成 {gen_clip:.0f}s clip · "
                f"{' / '.join(section_labels) if section_labels else f'unit {index + 1}'}"
            )

        required_asset = _required_asset_for_unit(
            strategy=strategy,
            brief=brief,
            start=start,
            end=end,
            index=index,
            unit_beats=unit_beats,
            gen_clip=gen_clip,
            editorial_seconds=editorial_seconds,
        )

        scenes.append({
            "id": f"sc{index + 1}",
            "type": "broll",
            "description": _editorial_description(
                unit_sections=unit_sections,
                start_seconds=start,
                end_seconds=end,
                clip_index=index,
                clip_count=len(ranges),
                gen_clip_seconds=gen_clip,
                strategy=strategy,
            ),
            "start_seconds": start,
            "end_seconds": end,
            "script_section_id": primary_section.get("id") or f"s{index + 1}",
            "framing": (
                f"9:16 竖屏 {gen_clip:.0f}s 静图单元，Ken Burns/ffmpeg 在 assets/compose"
                if strategy == "static_composition"
                else f"9:16 竖屏 {gen_clip:.0f}s 生成单元，快切在 edit 修剪"
            ),
            "movement": "dolly_in" if hero else "handheld",
            "transition_in": "cut" if index > 0 else "fade",
            "transition_out": "cut",
            "overlay_notes": (
                f"旁白段 {', '.join(str(s.get('id')) for s in unit_sections) or primary_section.get('id')}; "
                f"burn-in 字幕由 edit 烧录"
            ),
            "shot_language": _shot_language_for_unit(
                start_seconds=start,
                end_seconds=end,
                brief=brief,
                hero=hero,
            ),
            "shot_intent": shot_intent,
            "narrative_role": "call_to_action" if hero else "establish_context",
            "information_role": " / ".join(section_labels) if section_labels else f"unit-{index + 1}",
            "hero_moment": hero,
            "required_assets": [required_asset],
            "metadata": {
                "generation_request_duration_seconds": gen_clip,
                "editorial_duration_seconds": round(editorial_seconds, 3),
                "edit_internal_beats": edit_internal_beats,
                **(
                    {"video_compose_strategy": "ffmpeg_still_loop"}
                    if strategy == "static_composition"
                    else {}
                ),
            },
        })

    unit_label = "static image" if strategy == "static_composition" else "video-gen clip"
    return {
        "version": "1.0",
        "style_playbook": playbook,
        "scenes": scenes,
        "metadata": {
            **meta_fields,
            "scene_count": len(scenes),
            "generation_unit_seconds": gen_clip,
            "generation_unit_source": "lib/video_gen_units.video_gen_unit_ranges",
            "total_duration_seconds": total,
            "timing_note": (
                f"{len(scenes)} {unit_label}(s) at ~{gen_clip:.0f}s each. "
                "Script sections are packed inside each unit; "
                "edit/compose trims to editorial windows and applies narration timing."
            ),
            "derived_from": "script.json + video_analysis_brief.json",
            "edit_internal_beats": [
                {
                    "at_seconds": float(sec.get("start_seconds", 0)),
                    "script_section_id": sec.get("id"),
                    "beat": sec.get("label") or sec.get("id"),
                }
                for sec in sections
            ],
            "reference_prompt_source": (
                "video_analysis_brief via lib.generation_spec.compile_executable_prompt "
                f"(asset_type={'video' if strategy == 'ugc_native' else 'image'}); "
                "full reverse timeline in video_analysis_brief.json"
            ),
            "reference_prompt_profile": gen_profile,
            "executable_prompt_profile": (
                "ugc_native_executable"
                if strategy == "ugc_native"
                else "still_frame"
            ),
        },
    }


def sync_asset_manifest_prompts(
    manifest: dict[str, Any],
    scene_plan: dict[str, Any],
) -> dict[str, Any]:
    """Align stale placeholder manifest prompts with scene_plan executable prompts."""
    scenes_by_id = {
        str(s.get("id")): s
        for s in (scene_plan.get("scenes") or [])
        if isinstance(s, dict) and s.get("id")
    }
    plan_meta = scene_plan.get("metadata") or {}
    strategy = plan_meta.get("assets_composition_strategy", "ugc_native")
    for asset in manifest.get("assets") or []:
        if not isinstance(asset, dict):
            continue
        scene = scenes_by_id.get(str(asset.get("scene_id") or ""))
        if not scene:
            continue
        types = ("image",) if strategy == "static_composition" else ("video", "image")
        prompt = canonical_generation_prompt_from_scene(scene, types=types)
        if not prompt:
            continue
        tool = str(asset.get("source_tool") or "")
        if tool in {"", "frame_sampler", "image_selector"} or asset.get("type") in {"image", "video"}:
            asset["prompt"] = prompt
            profile = plan_meta.get("executable_prompt_profile")
            if profile:
                asset["prompt_profile"] = profile
            visual_asset = next(
                (
                    a for a in (scene.get("required_assets") or [])
                    if isinstance(a, dict) and a.get("type") in {"video", "image"}
                ),
                None,
            )
            if isinstance(visual_asset, dict):
                if visual_asset.get("duration"):
                    asset["duration"] = visual_asset["duration"]
                if visual_asset.get("editorial_duration_seconds") is not None:
                    asset["editorial_duration_seconds"] = visual_asset["editorial_duration_seconds"]
                if visual_asset.get("compose_strategy"):
                    asset["compose_strategy"] = visual_asset["compose_strategy"]
            if tool == "frame_sampler":
                asset["generation_summary"] = (
                    "Placeholder keyframe; prompt synced from scene_plan.required_assets"
                )
    meta = manifest.setdefault("metadata", {})
    meta["prompt_synced_from"] = "scene_plan.required_assets"
    if strategy == "static_composition":
        meta.setdefault("video_strategy", "ffmpeg_still_loop")
    return manifest


def sync_project_asset_manifest_prompts(project_id: str) -> dict[str, Any]:
    """Rewrite asset_manifest.json prompts from the canonical scene_plan."""
    project_dir = PROJECTS_DIR / project_id
    artifacts = project_dir / "artifacts"
    scene_plan = json.loads((artifacts / "scene_plan.json").read_text(encoding="utf-8"))
    manifest_path = artifacts / "asset_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {"version": "1.0", "assets": []}
    manifest = sync_asset_manifest_prompts(manifest, scene_plan)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def regenerate_scene_plan_for_project(project_id: str) -> dict[str, Any]:
    """Load project artifacts and rebuild scene_plan.json."""
    project_dir = PROJECTS_DIR / project_id
    artifacts = project_dir / "artifacts"
    script = json.loads((artifacts / "script.json").read_text(encoding="utf-8"))
    brief = json.loads((artifacts / "video_analysis_brief.json").read_text(encoding="utf-8"))
    production_inputs = _load_production_inputs(project_dir)
    proposal = _load_proposal_packet(project_dir)
    scene_plan = build_reference_driven_scene_plan(
        script,
        brief,
        production_inputs=production_inputs,
        proposal=proposal,
    )
    (artifacts / "scene_plan.json").write_text(
        json.dumps(scene_plan, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    if (artifacts / "asset_manifest.json").is_file():
        sync_project_asset_manifest_prompts(project_id)
    return scene_plan


def main(argv: list[str] | None = None) -> int:
    import argparse

    from schemas.artifacts import validate_artifact

    parser = argparse.ArgumentParser(description="Regenerate reference-driven scene_plan")
    parser.add_argument("project_id")
    args = parser.parse_args(argv)
    scene_plan = regenerate_scene_plan_for_project(args.project_id)
    validate_artifact("scene_plan", scene_plan)
    gen_unit = (scene_plan.get("metadata") or {}).get("generation_unit_seconds")
    strategy = (scene_plan.get("metadata") or {}).get("assets_composition_strategy")
    print(
        f"Wrote {args.project_id}/artifacts/scene_plan.json "
        f"({len(scene_plan['scenes'])} scenes, {gen_unit}s gen units, strategy={strategy})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
