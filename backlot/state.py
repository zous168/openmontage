"""BoardState derivation — turn a project directory into renderable state.

Everything here is read-only and defensive: a malformed JSON file, a missing
artifact, or a half-written checkpoint must degrade the board, never crash it
(design principle: "never block, never break").
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from lib.events import read_events
from lib.paths import PROJECTS_DIR, REPO_ROOT  # single source of truth (env-overridable)

MEDIA_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
MEDIA_VIDEO_EXT = {".mp4", ".webm", ".mov"}
MEDIA_AUDIO_EXT = {".mp3", ".wav", ".m4a", ".ogg"}
# HTML5 <video> reliably plays these; MKV/HEVC need a poster + H.264 preview.
BROWSER_VIDEO_EXT = {".mp4", ".webm"}
_BROWSER_VIDEO_CODECS = frozenset({"h264", "avc1", "vp8", "vp9", "av1"})
_NON_BROWSER_VIDEO_CODECS = frozenset({"hevc", "h265", "mpeg4", "msmpeg4v3", "wmv3", "vc1"})
_PREVIEW_VIDEO_PRIORITY = (
    "assets/video/source_preview.mp4",
    "assets/video/trim_work.mp4",
)

# Directories inside a project we never scan for media (build noise).
SCAN_EXCLUDE = {"node_modules", ".git", "__pycache__", "history", ".cache"}

# Stages every pipeline shares (fallback rail when the manifest is unknown).
FALLBACK_STAGES = [
    "research", "proposal", "idea", "script", "scene_plan",
    "assets", "edit", "compose", "publish",
]

# Simulated / screenshot demo workspaces — hidden from the library grid.
# Direct URLs (/p/<id>) still work for README walkthroughs.
_DEMO_PROJECT_IDS = frozenset({"backlot-demo-run", "the-last-lighthouse"})

# How long (seconds) without filesystem activity before a board reads "idle".
LIVE_WINDOW_SECONDS = 5 * 60

# An in_progress stage with no filesystem activity for this long is flagged
# as possibly stalled (F-05: a wedged agent must be visible, not silent —
# heartbeat checkpoints and tool events both reset the clock).
STALL_WINDOW_SECONDS = 10 * 60


def _read_json(path: Path) -> Optional[dict]:
    """Read a JSON file, returning None on any failure."""
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None


def _is_demo_project(project_dir: Path) -> bool:
    """True for simulate-run / screenshot fixtures — not real productions."""
    if project_dir.name in _DEMO_PROJECT_IDS:
        return True
    marker = _read_json(project_dir / "project.json") or {}
    return marker.get("demo") is True


def _rel(project_dir: Path, path: Path) -> str:
    """Project-relative POSIX path for media URLs."""
    try:
        return path.resolve().relative_to(Path(project_dir).resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


from backlot.bootstrap import pipeline_label_zh

def _load_pipeline_meta(pipeline_type: Optional[str]) -> dict[str, Any]:
    """Stage order + gate flags from the manifest; graceful fallback."""
    if pipeline_type and pipeline_type != "unknown":
        try:
            from lib.pipeline_loader import load_pipeline
            manifest = load_pipeline(pipeline_type)
            stages = [
                {
                    "name": s["name"],
                    "gated": bool(s.get("human_approval_default", False)),
                    "produces": [
                        str(name) for name in (s.get("produces") or [])
                        if isinstance(name, str) and name
                    ],
                }
                for s in manifest.get("stages", [])
                if isinstance(s, dict) and s.get("name")
            ]
            if stages:
                return {
                    "pipeline_type": pipeline_type,
                    "label_zh": pipeline_label_zh(pipeline_type),
                    "stages": stages,
                    "known": True,
                }
        except Exception:
            pass
    ptype = pipeline_type or "unknown"
    return {
        "pipeline_type": ptype,
        "label_zh": pipeline_label_zh(ptype),
        "stages": [{"name": s, "gated": False, "produces": []} for s in FALLBACK_STAGES],
        "known": False,
    }


def _resolve_artifact(project_dir: Path, value: Any) -> Optional[dict]:
    """Checkpoint artifacts may be inline dicts or path strings — resolve both.

    Path references are only followed INSIDE the project directory: a
    checkpoint must not be able to pull arbitrary JSON from elsewhere on
    disk onto the board (F-04).
    """
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value:
        p = Path(value)
        if not p.is_absolute():
            p = project_dir / value
        try:
            p.resolve().relative_to(Path(project_dir).resolve())
        except (ValueError, OSError):
            return None
        return _read_json(p)
    return None


def _collect_checkpoints(project_dir: Path) -> dict[str, dict]:
    """Current checkpoint per stage (raw dicts, unvalidated by design)."""
    out: dict[str, dict] = {}
    for path in sorted(project_dir.glob("checkpoint_*.json")):
        stage = path.stem[len("checkpoint_"):]
        data = _read_json(path)
        if data is not None:
            data["_mtime"] = path.stat().st_mtime
            out[stage] = data
    return out


def _collect_history(project_dir: Path) -> dict[str, list[dict]]:
    """Archived checkpoint versions per stage (oldest first)."""
    history_dir = project_dir / "history"
    out: dict[str, list[dict]] = {}
    if not history_dir.is_dir():
        return out
    for path in sorted(history_dir.glob("checkpoint_*.json")):
        m = re.match(r"checkpoint_(.+?)_\d", path.stem)
        stage = m.group(1) if m else path.stem[len("checkpoint_"):]
        data = _read_json(path)
        if data is not None:
            out.setdefault(stage, []).append(data)
    return out


def _build_stage_rail(
    pipeline_meta: dict,
    checkpoints: dict[str, dict],
    history: dict[str, list[dict]],
) -> list[dict]:
    """One entry per manifest stage with derived status + gate audit."""
    rail = []
    manifest_stage_names = {s["name"] for s in pipeline_meta["stages"]}
    for stage_def in pipeline_meta["stages"]:
        name = stage_def["name"]
        cp = checkpoints.get(name)
        versions = history.get(name, [])
        status = cp.get("status") if cp else "pending"
        entry: dict[str, Any] = {
            "name": name,
            "gated": stage_def["gated"],
            "produces": list(stage_def.get("produces") or []),
            "status": status or "pending",
            "timestamp": cp.get("timestamp") if cp else None,
            "review": cp.get("review") if cp else None,
            "cost_snapshot": cp.get("cost_snapshot") if cp else None,
            "error": cp.get("error") if cp else None,
            "human_approved": cp.get("human_approved") if cp else None,
            "partial_progress": (cp.get("metadata") or {}).get("partial_progress") if cp else None,
            "versions": len(versions) + (1 if cp else 0),
            # Chronological status trail (history + current) — powers replay.
            "history_entries": (
                [{"status": v.get("status"), "timestamp": v.get("timestamp")} for v in versions]
                + ([{"status": cp.get("status"), "timestamp": cp.get("timestamp")}] if cp else [])
            ),
        }
        # Gate audit: a gated stage that completed without ever passing
        # through awaiting_human (current or archived) was gate-skipped.
        if (
            stage_def["gated"]
            and cp is not None
            and cp.get("status") == "completed"
        ):
            saw_wait = any(v.get("status") == "awaiting_human" for v in versions)
            approved = bool(cp.get("human_approved"))
            entry["gate_skipped"] = not (saw_wait or approved)
        rail.append(entry)

    # Checkpoints for stages the manifest doesn't declare (legacy runs,
    # pipeline mismatch) still deserve a slot — at their canonical position
    # in the pipeline, not dangling after publish ("idea" belongs up front).
    canon = {name: i for i, name in enumerate(FALLBACK_STAGES)}
    for name, cp in checkpoints.items():
        if name in manifest_stage_names:
            continue
        entry = {
            "name": name,
            "gated": False,
            "produces": [
                str(artifact_name)
                for artifact_name in (cp.get("artifacts") or {})
                if isinstance(artifact_name, str) and artifact_name
            ],
            "status": cp.get("status") or "unknown",
            "timestamp": cp.get("timestamp"),
            "review": cp.get("review"),
            "cost_snapshot": cp.get("cost_snapshot"),
            "error": cp.get("error"),
            "human_approved": cp.get("human_approved"),
            "partial_progress": None,
            "versions": 1 + len(history.get(name, [])),
            "undeclared": True,
        }
        pos = canon.get(name)
        if pos is None:
            rail.append(entry)  # truly unknown name — end of rail
            continue
        insert_at = len(rail)
        for i, existing in enumerate(rail):
            existing_pos = canon.get(existing["name"])
            if existing_pos is not None and existing_pos > pos:
                insert_at = i
                break
        rail.insert(insert_at, entry)
    return rail


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

ARTIFACT_FILES = {
    "research_brief": "research_brief.json",
    "brief": "brief.json",
    "proposal_packet": "proposal_packet.json",
    "script": "script.json",
    "scene_plan": "scene_plan.json",
    "asset_manifest": "asset_manifest.json",
    "edit_decisions": "edit_decisions.json",
    "render_report": "render_report.json",
    "final_review": "final_review.json",
    "publish_log": "publish_log.json",
    "decision_log": "decision_log.json",
    "source_media_review": "source_media_review.json",
    "video_analysis_brief": "video_analysis_brief.json",
}

# Fallback when manifest `produces` is empty (legacy checkpoints).
_FALLBACK_STAGE_PRODUCES: dict[str, list[str]] = {
    "research": ["research_brief"],
    "proposal": ["proposal_packet", "decision_log"],
    "idea": ["brief"],
    "script": ["script"],
    "scene_plan": ["scene_plan"],
    "assets": ["asset_manifest"],
    "edit": ["edit_decisions"],
    "compose": ["render_report", "final_review"],
    "publish": ["publish_log"],
    "reference_analysis": ["video_analysis_brief"],
}

# Written before/at intake — not always declared in stage `produces`.
_BOOTSTRAP_ARTIFACTS: dict[str, list[str]] = {
    "source_media_review": ["idea", "proposal", "script"],
    "video_analysis_brief": ["reference_analysis"],
}


def _checkpoint_artifact_names(cp: Optional[dict[str, Any]]) -> list[str]:
    if not cp:
        return []
    arts = cp.get("artifacts") or {}
    return [str(k) for k in arts if isinstance(k, str) and k]


def _manifest_input_stages(pipeline_meta: dict[str, Any], art_name: str) -> list[str]:
    refs: list[str] = []
    for stage_def in pipeline_meta.get("stages") or []:
        if not isinstance(stage_def, dict):
            continue
        for key in ("optional_artifacts_in", "required_artifacts_in"):
            for name in (stage_def.get(key) or []):
                if name == art_name and stage_def.get("name"):
                    refs.append(str(stage_def["name"]))
                    break
    return refs


def _build_artifact_provenance(
    stages: list[dict[str, Any]],
    checkpoints: dict[str, dict[str, Any]],
    pipeline_meta: dict[str, Any],
) -> dict[str, list[str]]:
    """Map artifact -> stage(s) that actually emitted it (checkpoint-first)."""
    provenance: dict[str, list[str]] = {}
    for stage in stages:
        stage_name = stage.get("name") or ""
        if not stage_name:
            continue
        cp = checkpoints.get(stage_name)
        for art_name in _checkpoint_artifact_names(cp):
            if art_name == "decision_log":
                continue
            provenance.setdefault(art_name, [])
            if stage_name not in provenance[art_name]:
                provenance[art_name].append(stage_name)
    for stage in stages:
        stage_name = stage.get("name") or ""
        for art_name in _stage_produces(stage):
            if art_name == "decision_log":
                continue
            if art_name not in provenance:
                provenance[art_name] = [stage_name]
    for art_name, hints in _BOOTSTRAP_ARTIFACTS.items():
        if art_name in provenance:
            continue
        manifest_refs = _manifest_input_stages(pipeline_meta, art_name)
        if manifest_refs:
            provenance[art_name] = [manifest_refs[0]]
        elif hints:
            provenance[art_name] = [hints[0]]
    return provenance


def _resolve_stage_outputs(
    stage: dict[str, Any],
    cp: Optional[dict[str, Any]],
    artifact_keys: set[str],
) -> list[str]:
    from_cp = [a for a in _checkpoint_artifact_names(cp) if a != "decision_log"]
    if from_cp:
        return from_cp
    declared = [a for a in _stage_produces(stage) if a != "decision_log"]
    status = (cp or {}).get("status")
    if status and status != "pending":
        present = [a for a in declared if a in artifact_keys]
        if present:
            return present
    return declared


def _collect_artifacts(project_dir: Path, checkpoints: dict[str, dict]) -> dict[str, dict]:
    """Artifacts from artifacts/*.json, backfilled from checkpoint payloads."""
    artifacts: dict[str, dict] = {}
    art_dir = project_dir / "artifacts"
    for name, filename in ARTIFACT_FILES.items():
        data = _read_json(art_dir / filename)
        if data is not None:
            artifacts[name] = data
    # decision_log historically also lives at project root
    if "decision_log" not in artifacts:
        data = _read_json(project_dir / "decision_log.json")
        if data is not None:
            artifacts["decision_log"] = data
    # Backfill from checkpoint-embedded artifacts.
    for cp in checkpoints.values():
        for name, value in (cp.get("artifacts") or {}).items():
            if name not in artifacts:
                resolved = _resolve_artifact(project_dir, value)
                if resolved is not None:
                    artifacts[name] = resolved
    return artifacts


# ---------------------------------------------------------------------------
# Storyboard join
# ---------------------------------------------------------------------------

def _resolve_asset_path(project_dir: Path, raw_path: str) -> Optional[Path]:
    """Manifest paths appear in several real-world flavors — try them all.

    Observed on disk: project-relative ("assets/images/x.png"),
    repo-relative ("projects/<id>/assets/images/x.png"), and absolute.
    """
    if not raw_path:
        return None
    p = Path(raw_path)
    candidates = []
    if p.is_absolute():
        candidates.append(p)
    else:
        candidates.append(project_dir / raw_path)
        candidates.append(REPO_ROOT / raw_path)
        # repo-relative with the project prefix repeated
        parts = p.parts
        if len(parts) > 2 and parts[0] == "projects":
            candidates.append(project_dir.parent / Path(*parts[1:]))
    for c in candidates:
        try:
            if c.is_file():
                return c
        except OSError:
            continue
    return None


def _asset_entry(project_dir: Path, asset: dict) -> dict:
    """Normalize a manifest asset entry + resolve file existence.

    A file that resolves OUTSIDE the project directory is treated as
    not-servable (exists=False): /media only serves within the project, and
    a bare-filename fallback path would 404 or hit the wrong file.
    """
    raw_path = asset.get("path") or ""
    resolved = _resolve_asset_path(project_dir, raw_path)
    if resolved is not None:
        try:
            resolved.resolve().relative_to(Path(project_dir).resolve())
        except (ValueError, OSError):
            resolved = None
    file_path = resolved if resolved is not None else (project_dir / raw_path)
    exists = resolved is not None
    kind = asset.get("type") or ""
    if not kind and file_path.suffix:
        ext = file_path.suffix.lower()
        if ext in MEDIA_IMAGE_EXT:
            kind = "image"
        elif ext in MEDIA_VIDEO_EXT:
            kind = "video"
        elif ext in MEDIA_AUDIO_EXT:
            kind = "audio"
    # A visual is only *renderable* on the board if the file it points at is
    # actually a raster image or a video. Bespoke/atelier assets (type
    # "animation" pointing at a .tsx composition) exist on disk but can't be
    # thumbnailed — routing them to <img> yields a broken image. The board
    # falls back to a per-scene snapshot or the shot-spec placeholder instead.
    ext = file_path.suffix.lower()
    renderable = exists and ext in (MEDIA_IMAGE_EXT | MEDIA_VIDEO_EXT)
    return {
        "id": asset.get("id"),
        "type": kind,
        "scene_id": asset.get("scene_id"),
        "path": _rel(project_dir, file_path) if exists else raw_path,
        "exists": exists,
        "renderable": renderable,
        "prompt": asset.get("prompt"),
        "model": asset.get("model"),
        "source_tool": asset.get("source_tool"),
        "provider": asset.get("provider"),
        "cost_usd": asset.get("cost_usd"),
        "quality_score": asset.get("quality_score"),
        "duration_seconds": asset.get("duration_seconds"),
        "resolution": asset.get("resolution"),
    }


def _find_scene_snapshot(project_dir: Path, scene_id: str) -> Optional[dict]:
    """A per-scene review still, if the run wrote one.

    Atelier/animation scenes have no thumbnailable asset file, so the
    assets-stage snapshot (`snapshots/<scene_id>.png`) is what the filmstrip
    shows. Accept exact `<scene_id>.<ext>` and `<scene_id>_*.<ext>` forms.
    """
    snap_dir = project_dir / "snapshots"
    if not scene_id or not snap_dir.is_dir():
        return None
    try:
        for f in sorted(snap_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in MEDIA_IMAGE_EXT:
                continue
            stem = f.stem
            if stem == scene_id or stem.startswith(f"{scene_id}_"):
                return {
                    "id": f"snap_{scene_id}",
                    "type": "image",
                    "scene_id": scene_id,
                    "path": _rel(project_dir, f),
                    "exists": True,
                    "renderable": True,
                    "snapshot": True,
                }
    except OSError:
        return None
    return None


def _find_script_section(scene: dict, sections: list[dict]) -> Optional[dict]:
    """Join scene → script section by id, falling back to timing overlap."""
    sid = scene.get("script_section_id")
    if sid:
        for s in sections:
            if s.get("id") == sid:
                return s
    start = scene.get("start_seconds")
    end = scene.get("end_seconds")
    if start is None or end is None:
        return None
    best, best_overlap = None, 0.0
    for s in sections:
        s0, s1 = s.get("start_seconds"), s.get("end_seconds")
        if s0 is None or s1 is None:
            continue
        overlap = min(end, s1) - max(start, s0)
        if overlap > best_overlap:
            best, best_overlap = s, overlap
    return best


def _build_storyboard(
    project_dir: Path,
    artifacts: dict[str, dict],
    events: list[dict],
) -> Optional[dict]:
    """Scene cards: scene_plan × script × asset_manifest (+ live events)."""
    scene_plan = artifacts.get("scene_plan")
    if not scene_plan or not isinstance(scene_plan.get("scenes"), list):
        return None
    sections = (artifacts.get("script") or {}).get("sections") or []
    manifest_assets = (artifacts.get("asset_manifest") or {}).get("assets") or []

    def scene_key(value: Any) -> str:
        # 0 is a legitimate scene id — only None/absent collapses to "".
        return str(value) if value is not None else ""

    assets_by_scene: dict[str, list[dict]] = {}
    for asset in manifest_assets:
        if not isinstance(asset, dict):
            continue
        entry = _asset_entry(project_dir, asset)
        assets_by_scene.setdefault(scene_key(entry.get("scene_id")), []).append(entry)

    # A scene is "generating" if its most recent top-level event is an
    # unfinished start. Nested (depth>0) provider events inside a selector
    # call are skipped — the outer call's finish is the real completion.
    generating: dict[str, dict] = {}
    for ev in events:
        sid = ev.get("scene_id")
        if sid is None or ev.get("depth"):
            continue
        sid = scene_key(sid)
        if ev.get("event") == "start":
            generating[sid] = ev
        elif ev.get("event") in ("finish", "error"):
            generating.pop(sid, None)

    cards = []
    for scene in scene_plan["scenes"]:
        if not isinstance(scene, dict):
            continue
        sid = scene_key(scene.get("id"))
        section = _find_script_section(scene, sections)
        scene_assets = assets_by_scene.get(sid, [])
        visuals = [a for a in scene_assets if a["type"] in ("image", "video", "diagram", "animation")]
        audio = [a for a in scene_assets if a["type"] in ("audio", "narration", "music", "sfx")]
        # Only files that can actually be shown (raster/video) are takes; a
        # bespoke composition asset (.tsx animation) is real but not showable.
        renderable = [a for a in visuals if a.get("renderable")]
        # A raster/video asset whose FILE is missing stays as a "file missing"
        # indicator. But an asset that EXISTS yet can't be shown (a .tsx atelier
        # composition) is dropped — it falls back to a per-scene snapshot.
        missing = [a for a in visuals if not a.get("exists") and a["type"] in ("image", "video", "diagram")]
        active_visual = (
            renderable[-1] if renderable
            else missing[-1] if missing
            else _find_scene_snapshot(project_dir, sid)
        )
        cards.append({
            "id": sid,
            "type": scene.get("type"),
            "description": scene.get("description"),
            "start_seconds": scene.get("start_seconds"),
            "end_seconds": scene.get("end_seconds"),
            "duration_seconds": (
                max(0, (scene.get("end_seconds") or 0) - (scene.get("start_seconds") or 0))
                if scene.get("end_seconds") is not None and scene.get("start_seconds") is not None
                else None
            ),
            "hero_moment": bool(scene.get("hero_moment")),
            "shot_language": scene.get("shot_language"),
            "shot_intent": scene.get("shot_intent"),
            "framing": scene.get("framing"),
            "movement": scene.get("movement"),
            "narration": (section or {}).get("text"),
            "section_label": (section or {}).get("label"),
            "required_assets": scene.get("required_assets") or [],
            "visual": active_visual,
            "takes": renderable,
            "audio": audio,
            "generating": generating.get(sid) is not None,
            "generating_tool": (generating.get(sid) or {}).get("tool"),
        })

    total = scene_plan.get("metadata", {}).get("total_duration_seconds")
    if total is None and cards:
        ends = [c["end_seconds"] for c in cards if c["end_seconds"] is not None]
        total = max(ends) if ends else None
    return {
        "scenes": cards,
        "total_duration_seconds": total,
        "style_playbook": scene_plan.get("style_playbook"),
    }


# ---------------------------------------------------------------------------
# Source / reference media (bootstrap intake)
# ---------------------------------------------------------------------------

def _first_image_under(project_dir: Path, *rel_dirs: str) -> Optional[str]:
    for rel_dir in rel_dirs:
        d = project_dir / rel_dir
        if not d.is_dir():
            continue
        try:
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in MEDIA_IMAGE_EXT:
                    return _rel(project_dir, f)
        except OSError:
            continue
    return None


def _first_browser_video(project_dir: Path, *, skip: Optional[str] = None) -> Optional[str]:
    """Best project-local MP4/WebM for in-browser preview (skips raw source)."""
    skip_norm = (skip or "").replace("\\", "/")
    for rel in _PREVIEW_VIDEO_PRIORITY:
        if skip_norm and rel.replace("\\", "/") == skip_norm:
            continue
        candidate = project_dir / Path(rel)
        if candidate.is_file():
            return rel.replace("\\", "/")

    vid_dir = project_dir / "assets" / "video"
    if not vid_dir.is_dir():
        return None
    trim_candidates: list[str] = []
    other: list[str] = []
    try:
        for f in sorted(vid_dir.iterdir()):
            if not f.is_file() or f.suffix.lower() not in BROWSER_VIDEO_EXT:
                continue
            rel = _rel(project_dir, f)
            rel_norm = rel.replace("\\", "/")
            if skip_norm and rel_norm == skip_norm:
                continue
            name = f.name.lower()
            if name.startswith("trim") or name.endswith("_preview.mp4"):
                trim_candidates.append(rel_norm)
            else:
                other.append(rel_norm)
    except OSError:
        return None
    if trim_candidates:
        return trim_candidates[0]
    return other[0] if other else None


def _codec_browser_playable(codec: Any) -> bool:
    if codec is None or codec == "":
        return True
    name = str(codec).lower().strip()
    if name in _NON_BROWSER_VIDEO_CODECS:
        return False
    if name in _BROWSER_VIDEO_CODECS or name.startswith("h264") or name.startswith("avc"):
        return True
    return name not in _NON_BROWSER_VIDEO_CODECS


def _is_browser_playable_video(ext: str, codec: Any) -> bool:
    if ext not in BROWSER_VIDEO_EXT:
        return False
    return _codec_browser_playable(codec)


def _build_source_media(
    project_dir: Path,
    meta_json: dict[str, Any],
    artifacts: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """Resolve bootstrap source/reference footage for the board media panel."""
    pi = meta_json.get("production_inputs") or {}
    kind = "source"
    rel = str(pi.get("source_media_path") or "").strip()

    if not rel:
        ref = str(pi.get("reference_media_path") or "").strip()
        if ref:
            rel = ref
            kind = "reference"

    review = artifacts.get("source_media_review") or {}
    if not rel:
        files = review.get("files") or []
        if files:
            raw = str(files[0].get("path") or "")
            resolved = _resolve_asset_path(project_dir, raw)
            if resolved is not None:
                rel = _rel(project_dir, resolved)

    if not rel:
        return None

    resolved = _resolve_asset_path(project_dir, rel)
    exists = resolved is not None
    ext = Path(rel).suffix.lower()

    probe: dict[str, Any] = {}
    rel_name = Path(rel).name
    rel_norm = rel.replace("\\", "/")
    for entry in review.get("files") or []:
        raw = str(entry.get("path") or "").replace("\\", "/")
        if raw.endswith(rel_name) or rel_norm in raw or raw.endswith(rel_norm):
            probe = entry.get("technical_probe") or {}
            break

    codec = probe.get("codec")
    playable = exists and _is_browser_playable_video(ext, codec)

    poster = _first_image_under(project_dir, "assets/images", "assets/frames")
    preview_path = None if playable else _first_browser_video(project_dir, skip=rel_norm)
    playback_path = rel_norm if playable else preview_path

    summary = str(review.get("summary") or "").strip()
    if not summary:
        files = review.get("files") or []
        if files:
            summary = str(files[0].get("content_summary") or "").strip()

    return {
        "kind": kind,
        "path": rel_norm,
        "exists": exists,
        "playable": playable,
        "playback_path": playback_path,
        "poster": poster,
        "preview_path": preview_path,
        "summary": summary[:500],
        "duration_seconds": probe.get("duration_seconds"),
        "resolution": probe.get("resolution"),
        "format": ext.lstrip(".") or None,
        "codec": codec,
    }


def source_media_summary(project_dir: Path) -> Optional[dict[str, Any]]:
    """Public helper — source/reference media for settings API and board."""
    meta_json = _read_json(project_dir / "meta.json") or {}
    artifacts: dict[str, Any] = {}
    review = _read_json(project_dir / "artifacts" / "source_media_review.json")
    if review:
        artifacts["source_media_review"] = review
    return _build_source_media(project_dir, meta_json, artifacts)


# ---------------------------------------------------------------------------
# Media discovery
# ---------------------------------------------------------------------------

def _scan_media(project_dir: Path) -> dict[str, list[dict]]:
    """Discovered media files (renders, loose assets, snapshots)."""
    renders: list[dict] = []
    snapshots: list[dict] = []
    music: list[dict] = []

    renders_dir = project_dir / "renders"
    if renders_dir.is_dir():
        for f in sorted(renders_dir.iterdir()):
            if f.suffix.lower() in MEDIA_VIDEO_EXT and f.is_file():
                renders.append({"path": _rel(project_dir, f), "size": f.stat().st_size,
                                "mtime": f.stat().st_mtime})
    # Atelier heuristic: deliverables at project root.
    for f in sorted(project_dir.glob("*.mp4")):
        renders.append({"path": _rel(project_dir, f), "size": f.stat().st_size,
                        "mtime": f.stat().st_mtime, "at_root": True})
    for f in sorted(project_dir.glob("*.mp3")):
        music.append({"path": _rel(project_dir, f), "at_root": True})
    music_dir = project_dir / "assets" / "music"
    if music_dir.is_dir():
        for f in sorted(music_dir.iterdir()):
            if f.suffix.lower() in MEDIA_AUDIO_EXT:
                music.append({"path": _rel(project_dir, f)})

    for dirname in ("snapshots", "verify"):
        d = project_dir / dirname
        if d.is_dir():
            for f in sorted(d.iterdir()):
                if f.suffix.lower() in MEDIA_IMAGE_EXT and f.is_file():
                    snapshots.append({"path": _rel(project_dir, f)})

    renders.sort(key=lambda r: r.get("mtime", 0), reverse=True)
    return {"renders": renders, "snapshots": snapshots, "music": music}


def _find_poster(project_dir: Path, state: dict) -> Optional[str]:
    """Best poster for the library card (image path, or a video path —
    the /thumb endpoint extracts a frame from videos)."""
    board = state.get("storyboard") or {}
    for card in board.get("scenes", []):
        visual = card.get("visual")
        if visual and visual.get("exists") and visual.get("type") == "image":
            return visual["path"]
    for snap in (state.get("media") or {}).get("snapshots", []):
        return snap["path"]
    # Common image homes, in order of how representative they usually are.
    for rel_dir in ("assets/images", "assets/frames", "exports", "assets", "."):
        d = (project_dir / rel_dir) if rel_dir != "." else project_dir
        if not d.is_dir():
            continue
        try:
            for f in sorted(d.iterdir()):
                if f.is_file() and f.suffix.lower() in MEDIA_IMAGE_EXT:
                    return _rel(project_dir, f)
        except OSError:
            continue
    # Last resort: the newest render — /thumb extracts a poster frame.
    renders = (state.get("media") or {}).get("renders", [])
    if renders:
        return renders[0]["path"]
    return None


def _media_kind_from_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in MEDIA_IMAGE_EXT:
        return "image"
    if ext in MEDIA_VIDEO_EXT:
        return "video"
    if ext in MEDIA_AUDIO_EXT:
        return "audio"
    return "file"


def _normalize_media_entry(
    project_dir: Path,
    raw_path: str,
    *,
    label: Optional[str] = None,
    source_artifact: Optional[str] = None,
    media_type: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """Resolve a project-relative media path for stage output panels."""
    if not raw_path or not isinstance(raw_path, str):
        return None
    stripped = raw_path.strip()
    if not stripped:
        return None
    if stripped.startswith(("http://", "https://")):
        return {
            "path": stripped,
            "type": "url",
            "exists": True,
            "renderable": False,
            "label": label or stripped,
            "source_artifact": source_artifact,
        }

    resolved = _resolve_asset_path(project_dir, stripped)
    in_project = False
    if resolved is not None:
        try:
            resolved.resolve().relative_to(Path(project_dir).resolve())
            in_project = True
        except (ValueError, OSError):
            resolved = None
    file_path = resolved if resolved is not None else (project_dir / stripped)
    exists = resolved is not None
    kind = media_type or _media_kind_from_path(file_path)
    ext = file_path.suffix.lower()
    renderable = exists and ext in (MEDIA_IMAGE_EXT | MEDIA_VIDEO_EXT)
    return {
        "path": _rel(project_dir, file_path) if exists else stripped.replace("\\", "/"),
        "type": kind,
        "exists": exists,
        "renderable": renderable,
        "label": label or file_path.name,
        "source_artifact": source_artifact,
    }


def _media_from_artifact(
    project_dir: Path,
    artifact_name: str,
    artifact: dict[str, Any],
) -> list[dict[str, Any]]:
    """Extract servable media paths declared inside one artifact."""
    items: list[dict[str, Any]] = []

    if artifact_name == "asset_manifest":
        for asset in artifact.get("assets") or []:
            if not isinstance(asset, dict):
                continue
            entry = _asset_entry(project_dir, asset)
            entry["label"] = (
                asset.get("id")
                or asset.get("scene_id")
                or (entry.get("path") or "").split("/")[-1]
            )
            entry["source_artifact"] = artifact_name
            items.append(entry)
        return items

    if artifact_name == "render_report":
        for idx, output in enumerate(artifact.get("outputs") or []):
            if not isinstance(output, dict):
                continue
            entry = _normalize_media_entry(
                project_dir,
                str(output.get("path") or ""),
                label=(output.get("path") or "").split("/")[-1] or f"output {idx + 1}",
                source_artifact=artifact_name,
                media_type="video",
            )
            if entry:
                items.append(entry)
        return items

    if artifact_name == "video_analysis_brief":
        source = artifact.get("source") or {}
        if isinstance(source, dict):
            entry = _normalize_media_entry(
                project_dir,
                str(source.get("local_path") or ""),
                label=source.get("title") or "reference",
                source_artifact=artifact_name,
            )
            if entry:
                items.append(entry)
        return items

    if artifact_name == "source_media_review":
        for idx, file_entry in enumerate(artifact.get("files") or []):
            if not isinstance(file_entry, dict):
                continue
            entry = _normalize_media_entry(
                project_dir,
                str(file_entry.get("path") or ""),
                label=file_entry.get("label") or file_entry.get("role") or f"file {idx + 1}",
                source_artifact=artifact_name,
            )
            if entry:
                items.append(entry)
        return items

    if artifact_name == "edit_decisions":
        for key in ("subtitles_path", "subtitle_path", "srt_path"):
            entry = _normalize_media_entry(
                project_dir,
                str(artifact.get(key) or ""),
                label="subtitles",
                source_artifact=artifact_name,
            )
            if entry:
                items.append(entry)
        return items

    # Generic walk for path-like fields on uncommon artifacts.
    path_key = re.compile(r"(^path$|_path$|^local_path$|^output_path$)", re.I)

    def walk(value: Any, label: str = "") -> None:
        if isinstance(value, dict):
            for k, v in value.items():
                if isinstance(v, str) and path_key.search(k):
                    entry = _normalize_media_entry(
                        project_dir,
                        v,
                        label=label or v.split("/")[-1],
                        source_artifact=artifact_name,
                    )
                    if entry:
                        items.append(entry)
                elif isinstance(v, (dict, list)):
                    walk(v, label)
        elif isinstance(value, list):
            for i, item in enumerate(value):
                walk(item, label or f"item {i + 1}")

    walk(artifact)
    return items


def _stage_produces(stage: dict[str, Any]) -> list[str]:
    declared = [
        str(name)
        for name in (stage.get("produces") or [])
        if isinstance(name, str) and name
    ]
    if declared:
        return declared
    fallback = _FALLBACK_STAGE_PRODUCES.get(stage.get("name") or "")
    return list(fallback or [])


def _build_project_summary(
    project_dir: Path,
    stages: list[dict[str, Any]],
    artifacts: dict[str, dict],
    media: dict[str, list],
    checkpoints: dict[str, dict[str, Any]],
    pipeline_meta: dict[str, Any],
) -> dict[str, Any]:
    """Project-level artifact + media rollup for the board summary panel."""
    provenance = _build_artifact_provenance(stages, checkpoints, pipeline_meta)
    artifact_stages: dict[str, list[str]] = dict(provenance)
    ordered_names: list[str] = []
    seen_names: set[str] = set()

    for stage in stages:
        for art_name in stage.get("outputs") or _stage_produces(stage):
            if art_name == "decision_log" or art_name in seen_names:
                continue
            seen_names.add(art_name)
            ordered_names.append(art_name)

    for art_name in sorted(artifacts.keys()):
        if art_name == "decision_log" or art_name in seen_names:
            continue
        seen_names.add(art_name)
        ordered_names.append(art_name)

    artifact_list = [
        {
            "name": name,
            "path": f"artifacts/{ARTIFACT_FILES.get(name, f'{name}.json')}",
            "present": name in artifacts and isinstance(artifacts.get(name), dict),
            "stages": artifact_stages.get(name, []),
        }
        for name in ordered_names
    ]

    by_stage: list[dict[str, Any]] = []
    claimed: set[str] = set()
    for stage in stages:
        stage_name = stage.get("name") or ""
        if not stage_name:
            continue
        stage_items = [
            entry for entry in artifact_list
            if entry["name"] in (stage.get("outputs") or [])
            or (
                entry["name"] not in claimed
                and stage_name in (entry.get("stages") or [])
                and len(entry.get("stages") or []) == 1
            )
        ]
        for entry in stage_items:
            claimed.add(entry["name"])
        if stage_items:
            by_stage.append({"stage": stage_name, "artifacts": stage_items})

    orphan_items = [entry for entry in artifact_list if entry["name"] not in claimed]
    if orphan_items:
        by_stage.append({"stage": "_orphan", "artifacts": orphan_items})

    media_items: list[dict[str, Any]] = []
    seen_paths: set[str] = set()

    def add_media(entry: Optional[dict[str, Any]]) -> None:
        if not entry:
            return
        path = entry.get("path")
        if not path or path in seen_paths:
            return
        seen_paths.add(path)
        media_items.append(entry)

    for art_name, data in artifacts.items():
        if isinstance(data, dict):
            for entry in _media_from_artifact(project_dir, art_name, data):
                add_media(entry)

    for render in media.get("renders") or []:
        path = render.get("path")
        if not path:
            continue
        add_media({
            "path": path,
            "type": "video",
            "exists": True,
            "renderable": True,
            "label": str(path).split("/")[-1],
            "source_artifact": "render_report",
        })

    for snap in media.get("snapshots") or []:
        path = snap.get("path")
        if not path:
            continue
        add_media({
            "path": path,
            "type": "image",
            "exists": True,
            "renderable": True,
            "label": str(path).split("/")[-1],
            "snapshot": True,
        })

    for track in media.get("music") or []:
        path = track.get("path")
        if not path:
            continue
        add_media({
            "path": path,
            "type": "audio",
            "exists": True,
            "renderable": False,
            "label": str(path).split("/")[-1],
        })

    for rel_dir, kind in (
        ("assets/images", "image"),
        ("assets/video", "video"),
        ("assets/audio", "audio"),
        ("assets/music", "audio"),
    ):
        d = project_dir / rel_dir
        if not d.is_dir():
            continue
        try:
            for f in sorted(d.iterdir()):
                if not f.is_file():
                    continue
                add_media(_normalize_media_entry(
                    project_dir,
                    _rel(project_dir, f),
                    label=f.name,
                    media_type=kind,
                ))
        except OSError:
            continue

    present = sum(1 for item in artifact_list if item["present"])
    completed = sum(
        1 for stage in stages
        if stage.get("status") == "completed" and not stage.get("undeclared")
    )
    total_stages = sum(1 for stage in stages if not stage.get("undeclared"))

    return {
        "artifacts": artifact_list,
        "by_stage": by_stage,
        "media": media_items,
        "counts": {
            "artifacts_present": present,
            "artifacts_total": len(artifact_list),
            "media": len(media_items),
            "stages_completed": completed,
            "stages_total": total_stages,
        },
    }


def _last_activity(project_dir: Path) -> float:
    """Most recent mtime among state-bearing files (bounded scan)."""
    latest = 0.0
    try:
        candidates = list(project_dir.glob("checkpoint_*.json"))
        candidates.append(project_dir / "events.jsonl")
        art = project_dir / "artifacts"
        if art.is_dir():
            candidates.extend(art.glob("*.json"))
        for p in candidates:
            try:
                latest = max(latest, p.stat().st_mtime)
            except OSError:
                continue
    except OSError:
        pass
    return latest


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_board_state(project_dir: Path) -> dict[str, Any]:
    """Full BoardState for one project. Never raises."""
    project_dir = Path(project_dir)
    project_id = project_dir.name

    marker = _read_json(project_dir / "project.json") or {}
    meta_json = _read_json(project_dir / "meta.json") or {}

    checkpoints = _collect_checkpoints(project_dir)
    history = _collect_history(project_dir)

    pipeline_type = marker.get("pipeline_type")
    if not pipeline_type:
        for cp in checkpoints.values():
            pt = cp.get("pipeline_type")
            if pt and pt != "unknown":
                pipeline_type = pt
                break
    pipeline_meta = _load_pipeline_meta(pipeline_type)

    artifacts = _collect_artifacts(project_dir, checkpoints)
    events = read_events(project_dir, limit=250)
    storyboard = _build_storyboard(project_dir, artifacts, events)
    media = _scan_media(project_dir)

    stages = _build_stage_rail(pipeline_meta, checkpoints, history)
    artifact_keys = set(artifacts.keys())
    for stage_entry in stages:
        cp = checkpoints.get(stage_entry["name"])
        stage_entry["outputs"] = _resolve_stage_outputs(stage_entry, cp, artifact_keys)

    # Cost: latest checkpoint snapshot wins; fall back to manifest total.
    cost = None
    for cp in sorted(checkpoints.values(), key=lambda c: c.get("_mtime", 0), reverse=True):
        if cp.get("cost_snapshot"):
            cost = cp["cost_snapshot"]
            break
    if cost is None:
        total = (artifacts.get("asset_manifest") or {}).get("total_cost_usd")
        if total is not None:
            cost = {"total_spent_usd": total}

    import time
    last_activity = _last_activity(project_dir)
    now = time.time()

    # Stall detection: an in_progress stage that stopped writing anything.
    for stage_entry in stages:
        if (
            stage_entry["status"] == "in_progress"
            and last_activity
            and (now - last_activity) > STALL_WINDOW_SECONDS
        ):
            stage_entry["stalled"] = True
            stage_entry["stalled_minutes"] = int((now - last_activity) / 60)

    project_summary = _build_project_summary(
        project_dir, stages, artifacts, media, checkpoints, pipeline_meta,
    )

    state: dict[str, Any] = {
        "project_id": project_id,
        "title": marker.get("title") or meta_json.get("name") or project_id.replace("-", " ").title(),
        "pipeline": pipeline_meta,
        "style_playbook": marker.get("style_playbook"),
        "created_at": marker.get("created_at"),
        "has_marker": bool(marker),
        "has_pipeline_state": bool(checkpoints),
        "stages": stages,
        "artifacts": artifacts,
        "project_summary": project_summary,
        "storyboard": storyboard,
        "media": media,
        "source_media": _build_source_media(project_dir, meta_json, artifacts),
        "events": events,
        "cost": cost,
        "last_activity": last_activity,
        "live": bool(last_activity and (now - last_activity) < LIVE_WINDOW_SECONDS),
    }
    state["poster"] = _find_poster(project_dir, state)
    return state


def summarize_project(project_dir: Path) -> dict[str, Any]:
    """Cheap library-card summary (no full artifact parse of big files)."""
    state = load_board_state(project_dir)
    meta_json = _read_json(project_dir / "meta.json") or {}
    pi = meta_json.get("production_inputs") or {}
    has_reference = bool(
        str(pi.get("reference_url") or "").strip()
        or str(pi.get("reference_media_path") or "").strip()
    ) or meta_json.get("intake_mode") == "reference"
    active = next((s for s in state["stages"] if s["status"] in ("in_progress", "awaiting_human")), None)
    done = [s for s in state["stages"] if s["status"] == "completed"]
    return {
        "project_id": state["project_id"],
        "title": state["title"],
        "pipeline_type": state["pipeline"]["pipeline_type"],
        "pipeline_label_zh": state["pipeline"].get("label_zh") or pipeline_label_zh(
            state["pipeline"]["pipeline_type"]
        ),
        "has_reference": has_reference,
        "has_pipeline_state": state["has_pipeline_state"],
        "poster": state["poster"],
        "live": state["live"],
        "last_activity": state["last_activity"],
        "active_stage": active["name"] if active else None,
        "awaiting_human": bool(active and active["status"] == "awaiting_human"),
        "stage_states": [
            {"name": s["name"], "status": s["status"]}
            for s in state["stages"] if not s.get("undeclared")
        ],
        "completed_count": len(done),
        "render_count": len(state["media"]["renders"]),
        "scene_count": len((state["storyboard"] or {}).get("scenes", [])),
    }


def list_projects(projects_dir: Optional[Path] = None) -> list[dict[str, Any]]:
    """Library view: every project directory, live-first then recency."""
    root = Path(projects_dir) if projects_dir else PROJECTS_DIR
    if not root.is_dir():
        return []
    summaries = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        if _is_demo_project(entry):
            continue
        try:
            summaries.append(summarize_project(entry))
        except Exception:
            summaries.append({
                "project_id": entry.name,
                "title": entry.name.replace("-", " ").title(),
                "pipeline_type": "unknown",
                "pipeline_label_zh": "未知",
                "has_pipeline_state": False,
                "poster": None,
                "live": False,
                "last_activity": 0,
                "active_stage": None,
                "awaiting_human": False,
                "stage_states": [],
                "completed_count": 0,
                "render_count": 0,
                "scene_count": 0,
                "error": "unreadable",
            })
    summaries.sort(key=lambda s: (not s["live"], -(s["last_activity"] or 0)))
    return summaries
