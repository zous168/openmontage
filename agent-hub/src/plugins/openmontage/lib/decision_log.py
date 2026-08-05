"""Decision log persistence — append-only API for agents.

Agents MUST NOT edit ``projects/<id>/decision_log.json`` with the editor or
shell redirects. Append decisions through ``append_decisions()`` or pass a
``decision_log`` artifact to ``write_checkpoint()`` — both validate schema and
merge append-only.

See AGENT_GUIDE.md → Artifact Persistence (HARD RULE).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

from plugins.openmontage.lib.paths import PROJECTS_DIR
from plugins.openmontage.schemas.artifacts import validate_artifact


def decision_key(decision: dict[str, Any]) -> str:
    return f"{decision.get('category') or 'decision'}::{decision.get('subject') or ''}"


def latest_decisions_by_key(decisions: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Current decision per (category, subject) — matches Backlot board.js."""
    current: dict[str, dict[str, Any]] = {}
    for decision in decisions:
        current[decision_key(decision)] = decision
    return current


def latest_decisions_for_stage(
    decisions: list[dict[str, Any]],
    stage: str,
) -> list[dict[str, Any]]:
    stage_decisions = [d for d in decisions if d.get("stage") == stage]
    by_key = latest_decisions_by_key(stage_decisions)
    return list(by_key.values())


def _log_path(project_dir: Path) -> Path:
    return project_dir / "decision_log.json"


def load_decision_log(project_dir: Path) -> dict[str, Any]:
    path = _log_path(project_dir)
    if not path.is_file():
        return {
            "version": "1.0",
            "project_id": project_dir.name,
            "decisions": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def suggest_next_decision_id(project_dir: Path, *, prefix: str = "d") -> str:
    log = load_decision_log(project_dir)
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    max_num = 0
    for decision in log.get("decisions") or []:
        match = pattern.match(str(decision.get("decision_id", "")))
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"{prefix}-{max_num + 1:03d}"


def append_decisions(
    project_id: str,
    decisions: list[dict[str, Any]],
    *,
    projects_dir: Optional[Path] = None,
) -> Path:
    """Validate and append decisions (skip duplicate decision_id)."""
    if not decisions:
        raise ValueError("decisions must be a non-empty list")

    root = projects_dir or PROJECTS_DIR
    project_dir = root / project_id
    if not project_dir.is_dir():
        raise FileNotFoundError(f"Project not found: {project_dir}")

    for decision in decisions:
        validate_artifact("decision_log", {
            "version": "1.0",
            "project_id": project_id,
            "decisions": [decision],
        })

    log = load_decision_log(project_dir)
    log["project_id"] = project_id
    existing_ids = {d["decision_id"] for d in log.get("decisions") or []}
    for decision in decisions:
        if decision["decision_id"] in existing_ids:
            continue
        log.setdefault("decisions", []).append(decision)

    path = _log_path(project_dir)
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Append validated decisions to a project decision_log",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    append_p = sub.add_parser("append", help="Append one or more decisions")
    append_p.add_argument("project_id")
    append_p.add_argument(
        "--file",
        required=True,
        help="JSON file with {\"decisions\": [...]} or a single decision object",
    )

    next_p = sub.add_parser("next-id", help="Suggest next decision_id")
    next_p.add_argument("project_id")
    next_p.add_argument("--prefix", default="d")

    args = parser.parse_args(argv)
    root = PROJECTS_DIR
    project_dir = root / args.project_id

    if args.command == "next-id":
        print(suggest_next_decision_id(project_dir, prefix=args.prefix))
        return 0

    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "decisions" in payload:
        decisions = payload["decisions"]
    elif isinstance(payload, dict):
        decisions = [payload]
    else:
        print("Expected JSON object or {decisions: [...]}", file=sys.stderr)
        return 1

    path = append_decisions(args.project_id, decisions, projects_dir=root)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
