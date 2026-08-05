"""CLI mock worker tests."""

from __future__ import annotations

import importlib.util
import threading
import time
from pathlib import Path

import pytest

from plugins.mxai.orchestrator.models import Task
from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge, reset_rpa_worker_bridge

_CLI_PATH = Path(__file__).resolve().parents[3] / "automan" / "mock-rpa-cli" / "mock_worker.py"
_spec = importlib.util.spec_from_file_location("automan_mock_worker_cli", _CLI_PATH)
_cli_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_cli_mod)
_spec_results = importlib.util.spec_from_file_location(
    "automan_mock_results",
    _CLI_PATH.parent / "mock_results.py",
)
_results_mod = importlib.util.module_from_spec(_spec_results)
assert _spec_results.loader is not None
_spec_results.loader.exec_module(_results_mod)


@pytest.fixture(autouse=True)
def _reset():
    reset_rpa_worker_bridge()
    yield
    reset_rpa_worker_bridge()


class _FakeWs:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)


def test_cli_mock_result_shape():
    r = _results_mod.build_mock_result(
        {"profile_id": "wechat", "task_type": "inbound_reply", "payload": {"message": "你好"}},
    )
    assert r["reply"]["text"]
    assert r["send"]["sent"] is True


def test_bridge_with_simulated_cli_result():
    import asyncio

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    fake = _FakeWs()
    bridge.register(fake, loop, {"worker_id": "cli-test", "channels": ["wechat"]})

    task = Task(task_id="tsk_cli01", name="cli task", profile_id="wechat", task_type="dm")

    def reply():
        time.sleep(0.05)
        bridge.on_workflow_result(
            {
                "request_id": "tsk_cli01",
                "status": "succeeded",
                "outputs": {"mode": "automan_mock_cli", "simulated": True},
            }
        )

    threading.Thread(target=reply, daemon=True).start()
    result = bridge.execute_via_worker(task, timeout=5.0)
    assert result.get("mode") == "automan_mock_cli"
    loop.call_soon_threadsafe(loop.stop)
