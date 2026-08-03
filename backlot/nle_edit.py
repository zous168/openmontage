"""NLE interactive editing — draft state + governed apply for Backlot.

拖拽只改草稿（projects/<id>/renders/.nle_draft.json，非 artifacts，不违反
AGENT_GUIDE Artifact Persistence HARD RULE）；「应用编辑」= 用户在 UI 上的
人类确认 → 通过 lib.checkpoint.write_checkpoint + lib.decision_log.
append_decisions 合法落盘，decision_log 留下可审计痕迹。
"""

from __future__ import annotations

import copy
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Optional

from lib.paths import PROJECTS_DIR

DRAFT_FILENAME = ".nle_draft.json"


def _read_json(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _sha256_of(path: Path) -> str:
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _draft_path(project_dir: Path) -> Path:
    return project_dir / "renders" / DRAFT_FILENAME


def _canonical_edit(project_dir: Path) -> dict[str, Any]:
    edit = _read_json(project_dir / "artifacts" / "edit_decisions.json")
    if not edit:
        raise ValueError("edit_decisions 工件不存在")
    return edit


def write_draft(
    project_dir: Path,
    cuts: list[dict[str, Any]],
    overlays: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Persist an editing draft (non-artifact state) for live preview."""
    edit_path = project_dir / "artifacts" / "edit_decisions.json"
    draft = {
        "base_sha256": _sha256_of(edit_path),
        "updated_at": time.time(),
        "cuts": cuts,
        "overlays": overlays,
    }
    (project_dir / "renders").mkdir(parents=True, exist_ok=True)
    _draft_path(project_dir).write_text(
        json.dumps(draft, ensure_ascii=False), encoding="utf-8",
    )
    return {"ok": True, "duration_seconds": _draft_duration_seconds(draft)}


def read_draft_props(project_dir: Path) -> dict[str, Any]:
    """Props for the preview iframe: draft-on-top-of-canonical composition.

    Returns {"props": <normalized composition props> | None, "duration_seconds": n}.
    Paths are relativized against the project dir (same _prepare_remotion_props
    pass the real render uses) so the preview iframe's staticFile() requests
    resolve against the project directory served via --public-dir.
    """
    from lib.composition_timeline import composition_duration_seconds, normalize_composition_props

    edit = _canonical_edit(project_dir)
    draft = _read_json(_draft_path(project_dir))
    if draft and draft.get("base_sha256") == _sha256_of(
        project_dir / "artifacts" / "edit_decisions.json"
    ):
        merged = copy.deepcopy(edit)
        merged["cuts"] = draft.get("cuts") or []
        if draft.get("overlays") is not None:
            merged["overlays"] = draft["overlays"]
        props = normalize_composition_props(merged)
        duration = _draft_duration_seconds(draft)
    else:
        # No (valid) draft: preview the canonical edit as-is.
        props = normalize_composition_props(edit)
        duration = composition_duration_seconds(edit)

    # Relativize media paths exactly like a real render so the preview
    # iframe can load them (see tools/video/video_compose._prepare_remotion_props).
    try:
        from tools.video.video_compose import VideoCompose

        stub = project_dir / "renders" / "preview_stub.mp4"
        stub.parent.mkdir(parents=True, exist_ok=True)
        VideoCompose()._prepare_remotion_props(props, stub.resolve())
    except (ValueError, ImportError):
        pass  # keep raw paths; preview may still show captions/overlays

    return {"props": props, "duration_seconds": duration}


def _draft_duration_seconds(draft: dict[str, Any]) -> float:
    cuts = draft.get("cuts") or []
    if not cuts:
        return 0.0  # match composition_duration_seconds()'s empty-cuts semantics
    last_end = max((float(c.get("out_seconds") or 0) for c in cuts), default=0.0)
    return last_end + 1.0


class DraftStaleError(ValueError):
    """Raised when the canonical edit_decisions changed after the draft was made."""


def apply_draft(
    project_dir: Path,
    cuts: Optional[list[dict[str, Any]]] = None,
    overlays: Optional[list[dict[str, Any]]] = None,
    decision_note: str = "",
) -> dict[str, Any]:
    """Apply the user-confirmed draft through the governed artifact APIs.

    Human confirmation is the UI "应用编辑" button click: edit stage is
    written completed with human_approved=True and a decision_log entry
    (category "nle_edit") records the audit trail.

    The applied content is read from the persisted draft file, NOT trusted
    from the request body — the client can only apply exactly what it
    previewed.
    """
    from lib.checkpoint import write_checkpoint
    from lib.decision_log import append_decisions, suggest_next_decision_id
    from schemas.artifacts import validate_artifact

    project_id = project_dir.name
    edit_path = project_dir / "artifacts" / "edit_decisions.json"
    draft = _read_json(_draft_path(project_dir))
    if not draft:
        raise ValueError("无编辑草稿——请先在时间线上拖拽调整后再应用")

    if draft.get("base_sha256") != _sha256_of(edit_path):
        raise DraftStaleError(
            "编辑草稿已过期（edit_decisions 在拖拽期间被修改）。请重新拖拽后再应用。"
        )

    # Source of truth = the persisted draft file (request body is advisory).
    cuts = draft.get("cuts") or []
    overlays = draft.get("overlays")

    new_edit = copy.deepcopy(_canonical_edit(project_dir))
    new_edit["cuts"] = cuts
    if overlays is not None:
        new_edit["overlays"] = overlays

    # Schema gate: malformed data must not reach the artifact store.
    validate_artifact("edit_decisions", new_edit)

    write_checkpoint(
        PROJECTS_DIR,
        project_id,
        stage="edit",
        status="completed",
        artifacts={"edit_decisions": new_edit},
        human_approved=True,  # UI 按钮 = 人类确认
    )

    append_decisions(project_id, [
        {
            "decision_id": suggest_next_decision_id(project_dir, prefix="nle"),
            "stage": "edit",
            "category": "nle_edit",
            "subject": "Interactive timeline edit",
            "options_considered": [
                {
                    "option_id": "manual",
                    "label": "Backlot 时间线拖拽编辑",
                    "score": 1,
                    "reason": "用户在 NLE 时间线上手动调整 cuts",
                },
            ],
            "selected": "manual",
            "reason": decision_note or "用户在 Backlot NLE 时间线上确认了剪辑调整",
            "user_visible": True,
            "user_approved": True,  # UI「应用编辑」按钮 = 显式人工确认
        },
    ])

    _draft_path(project_dir).unlink(missing_ok=True)
    return {
        "ok": True,
        "cut_count": len(cuts),
        "duration_seconds": _draft_duration_seconds({"cuts": cuts}),
    }


def read_draft(project_dir: Path) -> dict[str, Any]:
    """Draft state for the board (restore after refresh)."""
    draft = _read_json(_draft_path(project_dir)) or {}
    return {
        "has_draft": bool(draft),
        "stale": bool(draft)
        and draft.get("base_sha256")
        != _sha256_of(project_dir / "artifacts" / "edit_decisions.json"),
        "cuts": draft.get("cuts") or [],
        "overlays": draft.get("overlays"),
        "updated_at": draft.get("updated_at"),
    }
