"""LT-032 — mock 驱动真实 hub worker 通道（workflow.execute 协议 · v4.0）.

用真实 ws 端点（mxai_unified_ws）+ 真实 RpaWorkerBridge，worker 侧用 mock_results 构造
workflow.result，驱动 bridge.execute_via_worker 真实派发-配对往返。

v4.0：协议为 workflow.execute / workflow.result（按 slug 寻址）。仅个人微信类 task_type 有
automan 工作流（slug=sendmsg/addfriend）；公域/Boss/企微为 gap（automan 告警+failed）→ 不在此断言成功。
完整 queue_manager+DB 链路另见 e2e-smoke.md。
"""

from __future__ import annotations

import importlib.util
import json
import threading
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.api.ws import mxai_unified_ws
from plugins.mxai.orchestrator.models import Task
from plugins.mxai.rpa_worker.bridge import get_rpa_worker_bridge, reset_rpa_worker_bridge

_AUTOMAN = Path(__file__).resolve().parents[3] / "automan"
_spec = importlib.util.spec_from_file_location(
    "am_mock_results_re", _AUTOMAN / "mock-rpa-cli" / "mock_results.py"
)
_results = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_results)


@pytest.fixture
def ws_client():
    reset_rpa_worker_bridge()
    app = FastAPI()
    app.add_api_websocket_route("/api/v1/ws", mxai_unified_ws)
    with TestClient(app) as client:
        yield client
    reset_rpa_worker_bridge()


def _connect_worker(ws):
    ws.send_text(json.dumps({
        "role": "rpa_worker", "type": "hello", "worker_id": "realenv-mock",
        "channels": ["douyin", "xiaohongshu", "shipinhao", "wechat", "qiyeweixin", "boss"],
    }))
    ack = json.loads(ws.receive_text())
    assert ack.get("type") == "hello.ack"


def _run_one(ws, task: Task) -> dict:
    """worker 侧：起线程派发任务；本线程收 workflow.execute 并用 mock 回 workflow.result。"""
    box: dict = {}

    def _dispatch():
        box["result"] = get_rpa_worker_bridge().execute_via_worker(task, timeout=5.0)

    t = threading.Thread(target=_dispatch, daemon=True)
    t.start()

    frame = json.loads(ws.receive_text())
    assert frame["type"] == "workflow.execute"
    request_id = frame["request_id"]
    meta = frame.get("meta") or {}
    # 用 mock 按 task_type 构造 outputs（inputs 为 per-type 映射）
    outputs = _results.build_mock_result(
        {"task_type": meta.get("task_type"), "profile_id": meta.get("profile_id"),
         "payload": frame.get("inputs") or {}}, success=True)
    ws.send_text(json.dumps({
        "type": "workflow.result", "request_id": request_id, "instance_id": "inst_re",
        "status": "succeeded", "outputs": outputs,
    }))
    t.join(timeout=5.0)
    return box.get("result", {})


def test_mock_drives_real_bridge_round_trip(ws_client: TestClient):
    """微信支持类（dm/add_friends slug 已配）经 workflow.execute 真实往返."""
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        _connect_worker(ws)
        assert get_rpa_worker_bridge().is_connected()  # worker 接管

        # dm（slug=sendmsg）
        r_dm = _run_one(ws, Task(task_id="re-dm", name="dm", profile_id="wechat",
                                 task_type="dm", payload={"recipient": "u1", "message": "hi"}))
        assert r_dm["send"]["sent"] is True
        assert r_dm["mode"] == "automan"  # from_result 归一

        # add_friends（slug=addfriend）
        r_af = _run_one(ws, Task(task_id="re-af", name="af", profile_id="wechat",
                                 task_type="add_friends", payload={"contacts": ["c1"]}))
        assert r_af.get("mode") == "automan"  # 往返 + from_result 归一（inputs 为 per-type 映射）


def test_mock_drive_failure_path(ws_client: TestClient):
    """worker 回 failed → execute_via_worker 抛 RuntimeError（任务即刻失败）."""
    with ws_client.websocket_connect("/api/v1/ws") as ws:
        _connect_worker(ws)
        task = Task(task_id="re-fail", name="dm", profile_id="wechat", task_type="dm")
        box: dict = {}

        def _dispatch():
            try:
                get_rpa_worker_bridge().execute_via_worker(task, timeout=5.0)
                box["err"] = None
            except RuntimeError as e:
                box["err"] = str(e)

        t = threading.Thread(target=_dispatch, daemon=True)
        t.start()
        frame = json.loads(ws.receive_text())
        assert frame["type"] == "workflow.execute"
        ws.send_text(json.dumps({
            "type": "workflow.result", "request_id": frame["request_id"],
            "status": "failed", "error": "mock forced failure",
        }))
        t.join(timeout=5.0)
        assert box.get("err") and "mock forced failure" in box["err"]
