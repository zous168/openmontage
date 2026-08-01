#!/usr/bin/env python3
"""Reset a project pipeline to a given stage (archive downstream checkpoints).

Used for governed reruns: archives checkpoint_<stage>.json files from the
reset stage onward into history/, so get_next_stage() resumes correctly.
Does not delete artifacts — the next agent run may overwrite them.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.checkpoint import get_pipeline_stages
from lib.paths import PROJECTS_DIR


def reset_from_stage(project_id: str, from_stage: str, *, dry_run: bool = False) -> list[str]:
    project_dir = PROJECTS_DIR / project_id
    if not project_dir.is_dir():
        raise SystemExit(f"Project not found: {project_dir}")

    marker = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    pipeline_type = marker.get("pipeline_type", "reference-driven")
    stages = get_pipeline_stages(pipeline_type)

    if from_stage not in stages:
        raise SystemExit(f"Unknown stage {from_stage!r} for pipeline {pipeline_type!r}")

    start_idx = stages.index(from_stage)
    to_reset = stages[start_idx:]

    history_dir = project_dir / "history"
    if not dry_run:
        history_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    removed: list[str] = []

    for stage in to_reset:
        cp = project_dir / f"checkpoint_{stage}.json"
        if not cp.exists():
            continue
        removed.append(stage)
        if dry_run:
            continue
        dest = history_dir / f"checkpoint_{stage}_reset_{stamp}.json"
        if dest.exists():
            dest = history_dir / f"checkpoint_{stage}_reset_{stamp}_{cp.stat().st_mtime_ns}.json"
        shutil.copy2(cp, dest)
        cp.unlink()

    # Invalidate proposal approval when proposal stage is reset.
    if not dry_run and "proposal" in to_reset:
        proposal_path = project_dir / "artifacts" / "proposal_packet.json"
        if proposal_path.exists():
            try:
                packet = json.loads(proposal_path.read_text(encoding="utf-8"))
                packet.setdefault("approval", {})["status"] = "pending"
                proposal_path.write_text(
                    json.dumps(packet, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            except (json.JSONDecodeError, OSError):
                pass

    return removed


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset project pipeline from a stage")
    parser.add_argument("project_id")
    parser.add_argument(
        "from_stage",
        help="First stage to reset (this stage's checkpoint is removed; resume starts here)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    removed = reset_from_stage(args.project_id, args.from_stage, dry_run=args.dry_run)
    verb = "Would reset" if args.dry_run else "Reset"
    print(f"{verb} {args.project_id} from {args.from_stage!r}: {removed or '(no checkpoints found)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
