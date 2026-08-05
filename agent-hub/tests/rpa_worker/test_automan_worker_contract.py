"""LT-030.03.02（步骤A 协议契约）— automan worker 帧 ↔ 真实 hub bridge.

跨仓加载 automan/src/hub_worker/message_types.py（自包含，仅 typing），
用 automan worker 的真实帧构造器驱动真实 hub RpaWorkerBridge + ws 识别逻辑，
闭合 hub↔worker 协议环：hello 被识别、dispatch 可解析、result 被 bridge 接受。

真实 socket 握手 + Tauri sidecar 拉起仍需运行时环境（见 e2e-smoke.md），不在本测试范围。
"""

from __future__ import annotations

import asyncio
import importlib.util
import threading
import time
from pathlib import Path

import pytest

from plugins.mxai.api.ws import _is_rpa_hello
from plugins.mxai.orchestrator.models import Task
from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge, reset_rpa_worker_bridge

# 跨仓加载 automan worker 的自包含协议模块
_MT_PATH = (
    Path(__file__).resolve().parents[3]
    / "automan" / "src" / "hub_worker" / "message_types.py"
)
_spec = importlib.util.spec_from_file_location("automan_hub_worker_message_types", _MT_PATH)
mt = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mt)


@pytest.fixture(autouse=True)
def _reset():
    reset_rpa_worker_bridge()
    yield
    reset_rpa_worker_bridge()


class _FakeWs:
    """记录 hub 下发帧的桩 ws。"""

    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)


# ── 契约1: automan worker 的 hello 被 hub 识别为 rpa_worker ──
def test_automan_hello_recognized_by_hub():
    hello = mt.build_hello("automan-host01")
    assert _is_rpa_hello(hello) is True
    assert hello["role"] == "rpa_worker"
    # 六渠道与 hub mock_worker CHANNELS 对齐
    assert set(mt.CHANNELS) == {"douyin", "xiaohongshu", "shipinhao", "wechat", "qiyeweixin", "boss"}


# ── 契约2: hub 下发的 task.dispatch 可被 worker 解析 ───────
def test_hub_dispatch_parsed_by_worker():
    import json

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    fake = _FakeWs()
    bridge.register(fake, loop, mt.build_hello("automan-c1"))

    task = Task(task_id="t-disp", name="dm", profile_id="wechat", task_type="dm",
                payload={"recipient": "u1", "message": "hi"})

    def _reply():
        time.sleep(0.05)
        # v4.0：worker 回 workflow.result（request_id 配对，outputs 归一）
        frame = mt.build_workflow_result("t-disp", status=mt.STATUS_SUCCEEDED,
                                         instance_id="i1", outputs={"sent": True})
        bridge.on_workflow_result(frame)

    threading.Thread(target=_reply, daemon=True).start()
    result = bridge.execute_via_worker(task, timeout=5.0)

    # hub 下发 workflow.execute 帧（按 slug 寻址）
    assert fake.sent, "hub 应已下发 workflow.execute"
    dispatched = json.loads(fake.sent[0])
    assert dispatched["type"] == mt.MSG_WORKFLOW_EXECUTE
    assert dispatched["request_id"] == "t-disp"
    assert dispatched["slug"] == "sendmsg"  # dm → sendmsg
    assert dispatched["meta"]["task_type"] == "dm"

    # worker workflow.result → 被 bridge 接受并解包（from_result 归一）
    assert result.get("sent") is True
    assert result.get("mode") == "automan"

    loop.call_soon_threadsafe(loop.stop)


# ── 契约3: worker 失败 result 被 bridge 识别为失败 ─────────
def test_worker_failure_result_raises():
    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    bridge.register(_FakeWs(), loop, mt.build_hello("automan-c2"))

    task = Task(task_id="t-fail", name="dm", profile_id="wechat", task_type="dm")

    def _reply():
        time.sleep(0.05)
        frame = mt.build_workflow_result("t-fail", status=mt.STATUS_FAILED, error="boom")
        bridge.on_workflow_result(frame)

    threading.Thread(target=_reply, daemon=True).start()
    with pytest.raises(RuntimeError, match="boom"):
        bridge.execute_via_worker(task, timeout=5.0)

    loop.call_soon_threadsafe(loop.stop)
