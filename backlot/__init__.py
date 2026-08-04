"""Backlot — the living storyboard.

A disk-derived production board for OpenMontage — and, since API_VERSION 44,
a second execution channel alongside the interactive agent. A small local web
server watches ``projects/`` and renders each production's pipeline stages,
script, scene plan, generated assets, decisions, cost, and activity — live.

Design contract (see internal/design/LIVING_STORYBOARD.md):
- Observation, not reporting: all state derives from files the pipeline
  already writes. Agents never update the UI.
- Never block, never break: malformed or missing state degrades gracefully.
- The agent's only duty: ``python -m backlot open <project>`` at pipeline init.
- Web channel (backlot.stage_runner): the page can trigger a headless agent
  (``claude -p``) to execute a single pipeline stage, and approve / reject
  awaiting-human gates. It follows the same director-skill / registry /
  checkpoint / append-only decision-log contract as the interactive agent.
"""

__version__ = "0.1.0"
# Bump when the UI requires new API routes (``backlot open`` restarts stale servers).
API_VERSION = 45

DEFAULT_PORT = 4750
