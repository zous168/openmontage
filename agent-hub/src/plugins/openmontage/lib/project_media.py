"""Resolve project media paths without LLM guessing.

Artifact contracts often store paths as ``projects/<id>/renders/final.mp4``
or project-relative ``renders/final.mp4`` / ``assets/audio/….srt``. Tools and
``om_registry`` must map those to real files under ``DATA_ROOT`` / the project
dir — not leave the agent to invent locations like ``renders/subtitles.srt``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional


_PATH_PARAM_KEYS = frozenset({
    "video_path",
    "subtitles_path",
    "subtitle_path",
    "srt_path",
    "thumbnail_path",
    "audio_path",
    "image_path",
    "output_path",
    "export_dir",
    "track_path",
    "reference_image_path",
    "reference_media_path",
})


def _roots(
    *,
    data_root: Path | None = None,
    projects_dir: Path | None = None,
) -> tuple[Path, Path]:
    from plugins.openmontage.lib.paths import DATA_ROOT, PROJECTS_DIR

    return (
        Path(data_root) if data_root is not None else Path(DATA_ROOT),
        Path(projects_dir) if projects_dir is not None else Path(PROJECTS_DIR),
    )


def _project_dir_for(
    project_id: str | None,
    project_dir: Path | None,
    projects_dir: Path,
) -> Path | None:
    if project_dir is not None:
        return Path(project_dir)
    if project_id:
        return projects_dir / str(project_id).strip()
    return None


def iter_media_path_candidates(
    raw: str | Path,
    *,
    project_id: str | None = None,
    project_dir: Path | None = None,
    data_root: Path | None = None,
    projects_dir: Path | None = None,
) -> Iterable[Path]:
    """Yield absolute-ish candidates for a contracted or relative media path."""
    data_root, projects_dir_r = _roots(data_root=data_root, projects_dir=projects_dir)
    text = str(raw or "").strip().replace("\\", "/")
    if not text:
        return

    seen: set[str] = set()

    def _emit(candidate: Path) -> Iterable[Path]:
        try:
            key = str(candidate)
        except Exception:
            return
        if key in seen:
            return
        seen.add(key)
        yield candidate

    p = Path(text).expanduser()
    yield from _emit(p)

    proj = _project_dir_for(project_id, project_dir, projects_dir_r)
    if proj is not None:
        yield from _emit(proj / text)

        parts = Path(text).parts
        if len(parts) >= 2 and parts[0] == "projects":
            # projects/<id>/renders/final.mp4 → <project_dir>/renders/final.mp4
            remainder = Path(*parts[2:]) if len(parts) > 2 else Path()
            if parts[1] == proj.name or project_id is None or parts[1] == project_id:
                if str(remainder):
                    yield from _emit(proj / remainder)

    # DATA_ROOT-relative: projects/<id>/renders/...
    yield from _emit(data_root / text)

    if proj is not None and not p.is_absolute():
        # bare renders/final.mp4 already covered; also try under projects_dir/<id>
        yield from _emit(projects_dir_r / proj.name / text)


def resolve_project_media_path(
    raw: str | Path | None,
    *,
    project_id: str | None = None,
    project_dir: Path | None = None,
    data_root: Path | None = None,
    projects_dir: Path | None = None,
    require_exists: bool = True,
) -> Optional[Path]:
    """Map a contract/relative path to a filesystem path.

    When ``require_exists`` is True, returns the first candidate that is a file
    (or directory for export_dir-like paths that already exist). When False,
    returns the preferred absolute location even if missing (for clearer errors).
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    candidates = list(
        iter_media_path_candidates(
            text,
            project_id=project_id,
            project_dir=project_dir,
            data_root=data_root,
            projects_dir=projects_dir,
        )
    )
    if not candidates:
        return None

    if require_exists:
        for c in candidates:
            try:
                if c.is_file() or c.is_dir():
                    return c.resolve()
            except OSError:
                continue
        return None

    # Prefer DATA_ROOT / projects/... form, else project_dir join, else raw.
    data_root, _ = _roots(data_root=data_root, projects_dir=projects_dir)
    proj = _project_dir_for(project_id, project_dir, _roots(projects_dir=projects_dir)[1])
    normalized = text.replace("\\", "/")
    if normalized.startswith("projects/"):
        return (data_root / normalized).resolve()
    if proj is not None and not Path(normalized).is_absolute():
        return (proj / normalized).resolve()
    return candidates[0].expanduser().resolve()


def list_subtitle_candidates(
    project_dir: Path,
    *,
    limit: int = 8,
) -> list[str]:
    """Known on-disk subtitle locations under a project (for error hints)."""
    root = Path(project_dir)
    patterns = (
        "assets/audio/*.srt",
        "assets/subtitles/*.srt",
        "assets/subtitles.srt",
        "assets/*.srt",
        "renders/*.srt",
    )
    found: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for hit in sorted(root.glob(pattern)):
            if not hit.is_file():
                continue
            rel = hit.relative_to(root).as_posix()
            if rel in seen:
                continue
            seen.add(rel)
            found.append(rel)
            if len(found) >= limit:
                return found
    return found


def rewrite_path_params(
    params: dict,
    *,
    project_id: str | None = None,
    project_dir: Path | None = None,
) -> dict:
    """Rewrite ``*_path`` / known path keys to absolute existing files when possible."""
    if not isinstance(params, dict) or not params:
        return params

    out = dict(params)
    for key, value in list(out.items()):
        if not isinstance(value, str) or not value.strip():
            continue
        if key not in _PATH_PARAM_KEYS and key != "path" and not str(key).endswith("_path"):
            continue
        # export_dir may not exist yet — only rewrite when we find an existing path,
        # or when require_exists=False for missing optional assets so tools see abs paths.
        existing = resolve_project_media_path(
            value,
            project_id=project_id,
            project_dir=project_dir,
            require_exists=True,
        )
        if existing is not None:
            out[key] = str(existing)
            continue
        # Keep clearer absolute form for missing optionals (subtitles/thumbnail).
        if key in ("subtitles_path", "subtitle_path", "srt_path", "thumbnail_path", "video_path"):
            preferred = resolve_project_media_path(
                value,
                project_id=project_id,
                project_dir=project_dir,
                require_exists=False,
            )
            if preferred is not None:
                out[key] = str(preferred)
    return out
