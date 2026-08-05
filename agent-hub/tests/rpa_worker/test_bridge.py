"""RPA Worker bridge tests."""

from __future__ import annotations

import json
import threading
import time

import pytest

from plugins.mxai.orchestrator.models import Task
from plugins.mxai.rpa_worker.bridge import (
    WorkflowExecutionError,
    get_rpa_worker_bridge,
    reset_rpa_worker_bridge,
)


@pytest.fixture(autouse=True)
def _reset_bridge():
    reset_rpa_worker_bridge()
    yield
    reset_rpa_worker_bridge()


class _FakeWs:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send_text(self, payload: str) -> None:
        self.sent.append(payload)


def test_bridge_status_disconnected():
    bridge = get_rpa_worker_bridge()
    st = bridge.status()
    assert st["connected"] is False
    assert st["worker_id"] is None


def test_register_triggers_queue_drain(monkeypatch):
    """LT-032：worker 上线即触发队列 drain（冲掉离线积压）."""
    import asyncio

    from plugins.mxai.orchestrator.queue_manager import QueueManager

    called: list[bool] = []
    monkeypatch.setattr(QueueManager, "notify_worker_connected",
                        lambda self: called.append(True))

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    bridge.register(_FakeWs(), loop, {"worker_id": "w", "channels": ["wechat"]})
    assert called == [True]


def test_send_monitor_fires_frame_over_ws(monkeypatch):
    """LT-032.06.01：monitor.start 经同一 WS 发出，带 monitor_slugs，fire-and-forget."""
    import asyncio

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.RpaWorkerBridge._read_rpa_integrate_settings",
        lambda self: ("ws", ""),
    )
    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    fake = _FakeWs()
    bridge.register(fake, loop, {"worker_id": "w", "channels": ["wechat"]})

    sent = bridge.send_monitor("start", ["douyin_reply", "weixin_reply"])
    assert sent is True
    assert fake.sent
    frame = json.loads(fake.sent[-1])
    assert frame["type"] == "monitor.start"
    assert frame["monitor_slugs"] == ["douyin_reply", "weixin_reply"]
    loop.call_soon_threadsafe(loop.stop)


def test_send_monitor_offline_returns_false():
    """worker 未连接：send_monitor 不抛错、返回 False（不阻塞开始工作）."""
    bridge = get_rpa_worker_bridge()
    assert bridge.send_monitor("stop") is False


def test_send_stop_all_executions_fires_frame_over_ws(monkeypatch):
    """终止全部：WS 发 executions.stop_all."""
    import asyncio

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.RpaWorkerBridge._read_rpa_integrate_settings",
        lambda self: ("ws", ""),
    )
    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    fake = _FakeWs()
    bridge.register(fake, loop, {"worker_id": "w", "channels": ["wechat"]})

    sent = bridge.send_stop_all_executions()
    assert sent is True
    assert fake.sent
    frame = json.loads(fake.sent[-1])
    assert frame["type"] == "executions.stop_all"
    loop.call_soon_threadsafe(loop.stop)


def test_send_stop_all_executions_offline_returns_false():
    bridge = get_rpa_worker_bridge()
    assert bridge.send_stop_all_executions() is False


def test_send_stop_all_executions_http_posts_open_api(monkeypatch):
    calls: list[str] = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True, "data": {"detail": "stopped=1"}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return None

        def post(self, url, json=None):
            calls.append(url)
            return _Resp()

    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.RpaWorkerBridge._read_rpa_integrate_settings",
        lambda self: ("http", "http://127.0.0.1:8123"),
    )
    monkeypatch.setattr("httpx.Client", _Client)
    bridge = get_rpa_worker_bridge()
    assert bridge.send_stop_all_executions() is True
    assert calls == ["http://127.0.0.1:8123/api/open/executions/stop-all"]


def test_send_monitor_invalid_action():
    bridge = get_rpa_worker_bridge()
    with pytest.raises(ValueError):
        bridge.send_monitor("pause")


def test_send_monitor_http_posts_open_api(monkeypatch):
    """CR-122：http 集成模式下 send_monitor 走 Open API，不经 WS."""
    calls: list[tuple[str, str, dict]] = []

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"ok": True, "data": {"action": "start", "detail": "ok"}}

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, json=None):
            calls.append(("POST", url, json or {}))
            return _Resp()

    monkeypatch.setattr("httpx.Client", _Client)
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.RpaWorkerBridge._read_rpa_integrate_settings",
        lambda self: ("http", "http://127.0.0.1:8123"),
    )

    bridge = get_rpa_worker_bridge()
    sent = bridge.send_monitor("start", ["weixin_reply"])
    assert sent is True
    assert calls
    assert calls[0][1] == "http://127.0.0.1:8123/api/open/monitor/start"
    assert calls[0][2]["monitor_slugs"] == ["weixin_reply"]


