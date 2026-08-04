#!/usr/bin/env python3
"""Reset a project pipeline to a given stage (archive downstream checkpoints).

Used for governed reruns: archives checkpoint_<stage>.json files from the
reset stage onward into history/, so get_next_stage() resumes correctly.
Does not delete artifacts — the next agent run may overwrite them.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lib.pipeline_reset import PipelineResetError, reset_from_stage


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset project pipeline from a stage")
    parser.add_argument("project_id")
    parser.add_argument(
        "from_stage",
        help="First stage to reset (this stage's checkpoint is removed; resume starts here)",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        result = reset_from_stage(
            args.project_id,
            args.from_stage,
            dry_run=args.dry_run,
        )
    except PipelineResetError as exc:
        raise SystemExit(str(exc)) from exc

    verb = "Would reset" if args.dry_run else "Reset"
    removed = result.get("removed_stages") or []
    print(f"{verb} {args.project_id} from {args.from_stage!r}: {removed or '(no checkpoints found)'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
