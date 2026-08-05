"""LT-013 配置持久化收口测试."""

from pathlib import Path

from fastapi.testclient import TestClient

from plugins.mxai.orchestrator.queue_manager import QueueManager


def test_lt013_workbench_scheduled(mxai_client: TestClient) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/agents/wechat/workbench",
        json={
            "data": {
                "scheduled_touch": {
                    "time": "10:30",
                    "message": "王总，方案整理好了",
                    "recipient": "存量客户",
                },
            },
        },
    )
    assert put.status_code == 200
    data = put.json()["data"]["scheduled_touch"]
    assert data["time"] == "10:30"
    assert data["message"] == "王总，方案整理好了"

    post = mxai_client.post(
        "/api/plugins/mxai/agents/wechat/tasks/scheduled-msg",
        json={"recipient": "客户A", "message": "回访话术", "time": "15:00", "run_now": True},
    )
    assert post.status_code == 200
    get = mxai_client.get("/api/plugins/mxai/agents/wechat/workbench").json()
    touch = get["data"]["scheduled_touch"]
    assert touch["message"] == "回访话术"
    assert touch["time"] == "15:00"


def test_lt013_run_agents_persist(mxai_client: TestClient) -> None:
    pause = mxai_client.post("/api/plugins/mxai/run/agents/douyin/pause")
    assert pause.status_code == 200
    assert pause.json()["enabled"] is False

    agents = mxai_client.get("/api/plugins/mxai/run/agents").json()
    assert agents["agents"]["douyin"]["enabled"] is False

    QueueManager.reset()
    agents2 = mxai_client.get("/api/plugins/mxai/run/agents").json()
    assert agents2["agents"]["douyin"]["enabled"] is False

    start = mxai_client.post("/api/plugins/mxai/run/agents/douyin/start")
    assert start.status_code == 200
    assert start.json()["enabled"] is True


def test_agent_start_does_not_unpause_global_queue(mxai_client) -> None:
    mxai_client.post("/api/plugins/mxai/queue/pause")
    assert mxai_client.get("/api/plugins/mxai/queue/summary").json()["paused"] is True

    mxai_client.post("/api/plugins/mxai/run/agents/douyin/start")
    assert mxai_client.get("/api/plugins/mxai/queue/summary").json()["paused"] is True

    mxai_client.post("/api/plugins/mxai/run/all/start")
    assert mxai_client.get("/api/plugins/mxai/queue/summary").json()["paused"] is False


def test_lt013_client_settings(mxai_client: TestClient) -> None:
    rejected = mxai_client.put(
        "/api/plugins/mxai/settings/client",
        json={"worklog_keep_days": 45, "max_concurrent": 8, "model_mode": "cloud"},
    )
    assert rejected.status_code == 422

    put = mxai_client.put(
        "/api/plugins/mxai/settings/client",
        json={"worklog_keep_days": 45, "max_concurrent": 8},
    )
    assert put.status_code == 200
    s = put.json()["settings"]
    assert s["worklog_keep_days"] == 45
    assert s["max_concurrent"] == 8
    assert "model_mode" not in s

    get = mxai_client.get("/api/plugins/mxai/settings/client").json()
    assert get["settings"]["worklog_keep_days"] == 45


def test_lt013_client_settings_ui_prefs(mxai_client: TestClient) -> None:
    put = mxai_client.put(
        "/api/plugins/mxai/settings/client",
        json={
            "theme_mode": "dark",
            "locale": "en",
            "pet_visible": False,
            "pet_size": 100,
            "pet_effect": "low",
            "sys_service": False,
        },
    )
    assert put.status_code == 200
    get = mxai_client.get("/api/plugins/mxai/settings/client").json()
    assert get["settings"]["theme_mode"] == "dark"
    assert get["settings"]["locale"] == "en"
    assert get["settings"]["pet_visible"] is False
    assert get["settings"]["pet_size"] == 100
    assert get["settings"]["pet_effect"] == "low"


def test_lt013_client_settings_assistant_ui_mode(mxai_client: TestClient) -> None:
    default = mxai_client.get("/api/plugins/mxai/settings/client").json()
    assert default["settings"]["assistant_ui_mode"] == "floating"

    put = mxai_client.put(
        "/api/plugins/mxai/settings/client",
        json={"assistant_ui_mode": "menu"},
    )
    assert put.status_code == 200
    assert put.json()["settings"]["assistant_ui_mode"] == "menu"


def test_lt013_queue_pause_persist(mxai_client: TestClient) -> None:
    pause = mxai_client.post("/api/plugins/mxai/queue/pause")
    assert pause.status_code == 200
    assert pause.json()["paused"] is True

    summary = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary["paused"] is True

    QueueManager.reset()
    summary2 = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary2["paused"] is True

    mxai_client.post("/api/plugins/mxai/run/all/start")
    summary3 = mxai_client.get("/api/plugins/mxai/queue/summary").json()
    assert summary3["paused"] is False


def test_lt013_data_dir(mxai_client: TestClient) -> None:
    res = mxai_client.get("/api/plugins/mxai/settings/data-dir")
    assert res.status_code == 200
    path = res.json()["path"]
    assert path
    assert Path(path).is_dir()
