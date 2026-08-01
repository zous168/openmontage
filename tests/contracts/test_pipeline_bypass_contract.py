"""Enforce pipeline bypass prohibition — internal governance contract.

Agents must orchestrate production via director skills + registry tools +
checkpoints, not ad-hoc Python scripts. This test guards the written contract
so fresh-session agents and CI catch regressions.

See:
- AGENT_GUIDE.md → Pipeline Bypass Prohibition (HARD RULE)
- skills/meta/reviewer.md → Pipeline Orchestration Bypass Review
- skills/meta/capability-extension.md
- lib/production_audit.py
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SKILLS_DIR = ROOT / "skills"
SCRIPTS_DIR = ROOT / "scripts"


def test_agent_guide_has_pipeline_bypass_hard_rule():
    guide = (ROOT / "AGENT_GUIDE.md").read_text(encoding="utf-8")
    assert "Pipeline Bypass Prohibition" in guide
    assert "HARD RULE" in guide
    assert "events.jsonl" in guide
    assert "audit_project" in guide
    assert "Agent Introspection" in guide
    assert "lib.project_status" in guide
    assert "Artifact Persistence" in guide
    assert "decision_log.append_decisions" in guide or "lib.decision_log" in guide


def test_reviewer_flags_bypass_as_critical():
    body = (SKILLS_DIR / "meta" / "reviewer.md").read_text(encoding="utf-8")
    assert "Pipeline Orchestration Bypass Review" in body
    assert "approval_gate_drift" in body
    assert "compose_without_tool_trace" in body
    assert re.search(
        r"compose_without_tool_trace.{0,400}(CRITICAL|critical)",
        body,
        re.DOTALL,
    ), "Reviewer must treat missing tool trace as CRITICAL"


def test_capability_extension_forbids_multi_stage_scripts():
    body = (SKILLS_DIR / "meta" / "capability-extension.md").read_text(encoding="utf-8")
    assert "Never use a script to substitute the pipeline" in body
    assert "assets" in body and "compose" in body


@pytest.mark.parametrize(
    "name",
    sorted(p.name for p in SCRIPTS_DIR.glob("*.py") if re.match(r"^(rerun_|run_.*_assets)\.py$", p.name)),
)
def test_dogfood_scripts_carry_non_production_marker(name: str):
    from lib.production_audit import is_non_production_script

    path = SCRIPTS_DIR / name
    assert is_non_production_script(path), (
        f"{path} looks like a production bypass script but is missing "
        f"OPENMONTAGE_NON_PRODUCTION_SCRIPT in its header. Mark it explicitly "
        f"or remove it — see AGENT_GUIDE.md → Pipeline Bypass Prohibition."
    )
