"""LT-001 A1：Gateway 实载 mxai 插件集成烟测."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def _seed_device_session(data_dir: Path) -> None:
    device_dir = data_dir / "device"
    device_dir.mkdir(parents=True, exist_ok=True)
    (device_dir / "device_auth.json").write_text(
        json.dumps(
            {
                "user_id": "test-user",
                "login_name": "tester",
                "tenant_id": "test-tenant",
                "tenant_name": "Test",
                "device_id": "test-device",
                "access_token": "test-access",
                "expires_at": 9999999999.0,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def gateway_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    profiles = data_dir / "profiles"
    profiles.mkdir()
    main = profiles / "main"
    main.mkdir()
    (main / "config.yaml").write_text("model: test\n", encoding="utf-8")
    _seed_device_session(data_dir)

    def fake_create(name: str, **kwargs: object) -> Path:
        d = profiles / name
        d.mkdir(parents=True, exist_ok=True)
        if not (d / "config.yaml").exists():
            (d / "config.yaml").write_text("model: test\n", encoding="utf-8")
        return d

    monkeypatch.setattr("hermes_cli.profiles.create_profile", fake_create)
    monkeypatch.setattr(
        "hermes_cli.profiles.profile_exists",
        lambda name: (profiles / name).is_dir(),
    )
    monkeypatch.setattr(
        "hermes_cli.profiles.get_profile_dir",
        lambda name: profiles / name,
    )
    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )

    from main import app

    return TestClient(app, base_url="http://127.0.0.1:8642")


@pytest.fixture
def ipc_headers(gateway_client: TestClient) -> dict[str, str]:
    from core.platform.device.local_ipc import get_or_create_ipc_token

    _ = gateway_client
    return {"X-Hub-Local-Token": get_or_create_ipc_token()}


def test_gateway_health(gateway_client: TestClient, ipc_headers: dict[str, str]) -> None:
    headers = {"Host": "127.0.0.1:8642", "Accept": "application/json", **ipc_headers}
    resp = gateway_client.get("/health", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_gateway_mxai_cron_run_uses_standard_ipc_auth(
    gateway_client: TestClient, ipc_headers: dict[str, str]
) -> None:
    """CR-132：cron 执行入口走 **MxAI 标准 IPC token 鉴权**（与其它 mxai 路由一致），
    不自建 api_server_key、不豁免鉴权门。带 IPC token → 穿全部门到达端点；无 token → 401。"""
    # 带 IPC token（mxai 标准鉴权）→ 到达端点本身（unknown kind → 端点自身 404）
    r = gateway_client.post(
        "/api/plugins/mxai/cron/run/bogus/default",
        headers={"Host": "127.0.0.1:8642", **ipc_headers},
    )
    assert r.status_code == 404
    assert "unknown cron kind" in r.text
    # 无 token → 被 dashboard 鉴权门挡（端点不可达）
    r2 = gateway_client.post(
        "/api/plugins/mxai/cron/run/bogus/default",
        headers={"Host": "127.0.0.1:8642"},
    )
    assert r2.status_code == 401


def test_gateway_mxai_bootstrap_status(
    gateway_client: TestClient, ipc_headers: dict[str, str]
) -> None:
    headers = {"Host": "127.0.0.1:8642", **ipc_headers}
    resp = gateway_client.get("/api/plugins/mxai/bootstrap/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["databases"]) == 4
    assert len(body["profiles"]) == 7


def test_gateway_mxai_bootstrap_status_without_ipc(
    gateway_client: TestClient,
) -> None:
    """splash 登录前：localhost 可读 bootstrap，无需 IPC / 设备会话。"""
    headers = {"Host": "127.0.0.1:8642", "Accept": "application/json"}
    resp = gateway_client.get("/api/plugins/mxai/bootstrap/status", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "ok" in body
    assert "failed" in body
