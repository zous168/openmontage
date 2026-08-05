"""LT-014 ConfigManager + 运行时热生效测试."""

from plugins.mxai.cfg.manager import ConfigManager
from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_config_manager_core(mxai_client, mxai_env) -> None:
    mgr = ConfigManager.get()
    before_rev = mgr.revision("client_settings")
    snap = mgr.patch("client_settings", {"worklog_keep_days": 17})
    assert snap["worklog_keep_days"] == 17
    assert mgr.revision("client_settings") == before_rev + 1

    bad = mxai_client.patch(
        "/api/plugins/mxai/config/unknown.domain",
        json={"data": {"x": 1}},
    )
    assert bad.status_code == 404


def test_config_api(mxai_client) -> None:
    reg = mxai_client.get("/api/plugins/mxai/config/registry")
    assert reg.status_code == 200
    domains = {d["domain_id"] for d in reg.json()["domains"]}
    assert "client_settings" in domains
    assert "queue_state" not in domains

    get = mxai_client.get("/api/plugins/mxai/config/client_settings")
    assert get.status_code == 200
    body = get.json()
    assert body["domain"] == "client_settings"
    assert "snapshot" in body


def test_client_settings_adapter(mxai_client) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/settings/client",
        json={"theme_mode": "dark", "locale": "en"},
    )
    assert put.status_code == 200
    snap = ConfigManager.get().read("client_settings")
    assert snap["theme_mode"] == "dark"
    assert snap["locale"] == "en"


def test_queue_pause_via_rest(mxai_client) -> None:
    mxai_client.post("/api/plugins/mxai/queue/resume")
    qm = QueueManager.get()
    assert qm.summary()["paused"] is False

    mxai_client.post("/api/plugins/mxai/queue/pause")
    assert QueueManager.get().summary()["paused"] is True


def test_run_agents_via_rest(mxai_client) -> None:
    pause = mxai_client.post("/api/plugins/mxai/run/agents/douyin/pause")
    assert pause.status_code == 200
    qm = QueueManager.get()
    assert qm.is_agent_enabled("douyin") is False

    start = mxai_client.post("/api/plugins/mxai/run/agents/douyin/start")
    assert start.status_code == 200
    assert QueueManager.get().is_agent_enabled("douyin") is True


def test_agent_cfg_delegate(mxai_client) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/douyin/risk",
        json={"data": {"daily_dm_limit": 42, "enabled": True}},
    )
    assert put.status_code == 200
    snap = ConfigManager.get().read("agent.douyin.risk")
    assert snap["daily_dm_limit"] == 42


def test_workbench_delegate(mxai_client) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={"data": {"scheduled_touch": {"time": "09:00", "message": "hi"}}},
    )
    assert put.status_code == 200
    snap = ConfigManager.get().read("agent.wechat.workbench")
    assert snap["scheduled_touch"]["time"] == "09:00"


def test_config_subscribers_risk(mxai_client) -> None:
    from plugins.mxai.risk.engine import get_risk_limits

    mxai_client.put(
        "/api/plugins/mxai/agents/douyin/risk",
        json={"data": {"daily_dm_limit": 99}},
    )
    limits = get_risk_limits("douyin")
    assert limits["daily_dm_limit"] == 99


def test_config_hydrate_on_ready(mxai_client) -> None:
    reg = mxai_client.get("/api/plugins/mxai/config/registry").json()
    assert any(d["domain_id"] == "agent.douyin.risk" for d in reg["domains"])


def test_config_ws_updated(mxai_client) -> None:
    with mxai_client.websocket_connect("/api/plugins/mxai/ws") as ws:
        # 统一 WS 端点连接后先做 2s 角色探测（RPA vs GUI），探测结束才 register() 为 GUI 订阅者。
        # 若连接后立刻 PATCH，config.updated 广播会早于注册、无人接收 → receive_json 永久阻塞（CI 超时）。
        # 先发一帧 GUI 文本触发「立即注册 + 回 pong」，收到 pong 即确认已订阅，消除竞态。
        ws.send_text("ping")
        assert ws.receive_json()["event"] == "pong"
        mxai_client.patch(
            "/api/plugins/mxai/config/client_settings",
            json={"data": {"pet_visible": False}},
        )
        msg = ws.receive_json()
        assert msg["event"] == "config.updated"
        assert msg["data"]["domain"] == "client_settings"
        assert "pet_visible" in msg["data"]["changed_keys"] or msg["data"]["snapshot"]