def test_send_monitor_http_offline_returns_false(monkeypatch):
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.RpaWorkerBridge._read_rpa_integrate_settings",
        lambda self: ("http", ""),
    )
    bridge = get_rpa_worker_bridge()
    assert bridge.send_monitor("stop") is False


def test_send_monitor_ws_mode_when_settings_ws(monkeypatch):
    """ws 模式仍走 WS 帧（回归）."""
    import asyncio

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    fake = _FakeWs()
    bridge.register(fake, loop, {"worker_id": "w", "channels": ["wechat"]})
    monkeypatch.setattr(
        "plugins.mxai.rpa_worker.bridge.RpaWorkerBridge._read_rpa_integrate_settings",
        lambda self: ("ws", "http://127.0.0.1:8123"),
    )

    sent = bridge.send_monitor("start", ["weixin_reply"])
    assert sent is True
    frame = json.loads(fake.sent[-1])
    assert frame["type"] == "monitor.start"
    assert frame["monitor_slugs"] == ["weixin_reply"]
    loop.call_soon_threadsafe(loop.stop)


def test_bridge_execute_via_worker_roundtrip():
    import asyncio

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    fake = _FakeWs()
    bridge.register(fake, loop, {"worker_id": "test-worker", "channels": ["wechat"]})

    task = Task(
        task_id="tsk_test001",
        name="test task",
        profile_id="wechat",
        task_type="dm",
    )

    def complete_later():
        time.sleep(0.05)
        bridge.on_workflow_result(
            {
                "request_id": "tsk_test001",
                "status": "succeeded",
                "outputs": {"simulated": True},
            }
        )

    threading.Thread(target=complete_later, daemon=True).start()
    result = bridge.execute_via_worker(task, timeout=5.0)
    assert result["simulated"] is True
    assert fake.sent
    assert "workflow.execute" in fake.sent[0]
    loop.call_soon_threadsafe(loop.stop)


def test_bridge_workflow_accepted_uses_real_instance_id():
    import asyncio

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    fake = _FakeWs()
    bridge.register(fake, loop, {"worker_id": "test-worker", "channels": ["wechat"]})
    task = Task(
        task_id="tsk_accepted",
        name="scheduled",
        profile_id="wechat",
        task_type="scheduled_msg",
        payload={"delivery_id": "tdl-1"},
    )
    accepted: list[str] = []

    def complete_later():
        time.sleep(0.05)
        bridge.on_workflow_accepted(
            {"request_id": task.task_id, "instance_id": "real-instance-99"}
        )
        bridge.on_workflow_result(
            {
                "request_id": task.task_id,
                "instance_id": "real-instance-99",
                "status": "succeeded",
                "outputs": {"send_status": "sent"},
            }
        )

    threading.Thread(target=complete_later, daemon=True).start()
    result = bridge.execute_via_worker(
        task,
        timeout=5,
        on_accepted=accepted.append,
    )
    assert accepted == ["real-instance-99"]
    assert result["execution_id"] == "real-instance-99"
    loop.call_soon_threadsafe(loop.stop)


def test_bridge_failed_scheduled_result_preserves_outputs():
    import asyncio

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    fake = _FakeWs()
    bridge.register(fake, loop, {"worker_id": "test-worker", "channels": ["wechat"]})
    task = Task(
        task_id="tsk_failed_outputs",
        name="scheduled",
        profile_id="wechat",
        task_type="scheduled_msg",
        payload={"delivery_id": "tdl-2"},
    )

    def complete_later():
        time.sleep(0.05)
        bridge.on_workflow_accepted(
            {"request_id": task.task_id, "instance_id": "real-instance-100"}
        )
        bridge.on_workflow_result(
            {
                "request_id": task.task_id,
                "instance_id": "real-instance-100",
                "status": "failed",
                "outputs": {"send_status": "sent", "sent_at": "2026-07-14T00:00:00+00:00"},
                "error": "cleanup failed",
            }
        )

    threading.Thread(target=complete_later, daemon=True).start()
    result = bridge.execute_via_worker(task, timeout=5, on_accepted=lambda _eid: None)
    assert result["send_status"] == "sent"
    assert result["sent_at"] == "2026-07-14T00:00:00+00:00"
    assert result["cleanup_warning"]
    loop.call_soon_threadsafe(loop.stop)


