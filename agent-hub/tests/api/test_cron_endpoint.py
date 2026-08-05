"""MxAI cron-run 端点（CR-132 方案 A · Hermes cron http job 打这里跑 in-gateway 业务）.

鉴权走 **MxAI 标准 IPC token**（`X-Hub-Local-Token`），端点本身不自建鉴权——由 dashboard
鉴权门统一把关。端到端鉴权集成见 ``tests/test_mxai_gateway.py``
（``test_gateway_mxai_cron_run_uses_standard_ipc_auth``，走真实门）。本文件只测 **dispatch**：
``mxai_client`` fixture 直挂 router、不过门，故直接命中端点体。
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_cron_run_unknown_kind_404(mxai_client: TestClient) -> None:
    res = mxai_client.post("/api/plugins/mxai/cron/run/bogus/wechat")
    assert res.status_code == 404
    assert "unknown cron kind" in res.text


def test_cron_run_returns_uniform_callback_result(
    mxai_client: TestClient, monkeypatch
) -> None:
    """统一完成回调：每个 kind 都产出一致的 {success, message, result}（供 callback 用）。"""
    monkeypatch.setattr(
        "plugins.mxai.scheduler.benchmark_monitor.run_scheduled_touch_enqueue",
        lambda *a, **k: {"ok": True, "enqueued": 3, "skipped": None},
    )
    res = mxai_client.post("/api/plugins/mxai/cron/run/scheduled_touch/wechat")
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert "入队 3 条" in body["message"]  # 统一通知文案（投 channel 用）
    assert body["result"]["enqueued"] == 3


def test_cron_run_execution_end_invokes_callback(mxai_client: TestClient, monkeypatch) -> None:
    """执行端自己调 callback：callback URL 由执行器**执行时经 X-Cron-Callback 头传递进来**
    （不入配置），cron_run 跑完 POST 到该 URL 带 {success, message}。"""
    monkeypatch.setattr(
        "plugins.mxai.scheduler.benchmark_monitor.run_scheduled_touch_enqueue",
        lambda *a, **k: {"ok": True, "enqueued": 3},
    )
    posted: dict = {}

    class _R:
        status_code = 200
        text = "ok"

    def _fake(method, url, **kwargs):  # noqa: ANN001
        posted["url"] = url
        posted["json"] = kwargs.get("json")
        posted["headers"] = kwargs.get("headers")
        return _R()

    monkeypatch.setattr("httpx.request", _fake)
    res = mxai_client.post(
        "/api/plugins/mxai/cron/run/scheduled_touch/wechat",
        headers={
            "X-Cron-Callback": "http://127.0.0.1:8642/api/cron/jobs/mxai-wechat-scheduled_touch/callback",
            "X-Cron-Run-Id": "20260703-abc123",
            "X-Hub-Local-Token": "tok",
        },
    )
    assert res.status_code == 200
    body = res.json()
    # 同步响应：只含本次执行结果 + run_id，**不含** callback 结局（回调是异步的，另发）
    assert body["run_id"] == "20260703-abc123"
    assert "callback" not in body  # 回调不塞进同步响应
    # 回调走 BackgroundTasks：TestClient 在响应后跑后台任务，故已 POST 到 callback URL（带 run_id）
    assert posted["url"] == "http://127.0.0.1:8642/api/cron/jobs/mxai-wechat-scheduled_touch/callback"
    assert posted["json"]["success"] is True
    assert posted["json"]["run_id"] == "20260703-abc123"
    assert "入队 3 条" in posted["json"]["message"]
    assert posted["headers"].get("X-Hub-Local-Token") == "tok"  # 复用入站 IPC token 鉴权
