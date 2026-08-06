"""Optional integration test — real in-process Hermes AIAgent (slow, opt-in).

Verifies that ``run_agent_conversation`` can construct an AIAgent and complete
a trivial turn (requires configured provider credentials).

Run explicitly (skipped by default):
    RUN_BACKLOT_HEADLESS_IT=1 python -m pytest tests/backlot/test_headless_integration.py -v
"""

from __future__ import annotations

import io
import os

import pytest

from plugins.openmontage.backlot import agent_executor

pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_BACKLOT_HEADLESS_IT") != "1",
    reason="opt-in integration test (runs a real Hermes AIAgent turn)",
)


def test_headless_hermes_agent_answers():
    buf = io.BytesIO()
    holder: list = []
    result = agent_executor.run_agent_conversation(
        "Reply with exactly the characters: 2",
        task_id="itest",
        log_fh=buf,
        agent_holder=holder,
    )
    assert result.get("exit_code") == 0, result
    assert "2" in (result.get("final_response") or ""), result
    log_text = buf.getvalue().decode("utf-8", "replace")
    assert '"type": "system"' in log_text or '"type":"system"' in log_text
