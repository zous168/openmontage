"""LLM credential / model hot-reload helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from starlette.testclient import TestClient


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
def hub_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "hub"
    root.mkdir()
    (root / "config.yaml").write_text(
        "model:\n  provider: moark\n  default: old-model\n",
        encoding="utf-8",
    )
    (root / ".env").write_text("", encoding="utf-8")
    _seed_device_session(root)

    import runtime_paths as rp_mod

    monkeypatch.setattr(rp_mod, "resolve_hub_data_dir_path", lambda: root)
    monkeypatch.setenv("HUB_DATA_DIR", str(root))
    monkeypatch.delenv("HERMES_PROFILE", raising=False)
    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )

    from core.platform.device.local_ipc import get_or_create_ipc_token
    from main import app

    client = TestClient(app, base_url="http://127.0.0.1:8642")
    headers = {
        "Host": "127.0.0.1:8642",
        "X-Hub-Local-Token": get_or_create_ipc_token(),
    }
    return client, headers, root


def test_apply_llm_runtime_reload(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("hermes_cli.config.reload_env", lambda: 2)

    fake_proc = MagicMock()
    fake_proc.pid = 4242
    monkeypatch.setattr(
        "hermes_cli.web_routes.helpers.spawn_gateway_restart",
        lambda: (fake_proc, False),
    )

    from hermes_cli.web_routes.helpers import apply_llm_runtime_reload

    result = apply_llm_runtime_reload()

    assert result["env_reloaded"] == 2
    assert result["gateway_restart_started"] is True
    assert result["gateway_restart_pid"] == 4242
    assert result["gateway_restart_reused"] is False


def test_model_set_global_main_triggers_reload(hub_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, headers, _root = hub_client
    reload_calls: list[int] = []

    monkeypatch.setattr(
        "hermes_cli.web_routes.config.apply_llm_runtime_reload",
        lambda: reload_calls.append(1)
        or {
            "env_reloaded": 1,
            "gateway_restart_started": True,
            "gateway_restart_pid": 99,
        },
    )

    response = client.post(
        "/api/model/set",
        headers=headers,
        json={
            "scope": "main",
            "provider": "moark",
            "model": "moark-acceptance-placeholder",
            "confirm_expensive_model": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["gateway_restart_started"] is True
    assert reload_calls == [1]


def test_model_set_profile_patch_triggers_reload(hub_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, headers, root = hub_client
    profile_dir = root / "profiles" / "douyin"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text("model: profile-old\n", encoding="utf-8")

    reload_calls: list[int] = []

    monkeypatch.setattr(
        "hermes_cli.web_routes.config.apply_llm_runtime_reload",
        lambda: reload_calls.append(1) or {"env_reloaded": 1, "gateway_restart_started": True},
    )

    response = client.post(
        "/api/model/set?profile=douyin",
        headers=headers,
        json={
            "scope": "main",
            "provider": "moark",
            "model": "profile-new",
            "confirm_expensive_model": True,
        },
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert reload_calls == [1]


def test_put_env_llm_key_triggers_reload(hub_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, headers, _root = hub_client
    reload_calls: list[int] = []

    monkeypatch.setattr(
        "hermes_cli.web_routes.config.apply_llm_runtime_reload",
        lambda: reload_calls.append(1)
        or {"env_reloaded": 1, "gateway_restart_started": True},
    )

    response = client.put(
        "/api/env",
        headers=headers,
        json={"key": "MOARK_API_KEY", "value": "sk-test"},
    )

    assert response.status_code == 200
    assert response.json()["gateway_restart_started"] is True
    assert reload_calls == [1]


def test_put_env_non_llm_key_skips_reload(hub_client, monkeypatch: pytest.MonkeyPatch) -> None:
    client, headers, _root = hub_client
    reload_calls: list[int] = []

    monkeypatch.setattr(
        "hermes_cli.web_routes.config.apply_llm_runtime_reload",
        lambda: reload_calls.append(1) or {"env_reloaded": 1},
    )

    response = client.put(
        "/api/env",
        headers=headers,
        json={"key": "FIRECRAWL_API_KEY", "value": "fc-test"},
    )

    assert response.status_code == 200
    assert response.json().get("gateway_restart_started") is None
    assert reload_calls == []


def test_env_key_touches_llm_runtime() -> None:
    from hermes_cli.config import env_key_touches_llm_runtime

    assert env_key_touches_llm_runtime("MOARK_API_KEY") is True
    assert env_key_touches_llm_runtime("DASHSCOPE_BASE_URL") is True
    assert env_key_touches_llm_runtime("FIRECRAWL_API_KEY") is False
    assert env_key_touches_llm_runtime("TERMINAL_ENV") is False
