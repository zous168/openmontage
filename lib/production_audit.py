"""Production governance audit — detect pipeline bypass and approval drift.

Read-only checks over a project directory. Used by contract tests and
referenced from ``skills/meta/reviewer.md``. Does not mutate projects.

See AGENT_GUIDE.md → "Pipeline Bypass Prohibition (HARD RULE)".
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

from lib.checkpoint import get_pipeline_stages
from lib.decision_log import latest_decisions_for_stage
from lib.events import read_events
from lib.voice_bounds import check_project_voice_listenability

# Repo-root scripts carrying this marker are dev/dogfood utilities only — not
# permitted production orchestrators. See tests/contracts/test_pipeline_bypass_contract.py.
NON_PRODUCTION_SCRIPT_MARKER = "OPENMONTAGE_NON_PRODUCTION_SCRIPT"

# Stages that require human approval on most pipelines when marked completed.
_GATED_STAGES = frozenset({"proposal", "script", "scene_plan", "assets"})

# Tool names that must appear in events.jsonl before compose completes on a
# generated pipeline (evidence the agent used tools, not a bypass script).
_COMPOSE_PREREQUISITE_TOOLS = frozenset({
    "tts_selector",
    "piper_tts",
    "doubao_tts",
    "image_selector",
    "frame_sampler",
    "subtitle_gen",
    "transcriber",
})


def _load_json(path: Path) -> Optional[dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _read_checkpoint_raw(project_dir: Path, stage: str) -> Optional[dict[str, Any]]:
    """Load checkpoint JSON without schema validation (audit must see bypass forgeries)."""
    return _load_json(project_dir / f"checkpoint_{stage}.json")


def _completed_stages_raw(project_dir: Path, pipeline_type: str) -> list[str]:
    completed: list[str] = []
    for stage in get_pipeline_stages(pipeline_type):
        cp = _read_checkpoint_raw(project_dir, stage)
        if cp and cp.get("status") == "completed":
            completed.append(stage)
    return completed


def check_approval_gate_drift(project_dir: Path) -> list[dict[str, Any]]:
    """Flag gated checkpoints approved while current decisions are still rejected.

    Uses the same (category, subject) → latest entry rule as the Backlot board.
    Mutating older entries (e.g. flipping ``user_visible`` to false) does NOT
    clear drift — only a newer approved entry for that pair counts.
    """
    findings: list[dict[str, Any]] = []
    decision_log = _load_json(project_dir / "decision_log.json") or {}
    all_decisions = decision_log.get("decisions") or []

    for stage in _GATED_STAGES:
        cp = _read_checkpoint_raw(project_dir, stage)
        if not cp:
            continue
        if cp.get("status") != "completed" or not cp.get("human_approved"):
            continue

        current = latest_decisions_for_stage(all_decisions, stage)
        blocking = [
            d for d in current
            if d.get("user_visible") and d.get("user_approved") is False
        ]
        if blocking:
            findings.append({
                "severity": "critical",
                "code": "approval_gate_drift",
                "stage": stage,
                "message": (
                    f"checkpoint_{stage} is completed with human_approved=true "
                    f"but {len(blocking)} current decision(s) for this stage still "
                    f"have user_approved=false (latest per category+subject)."
                ),
                "proposed_fix": (
                    f"Append new approved decision_log entries via "
                    f"lib.decision_log.append_decisions() or write_checkpoint() — "
                    f"do NOT edit decision_log.json by hand."
                ),
            })
    return findings


def check_compose_tool_trace(project_dir: Path, pipeline_type: str) -> list[dict[str, Any]]:
    """Compose completed but events.jsonl lacks prerequisite tool finishes."""
    findings: list[dict[str, Any]] = []
    compose_cp = _read_checkpoint_raw(project_dir, "compose")
    if not compose_cp or compose_cp.get("status") != "completed":
        return findings

    events = read_events(project_dir)
    finished_tools = {
        e.get("tool")
        for e in events
        if e.get("event") == "finish" and e.get("success")
    }
    if finished_tools & _COMPOSE_PREREQUISITE_TOOLS:
        return findings

    # Allow compose-only pipelines that truly have no assets stage — but
    # reference-driven and explainer paths always generate assets first.
    stages = get_pipeline_stages(pipeline_type)
    if "assets" not in stages:
        return findings

    assets_cp = _read_checkpoint_raw(project_dir, "assets")
    if assets_cp and assets_cp.get("status") == "completed":
        findings.append({
            "severity": "critical",
            "code": "compose_without_tool_trace",
            "stage": "compose",
            "message": (
                "compose checkpoint is completed but events.jsonl shows no "
                "successful finish events for asset-stage tools "
                f"({', '.join(sorted(_COMPOSE_PREREQUISITE_TOOLS))}). "
                "Likely a bypass script orchestrated compose without registry tools."
            ),
            "proposed_fix": (
                "Re-run assets and compose via stage director skills and "
                "BaseTool.execute() so events.jsonl records tool finishes."
            ),
        })
    return findings


def check_stage_prefix_order(project_dir: Path, pipeline_type: str) -> list[dict[str, Any]]:
    """Completed stages must form a prefix of the pipeline stage list."""
    findings: list[dict[str, Any]] = []
    order = get_pipeline_stages(pipeline_type)
    completed = _completed_stages_raw(project_dir, pipeline_type)
    if not completed:
        return findings

    expected_prefix = order[: len(completed)]
    if completed != expected_prefix:
        findings.append({
            "severity": "critical",
            "code": "stage_order_violation",
            "stage": completed[-1] if completed else "unknown",
            "message": (
                f"Completed stages {completed!r} are not a prefix of pipeline "
                f"order {order!r}."
            ),
            "proposed_fix": (
                "Reset from the first out-of-order stage and re-run via "
                "get_next_stage() — do not skip stages with ad-hoc scripts."
            ),
        })
    return findings


def audit_project(project_dir: Path, *, pipeline_type: Optional[str] = None) -> list[dict[str, Any]]:
    """Run all governance audits; return findings sorted critical-first."""
    if pipeline_type is None:
        marker = _load_json(project_dir / "project.json") or {}
        pipeline_type = marker.get("pipeline_type") or "unknown"

    findings: list[dict[str, Any]] = []
    findings.extend(check_approval_gate_drift(project_dir))
    findings.extend(check_stage_prefix_order(project_dir, pipeline_type))
    findings.extend(check_compose_tool_trace(project_dir, pipeline_type))
    findings.extend(check_project_voice_listenability(project_dir))

    severity_rank = {"critical": 0, "suggestion": 1, "investigation": 2}
    findings.sort(key=lambda f: severity_rank.get(f.get("severity", "investigation"), 9))
    return findings


def is_non_production_script(path: Path) -> bool:
    """True if *path* declares itself a non-production dev script."""
    try:
        head = path.read_text(encoding="utf-8")[:4096]
    except OSError:
        return False
    return NON_PRODUCTION_SCRIPT_MARKER in head


_NON_PRODUCTION_SCRIPT_NAME = re.compile(
    r"^(_compose_once|rerun_|run_.*_assets)\.py$",
    re.IGNORECASE,
)


def find_unmarked_non_production_scripts(scripts_dir: Path) -> list[Path]:
    """Repo-root scripts that look like production bypass but lack the marker."""
    if not scripts_dir.is_dir():
        return []
    bad: list[Path] = []
    for path in sorted(scripts_dir.glob("*.py")):
        if not _NON_PRODUCTION_SCRIPT_NAME.match(path.name):
            continue
        if not is_non_production_script(path):
            bad.append(path)
    return bad