def test_bridge_rejected_before_accepted_is_retryable_failure():
    import asyncio

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    fake = _FakeWs()
    bridge.register(fake, loop, {"worker_id": "test-worker", "channels": ["wechat"]})
    task = Task(
        task_id="tsk_rejected_before_accepted",
        name="scheduled",
        profile_id="wechat",
        task_type="scheduled_msg",
        payload={"delivery_id": "tdl-rejected"},
    )

    def complete_later():
        time.sleep(0.05)
        bridge.on_workflow_result(
            {
                "request_id": task.task_id,
                "status": "failed",
                "outputs": {},
                "error": "no automan workflow",
            }
        )

    threading.Thread(target=complete_later, daemon=True).start()
    with pytest.raises(WorkflowExecutionError) as caught:
        bridge.execute_via_worker(task, timeout=5)
    assert caught.value.execution_id == ""
    assert caught.value.outcome_hint == "failed"
    loop.call_soon_threadsafe(loop.stop)


def test_bridge_disconnect_before_accepted_is_uncertain():
    import asyncio

    bridge = get_rpa_worker_bridge()
    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    fake = _FakeWs()
    bridge.register(fake, loop, {"worker_id": "test-worker", "channels": ["wechat"]})
    task = Task(
        task_id="tsk_disconnect_before_accepted",
        name="scheduled",
        profile_id="wechat",
        task_type="scheduled_msg",
        payload={"delivery_id": "tdl-disconnect"},
    )

    def disconnect_later():
        time.sleep(0.05)
        bridge.unregister(fake)

    threading.Thread(target=disconnect_later, daemon=True).start()
    with pytest.raises(WorkflowExecutionError) as caught:
        bridge.execute_via_worker(task, timeout=5)
    assert caught.value.execution_id == ""
    assert caught.value.outcome_hint == "uncertain"
    loop.call_soon_threadsafe(loop.stop)


# ── http 出站（hub→automan Open API，async + 轮询）──────────────────


def _http_task() -> Task:
    return Task(
        task_id="tsk_http001",
        name="http task",
        profile_id="wechat",
        task_type="dm",
        payload={"recipient": "wxid_x", "message": "hi"},
    )


class _Resp:
    """假 httpx 响应：status_code + json()（payload=None 时模拟非 JSON）。"""

    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _FakeClient:
    """假 httpx.Client：记录 post，依次返回 get 响应（用尽后重复末个）。"""

    def __init__(self, post_resp, get_resps=None):
        self._post_resp = post_resp
        self._get_resps = list(get_resps or [])
        self.post_url = None
        self.post_json = None

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, json=None):
        self.post_url, self.post_json = url, json
        return self._post_resp

    def get(self, url):
        if len(self._get_resps) > 1:
            return self._get_resps.pop(0)
        return self._get_resps[0]


def _patch_client(monkeypatch, fake):
    import httpx

    monkeypatch.setattr(httpx, "Client", lambda **kw: fake)


def test_execute_via_worker_http_async_success(monkeypatch):
    """async：POST mode=async 拿 instance_id → 轮询 completed 取 output_vars 归一。"""
    fake = _FakeClient(
        post_resp=_Resp(200, {"ok": True, "data": {"instance_id": "42"}}),
        get_resps=[_Resp(200, {"ok": True, "data": {"status": "completed", "output_vars": {"sent": True}}})],
    )
    _patch_client(monkeypatch, fake)

    bridge = get_rpa_worker_bridge()
    result = bridge.execute_via_worker_http(_http_task(), "http://127.0.0.1:8123/", poll_interval=0)

    assert result["sent"] is True
    assert result["mode"] == "automan"  # from_result 归一补 mode
    assert fake.post_url == "http://127.0.0.1:8123/api/open/hooks/weixin_sendmsg"
    assert fake.post_json["mode"] == "async"
    assert fake.post_json["inputs"] == {"inputid": "wxid_x", "msg": "hi"}


