"""Project status introspection — single entry point for agents.

Agents MUST use this module (or Backlot) to discover pipeline state, artifact
paths, and director skills. Do NOT use shell directory listings (dir, ls,
Get-ChildItem) to explore project layout.

See AGENT_GUIDE.md → Agent Introspection (HARD RULE).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

from lib.checkpoint import (
    CANONICAL_STAGE_ARTIFACTS,
    get_completed_stages,
    get_next_stage,
    get_pipeline_stages,
)
from lib.events import read_events
from lib.paths import PROJECTS_DIR, REPO_ROOT
from lib.pipeline_loader import get_stage_skill, load_pipeline_readonly
from lib.production_audit import audit_project


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def resolve_project_dir(project_id: str, *, projects_dir: Optional[Path] = None) -> Path:
    root = projects_dir or PROJECTS_DIR
    path = root / project_id
    if not path.is_dir():
        raise FileNotFoundError(f"Project not found: {path}")
    return path


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_checkpoint_raw(project_dir: Path, stage: str) -> Optional[dict[str, Any]]:
    return _load_json(project_dir / f"checkpoint_{stage}.json")


def _artifact_paths(project_dir: Path) -> list[dict[str, Any]]:
    artifacts_dir = project_dir / "artifacts"
    entries: list[dict[str, Any]] = []
    if not artifacts_dir.is_dir():
        return entries
    for path in sorted(artifacts_dir.glob("*.json")):
        entries.append({
            "name": path.stem,
            "path": _display_path(path),
            "exists": True,
            "bytes": path.stat().st_size,
        })
    return entries


def _render_paths(project_dir: Path) -> list[dict[str, Any]]:
    renders_dir = project_dir / "renders"
    if not renders_dir.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(renders_dir.glob("*")):
        if path.is_file():
            out.append({
                "name": path.name,
                "path": _display_path(path),
                "bytes": path.stat().st_size,
            })
    return out


def _tool_trace_summary(project_dir: Path) -> dict[str, Any]:
    events = read_events(project_dir)
    finished: list[str] = []
    started: list[str] = []
    for event in events:
        tool = event.get("tool")
        if not tool:
            continue
        if event.get("event") == "finish" and event.get("success"):
            finished.append(tool)
        elif event.get("event") == "start":
            started.append(tool)
    return {
        "event_count": len(events),
        "tools_started": sorted(set(started)),
        "tools_finished_ok": sorted(set(finished)),
    }


def _stage_rows(
    project_dir: Path,
    project_id: str,
    pipeline_type: str,
    *,
    projects_dir: Path,
) -> list[dict[str, Any]]:
    order = get_pipeline_stages(pipeline_type)
    rows: list[dict[str, Any]] = []
    for stage in order:
        cp = _read_checkpoint_raw(project_dir, stage)
        artifact_name = CANONICAL_STAGE_ARTIFACTS.get(stage)
        artifact_path = (
            project_dir / "artifacts" / f"{artifact_name}.json"
            if artifact_name
            else None
        )
        rows.append({
            "stage": stage,
            "status": (cp or {}).get("status", "pending"),
            "human_approved": (cp or {}).get("human_approved"),
            "timestamp": (cp or {}).get("timestamp"),
            "canonical_artifact": artifact_name,
            "artifact_exists": bool(artifact_path and artifact_path.is_file()),
        })
    return rows


def build_project_status(
    project_id: str,
    *,
    projects_dir: Optional[Path] = None,
    include_audit: bool = False,
) -> dict[str, Any]:
    """Structured project snapshot for agents and CLI."""
    root = projects_dir or PROJECTS_DIR
    project_dir = resolve_project_dir(project_id, projects_dir=root)
    marker = _load_json(project_dir / "project.json") or {}
    meta = _load_json(project_dir / "meta.json") or {}
    pipeline_type = marker.get("pipeline_type") or "unknown"

    try:
        manifest = load_pipeline_readonly(pipeline_type)
    except Exception:
        manifest = None

    next_stage = get_next_stage(root, project_id, pipeline_type)
    completed = get_completed_stages(root, project_id, pipeline_type)

    director_skill: Optional[str] = None
    if next_stage and manifest:
        skill = get_stage_skill(manifest, next_stage)
        if skill:
            director_skill = f"skills/{skill}.md"

    status: dict[str, Any] = {
        "project_id": project_id,
        "title": marker.get("title"),
        "pipeline_type": pipeline_type,
        "style_playbook": marker.get("style_playbook"),
        "project_dir": _display_path(project_dir),
        "completed_stages": completed,
        "next_stage": next_stage,
        "director_skill": director_skill,
        "stages": _stage_rows(project_dir, project_id, pipeline_type, projects_dir=root),
        "artifacts": _artifact_paths(project_dir),
        "renders": _render_paths(project_dir),
        "tool_trace": _tool_trace_summary(project_dir),
        "intake": {
            "mode": meta.get("intake_mode"),
            "production_inputs": meta.get("production_inputs"),
        },
        "agent_commands": {
            "status": f"python -m lib.project_status {project_id}",
            "status_json": f"python -m lib.project_status {project_id} --json",
            "audit": f"python -m lib.project_status {project_id} --audit",
        },
    }

    if include_audit:
        status["audit_findings"] = audit_project(project_dir, pipeline_type=pipeline_type)

    return status


def format_human(status: dict[str, Any]) -> str:
    lines = [
        f"Project: {status.get('project_id')} ({status.get('title') or 'untitled'})",
        f"Pipeline: {status.get('pipeline_type')}",
        f"Directory: {status.get('project_dir')}",
        f"Completed: {', '.join(status.get('completed_stages') or []) or '(none)'}",
        f"Next stage: {status.get('next_stage') or '(done)'}",
    ]
    if status.get("director_skill"):
        lines.append(f"Read next: {status['director_skill']}")
    lines.append("")
    lines.append("Stages:")
    for row in status.get("stages") or []:
        gate = ""
        if row.get("human_approved") is True:
            gate = " [approved]"
        elif row.get("human_approved") is False:
            gate = " [awaiting approval]"
        art = ""
        if row.get("canonical_artifact"):
            mark = "✓" if row.get("artifact_exists") else "✗"
            art = f"  artifact:{row['canonical_artifact']} {mark}"
        lines.append(f"  - {row['stage']}: {row['status']}{gate}{art}")
    trace = status.get("tool_trace") or {}
    if trace.get("event_count"):
        lines.append("")
        lines.append(
            f"Tool events: {trace['event_count']}  "
            f"finished: {', '.join(trace.get('tools_finished_ok') or []) or '(none)'}"
        )
    renders = status.get("renders") or []
    if renders:
        lines.append("")
        lines.append("Renders:")
        for r in renders:
            lines.append(f"  - {r['path']}")
    if status.get("audit_findings"):
        lines.append("")
        lines.append("Audit findings:")
        for finding in status["audit_findings"]:
            lines.append(f"  [{finding.get('severity')}] {finding.get('code')}: {finding.get('message')}")
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="OpenMontage project status — preferred agent introspection entry point",
    )
    parser.add_argument("project_id", help="Project id under projects/")
    parser.add_argument("--json", action="store_true", help="Emit JSON (default)")
    parser.add_argument("--human", action="store_true", help="Emit human-readable text")
    parser.add_argument("--audit", action="store_true", help="Include production_audit findings")
    args = parser.parse_args(argv)

    try:
        status = build_project_status(args.project_id, include_audit=args.audit)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.human:
        print(format_human(status))
    else:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
