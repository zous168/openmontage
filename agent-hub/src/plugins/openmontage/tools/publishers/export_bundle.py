"""Local export bundler — the first PUBLISH-tier tool.

Every pipeline ends in a `publish` stage that produces a `publish_log` artifact,
but `tools/publishers/` shipped empty, so the mechanical packaging (copying the
render, writing metadata files, laying out the export directory, and emitting a
schema-valid `publish_log`) had to be hand-rolled by the agent each time.

This tool does that packaging deterministically and locally — no external
account, no upload, no cost. It takes the final render path plus the SEO
metadata the publish-director skill prepares and writes a self-contained export
bundle a creator can hand to any platform, returning a validated `publish_log`
entry with `status: "exported"`.

A networked publisher (e.g. a YouTube uploader) can be added later as a separate
`provider` under the same `publish` capability.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from plugins.openmontage.tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)


class ExportBundle(BaseTool):
    name = "export_bundle"
    version = "0.1.0"
    tier = ToolTier.PUBLISH
    capability = "publish"
    provider = "local"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC
    runtime = ToolRuntime.LOCAL

    dependencies = []  # pure filesystem packaging
    install_instructions = "No setup required — runs locally with the Python standard library."

    agent_skills = []

    capabilities = ["package_export", "write_publish_log"]
    supports = {
        "local_offline": True,
        "free": True,
        "uploads": False,
    }
    best_for = [
        "packaging a finished render for hand-off to any platform",
        "producing a schema-valid publish_log without an external account",
        "offline / no-API-key publishing",
    ]
    not_good_for = [
        "uploading directly to YouTube/TikTok/etc. (no network publish)",
        "generating SEO metadata or thumbnails (the publish-director prepares those)",
    ]

    input_schema = {
        "type": "object",
        "required": ["video_path", "title"],
        "properties": {
            "video_path": {
                "type": "string",
                "description": "Path to the final rendered video (from render_report.outputs[].path).",
            },
            "title": {"type": "string", "description": "Video title / SEO title."},
            "project_name": {
                "type": "string",
                "description": "Project name; used for the export folder. Defaults to the video's parent-of-parent dir name.",
            },
            "export_dir": {
                "type": "string",
                "description": "Override the export root. Defaults to 'exports/<project_name>'.",
            },
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "chapters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "description": "Either {start_seconds, title} or {time, label}.",
                },
            },
            "subtitles_path": {"type": "string"},
            "thumbnail_path": {"type": "string"},
            "thumbnail_concept": {
                "type": "object",
                "description": "Thumbnail concept JSON when no rendered thumbnail exists.",
            },
            "thumbnail_preferred_provider": {
                "type": "string",
                "description": "Preferred image provider when cover source is text_to_image (image_selector).",
            },
            "platform": {
                "type": "string",
                "description": "Target platform label for the publish_log entry. Defaults to 'local'.",
            },
            "visibility": {"type": "string", "enum": ["public", "private", "unlisted"]},
            "timestamp": {
                "type": "string",
                "description": "Override the ISO-8601 timestamp (mainly for deterministic tests).",
            },
        },
    }
    output_schema = {
        "type": "object",
        "properties": {
            "publish_log": {"type": "object"},
            "export_path": {"type": "string"},
            "files_written": {"type": "array", "items": {"type": "string"}},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=128, vram_mb=0, disk_mb=0, network_required=False
    )
    side_effects = ["writes an export bundle directory to disk"]
    user_visible_verification = [
        "Open the export folder and confirm the video, metadata, and chapters are present and correct",
    ]

    # ---- Helpers ----

    @staticmethod
    def _format_chapter_time(seconds: float) -> str:
        seconds = int(round(seconds))
        h, rem = divmod(seconds, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{s:02d}"
        return f"{m}:{s:02d}"

    def _chapter_lines(self, chapters: list[dict[str, Any]]) -> list[str]:
        lines: list[str] = []
        for ch in chapters:
            label = ch.get("title") or ch.get("label") or ""
            if "start_seconds" in ch or "time_seconds" in ch:
                ts = self._format_chapter_time(ch.get("start_seconds", ch.get("time_seconds", 0)))
            elif "time" in ch:
                ts = str(ch["time"])
            else:
                ts = "0:00"
            lines.append(f"{ts} - {label}".rstrip(" -"))
        return lines

    # ---- Execution ----

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        from plugins.openmontage.lib.deliverable_spec import load_deliverable_from_project

        video_path = Path(inputs["video_path"]).expanduser()
        if not video_path.is_file():
            return ToolResult(success=False, error=f"video_path not found: {video_path}")

        title = inputs["title"]
        project_name = inputs.get("project_name") or self._infer_project_name(video_path)

        deliverable = None
        resolved_video = video_path.resolve()
        if resolved_video.parent.name == "renders":
            deliverable = load_deliverable_from_project(resolved_video.parent.parent)

        # Explicitly-provided optional assets must exist — silently dropping them
        # would ship a publish package missing part of an approved deliverable.
        for key in ("subtitles_path", "thumbnail_path"):
            val = inputs.get(key)
            if val and not Path(val).expanduser().is_file():
                return ToolResult(success=False, error=f"{key} provided but not found: {val}")

        export_root = (
            Path(inputs["export_dir"]).expanduser()
            if inputs.get("export_dir")
            else self._default_export_dir(video_path, project_name)
        )

        video_dir = export_root / "video"
        meta_dir = export_root / "metadata"
        thumb_dir = export_root / "thumbnails"
        for d in (video_dir, meta_dir, thumb_dir):
            d.mkdir(parents=True, exist_ok=True)

        files_written: list[str] = []

        # Video
        out_video = video_dir / f"output{video_path.suffix or '.mp4'}"
        shutil.copy2(video_path, out_video)
        files_written.append(str(out_video))

        # Subtitles (optional)
        subs_in = inputs.get("subtitles_path")
        if subs_in:
            subs_in = Path(subs_in).expanduser()
            if subs_in.is_file():
                out_subs = video_dir / f"subtitles{subs_in.suffix or '.srt'}"
                shutil.copy2(subs_in, out_subs)
                files_written.append(str(out_subs))

        description = inputs.get("description", "")
        tags = inputs.get("tags", []) or []
        hashtags = inputs.get("hashtags", []) or []
        chapters = inputs.get("chapters", []) or []
        chapter_lines = self._chapter_lines(chapters)

        cover_brief = None
        project_dir = None
        if resolved_video.parent.name == "renders":
            project_dir = resolved_video.parent.parent
            from plugins.openmontage.lib.publish_intake import load_cover_brief_from_project

            cover_brief = load_cover_brief_from_project(project_dir)

        # metadata.json
        metadata = {
            "title": title,
            "description": description,
            "tags": tags,
            "hashtags": hashtags,
            "chapters": chapters,
        }
        if deliverable:
            metadata["deliverable"] = {
                "resolution": deliverable["resolution"],
                "aspect_ratio": deliverable["aspect_ratio"],
                "quality_tier": deliverable["quality_tier"],
                "fps": deliverable["fps"],
                "target_platform": deliverable.get("target_platform"),
            }
        if cover_brief:
            metadata["cover_brief"] = {
                "text_hook": cover_brief.get("text_hook"),
                "style_notes": cover_brief.get("style_notes"),
                "source": cover_brief.get("source"),
            }
        meta_json = meta_dir / "metadata.json"
        meta_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        files_written.append(str(meta_json))

        # description.txt (description + chapters appended, ready to paste)
        desc_parts = [description] if description else []
        if chapter_lines:
            desc_parts.append("\n".join(chapter_lines))
        desc_txt = meta_dir / "description.txt"
        desc_txt.write_text("\n\n".join(desc_parts) + ("\n" if desc_parts else ""), encoding="utf-8")
        files_written.append(str(desc_txt))

        # tags.txt (one per line)
        if tags:
            tags_txt = meta_dir / "tags.txt"
            tags_txt.write_text("\n".join(tags) + "\n", encoding="utf-8")
            files_written.append(str(tags_txt))

        # chapters.txt
        if chapter_lines:
            chapters_txt = meta_dir / "chapters.txt"
            chapters_txt.write_text("\n".join(chapter_lines) + "\n", encoding="utf-8")
            files_written.append(str(chapters_txt))

        # Thumbnail: explicit path > text_to_image > auto_frame > concept_only
        thumb_in = inputs.get("thumbnail_path")
        thumbnail_concept = inputs.get("thumbnail_concept")
        style_playbook = ""
        marker_path = (project_dir / "project.json") if project_dir else None
        if marker_path and marker_path.is_file():
            try:
                marker = json.loads(marker_path.read_text(encoding="utf-8"))
                style_playbook = str(marker.get("style_playbook") or "")
            except (OSError, json.JSONDecodeError):
                pass

        cover_source = (cover_brief or {}).get("source", "auto_frame")
        preferred_provider = inputs.get("thumbnail_preferred_provider") or "auto"
        generation_meta: dict[str, Any] | None = None
        t2i_error: str | None = None
        thumbnail_written = False

        if thumb_in and Path(thumb_in).expanduser().is_file():
            thumb_in = Path(thumb_in).expanduser()
            out_thumb = thumb_dir / f"thumbnail{thumb_in.suffix or '.png'}"
            shutil.copy2(thumb_in, out_thumb)
            files_written.append(str(out_thumb))
            thumbnail_written = True
        elif cover_brief and cover_source == "text_to_image":
            from plugins.openmontage.lib.publish_intake import (
                build_thumbnail_prompt,
                generate_cover_thumbnail,
                thumbnail_dimensions,
            )

            width, height, aspect = thumbnail_dimensions(deliverable)
            prompt = build_thumbnail_prompt(
                cover_brief,
                title=title,
                style_playbook=style_playbook,
                deliverable=deliverable,
            )
            out_thumb = thumb_dir / "thumbnail.png"
            artifact, gen_meta, err = generate_cover_thumbnail(
                prompt,
                out_thumb,
                width=width,
                height=height,
                aspect_ratio=aspect,
                preferred_provider=preferred_provider,
            )
            if artifact:
                if artifact.resolve() != out_thumb.resolve():
                    shutil.copy2(artifact, out_thumb)
                files_written.append(str(out_thumb))
                thumbnail_written = True
                generation_meta = gen_meta
            else:
                t2i_error = err
                cover_source = "auto_frame"

        if not thumbnail_concept and cover_brief:
            from plugins.openmontage.lib.publish_intake import build_thumbnail_concept

            if generation_meta is None and t2i_error:
                generation_meta = {"error": t2i_error, "fallback": "auto_frame"}
            thumbnail_concept = build_thumbnail_concept(
                cover_brief,
                title=title,
                style_playbook=style_playbook,
                deliverable=deliverable,
                generation=generation_meta,
            )
        elif thumbnail_concept and generation_meta:
            thumbnail_concept = dict(thumbnail_concept)
            thumbnail_concept["generation"] = generation_meta

        explicit_thumb = bool(thumb_in and Path(thumb_in).expanduser().is_file())
        if thumbnail_concept and not explicit_thumb:
            concept = thumb_dir / "concept.json"
            concept.write_text(json.dumps(thumbnail_concept, indent=2), encoding="utf-8")
            files_written.append(str(concept))

        if (
            not thumbnail_written
            and cover_brief
            and cover_source == "auto_frame"
        ):
            from plugins.openmontage.lib.publish_intake import default_frame_capture_seconds, extract_frame_thumbnail

            extracted = extract_frame_thumbnail(
                video_path,
                thumb_dir,
                default_frame_capture_seconds(),
            )
            if extracted:
                files_written.append(str(extracted))

        timestamp = inputs.get("timestamp") or datetime.now(timezone.utc).isoformat()
        platform = inputs.get("platform") or (deliverable or {}).get("target_platform") or "local"
        entry: dict[str, Any] = {
            "platform": platform,
            "status": "exported",
            "export_path": str(export_root),
            "timestamp": timestamp,
            "metadata_used": {
                "title": title,
                "description": description,
                "hashtags": hashtags,
                "chapters": chapters,
            },
        }
        if deliverable:
            entry["metadata_used"]["deliverable"] = metadata.get("deliverable")
        if cover_brief:
            entry["metadata_used"]["cover_brief"] = metadata.get("cover_brief")
        if inputs.get("visibility"):
            entry["visibility"] = inputs["visibility"]

        publish_log = {"version": "1.0", "entries": [entry]}

        # Validate against the canonical schema so a bad entry fails here, not at checkpoint.
        try:
            from plugins.openmontage.schemas.artifacts import validate_artifact

            validate_artifact("publish_log", publish_log)
        except Exception as exc:  # pragma: no cover - defensive
            return ToolResult(success=False, error=f"publish_log failed schema validation: {exc}")

        return ToolResult(
            success=True,
            data={
                "publish_log": publish_log,
                "export_path": str(export_root),
                "files_written": files_written,
            },
            artifacts=[str(out_video)],
        )

    @staticmethod
    def _default_export_dir(video_path: Path, project_name: str) -> Path:
        """Keep run output inside the project workspace.

        When the render lives at ``projects/<name>/renders/...`` (the OpenMontage
        convention), default the bundle to ``projects/<name>/exports/`` alongside
        ``artifacts/``, ``assets/`` and ``renders/``. Otherwise fall back to a
        top-level ``exports/<project_name>/``.
        """
        resolved = video_path.resolve()
        if resolved.parent.name == "renders":
            return resolved.parent.parent / "exports"
        return Path("exports") / project_name

    @staticmethod
    def _infer_project_name(video_path: Path) -> str:
        # projects/<name>/renders/final.mp4 -> <name>; fall back to the file stem.
        parents = video_path.resolve().parents
        if len(parents) >= 2:
            return parents[1].name
        return video_path.stem