def test_execute_via_worker_http_calls_accepted_immediately(monkeypatch):
    fake = _FakeClient(
        post_resp=_Resp(200, {"ok": True, "data": {"instance_id": "accepted-7"}}),
        get_resps=[
            _Resp(
                200,
                {
                    "ok": True,
                    "data": {
                        "status": "completed",
                        "output_vars": {"send_status": "sent"},
                    },
                },
            )
        ],
    )
    _patch_client(monkeypatch, fake)
    accepted: list[str] = []
    task = _http_task()
    task.task_type = "scheduled_msg"
    task.payload["delivery_id"] = "tdl-http"
    result = get_rpa_worker_bridge().execute_via_worker_http(
        task,
        "http://127.0.0.1:8123",
        poll_interval=0,
        on_accepted=accepted.append,
    )
    assert accepted == ["accepted-7"]
    assert result["execution_id"] == "accepted-7"


def test_execute_via_worker_http_polls_until_terminal(monkeypatch):
    """running → completed：中间态继续轮询，终态才返回。"""
    fake = _FakeClient(
        post_resp=_Resp(200, {"ok": True, "data": {"instance_id": "7"}}),
        get_resps=[
            _Resp(200, {"ok": True, "data": {"status": "running"}}),
            _Resp(200, {"ok": True, "data": {"status": "completed", "output_vars": {"x": 1}}}),
        ],
    )
    _patch_client(monkeypatch, fake)
    bridge = get_rpa_worker_bridge()
    result = bridge.execute_via_worker_http(_http_task(), "http://127.0.0.1:8123", poll_interval=0)
    assert result["x"] == 1


def test_execute_via_worker_http_failed_status_raises(monkeypatch):
    """终态 failed → RuntimeError（带 error_message）。"""
    fake = _FakeClient(
        post_resp=_Resp(200, {"ok": True, "data": {"instance_id": "9"}}),
        get_resps=[_Resp(200, {"ok": True, "data": {"status": "failed", "error_message": "boom"}})],
    )
    _patch_client(monkeypatch, fake)
    bridge = get_rpa_worker_bridge()
    with pytest.raises(RuntimeError, match="boom"):
        bridge.execute_via_worker_http(_http_task(), "http://127.0.0.1:8123", poll_interval=0)


def test_execute_via_worker_http_404_no_workflow(monkeypatch):
    """slug 无对应工作流（提交 404）→ NoWorkflowError（与 ws 缺口语义一致）。"""
    from plugins.mxai.rpa_worker.automan_bridge import NoWorkflowError

    fake = _FakeClient(post_resp=_Resp(404, text="not found"))
    _patch_client(monkeypatch, fake)
    bridge = get_rpa_worker_bridge()
    with pytest.raises(NoWorkflowError):
        bridge.execute_via_worker_http(_http_task(), "http://127.0.0.1:8123", poll_interval=0)


def test_execute_via_worker_http_404_delivery_is_retryable_failure(monkeypatch):
    fake = _FakeClient(post_resp=_Resp(404, text="not found"))
    _patch_client(monkeypatch, fake)
    task = _http_task()
    task.task_type = "scheduled_msg"
    task.payload["delivery_id"] = "tdl-http-404"

    with pytest.raises(WorkflowExecutionError) as caught:
        get_rpa_worker_bridge().execute_via_worker_http(
            task,
            "http://127.0.0.1:8123",
            poll_interval=0,
        )
    assert caught.value.execution_id == ""
    assert caught.value.outcome_hint == "failed"


def test_execute_via_worker_http_non_200_raises(monkeypatch):
    fake = _FakeClient(post_resp=_Resp(500, text="boom"))
    _patch_client(monkeypatch, fake)
    bridge = get_rpa_worker_bridge()
    with pytest.raises(RuntimeError):
        bridge.execute_via_worker_http(_http_task(), "http://127.0.0.1:8123", poll_interval=0)


def test_execute_via_worker_http_500_delivery_is_uncertain(monkeypatch):
    fake = _FakeClient(post_resp=_Resp(500, text="boom"))
    _patch_client(monkeypatch, fake)
    task = _http_task()
    task.task_type = "scheduled_msg"
    task.payload["delivery_id"] = "tdl-http-500"

    with pytest.raises(WorkflowExecutionError) as caught:
        get_rpa_worker_bridge().execute_via_worker_http(
            task,
            "http://127.0.0.1:8123",
            poll_interval=0,
        )
    assert caught.value.outcome_hint == "uncertain"


def test_execute_via_worker_http_requires_outbound_url():
    bridge = get_rpa_worker_bridge()
    with pytest.raises(RuntimeError):
        bridge.execute_via_worker_http(_http_task(), "")
