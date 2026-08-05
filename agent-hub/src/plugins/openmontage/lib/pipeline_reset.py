"""Archive downstream checkpoints so a project can resume from a given stage."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plugins.openmontage.lib.checkpoint import get_pipeline_stages
from plugins.openmontage.lib.paths import PROJECTS_DIR


class PipelineResetError(Exception):
    """Reset could not be applied."""

    def __init__(self, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.status = status


def reset_from_stage(
    project_id: str,
    from_stage: str,
    *,
    projects_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Archive checkpoint_<stage>.json from *from_stage* onward; resume starts there.

    Does not delete artifacts — the next agent run may overwrite them.
    """
    base = projects_dir or PROJECTS_DIR
    project_dir = base / project_id
    if not project_dir.is_dir():
        raise PipelineResetError(f"项目不存在：{project_id}", status=404)

    marker_path = project_dir / "project.json"
    if not marker_path.is_file():
        raise PipelineResetError(f"项目缺少 project.json：{project_id}", status=404)

    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise PipelineResetError("无法读取 project.json") from exc

    pipeline_type = marker.get("pipeline_type")
    if not pipeline_type:
        raise PipelineResetError("项目缺少 pipeline_type")

    stages = get_pipeline_stages(pipeline_type)
    if not stages:
        raise PipelineResetError(f"流水线 {pipeline_type!r} 没有阶段定义")

    if from_stage not in stages:
        raise PipelineResetError(
            f"未知阶段 {from_stage!r}（流水线 {pipeline_type!r}）"
        )

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

    from plugins.openmontage.lib.checkpoint import get_next_stage

    next_stage = get_next_stage(base, project_id, pipeline_type) if not dry_run else from_stage

    return {
        "ok": True,
        "project_id": project_id,
        "pipeline_type": pipeline_type,
        "from_stage": from_stage,
        "removed_stages": removed,
        "next_stage": next_stage,
    }


def reset_to_first_stage(
    project_id: str,
    *,
    projects_dir: Path | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Reset from the pipeline manifest's first stage."""
    base = projects_dir or PROJECTS_DIR
    project_dir = base / project_id
    if not project_dir.is_dir():
        raise PipelineResetError(f"项目不存在：{project_id}", status=404)

    marker = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    pipeline_type = marker.get("pipeline_type")
    if not pipeline_type:
        raise PipelineResetError("项目缺少 pipeline_type")

    stages = get_pipeline_stages(pipeline_type)
    if not stages:
        raise PipelineResetError(f"流水线 {pipeline_type!r} 没有阶段定义")

    return reset_from_stage(
        project_id,
        stages[0],
        projects_dir=projects_dir,
        dry_run=dry_run,
    )
