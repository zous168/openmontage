"""Optional integration test — real headless claude spawn (slow, opt-in).

Verifies the Windows spawn chain end-to-end: CLI resolution (claude.exe /
claude.cmd) → argv construction → child env scrub → `claude -p` executes
and returns.

The env scrub is load-bearing, not cosmetic: the Backlot server normally
inherits ``CLAUDE_CODE_ENTRYPOINT`` from the interactive session that
launched it, and passing it through makes the child use host-managed OAuth
credentials → ``401 OAuth access token has expired``. This test spawns with
``_child_env()`` so a regression there fails here.

Run explicitly (skipped by default):
    RUN_BACKLOT_HEADLESS_IT=1 python -m pytest tests/backlot/test_headless_integration.py -v
"""

from __future__ import annotations

import os
import subprocess

import pytest

import backlot.stage_runner as stage_runner_mod

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BACKLOT_HEADLESS_IT") != "1",
    reason="opt-in integration test (spawns a real claude process)",
)


def test_headless_claude_spawns_and_answers():
    cmd = [
        *stage_runner_mod._resolve_claude_cmd(),
        *stage_runner_mod._build_cli_args(1.0),
        "print 1+1",
    ]
    assert cmd[0]  # resolved binary (no shell interpolation)
    r = subprocess.run(
        cmd, capture_output=True, timeout=180,
        cwd=str(stage_runner_mod.REPO_ROOT),
        env=stage_runner_mod._child_env(),  # 与 _spawn_agent 同一环境构造
    )
    assert r.returncode == 0, (
        f"claude exited {r.returncode}: "
        f"{r.stderr.decode('utf-8', 'replace')[:400]}"
    )
    out = (r.stdout or b"").decode("utf-8", "replace")
    assert "2" in out, f"expected answer in stdout, got: {out[:400]}"
