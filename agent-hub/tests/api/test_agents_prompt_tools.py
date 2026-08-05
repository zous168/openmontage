"""agents prompt/tools HTTP routes（CR-74）."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentDefinition, AgentRegistry
from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.mcp_tools import MXAI_PER_TOOL_TOOLSETS
from plugins.mxai.cfg.prompt_config import seed_prompt_files


@pytest.fixture
def mxai_client(tmp_path: Path, monkeypatch) -> TestClient:
    AgentRegistry.clear()
    AgentRegistry.register(
        AgentDefinition(profile_id="assistant", module="chat", clone_from="main")
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.prompt_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    # prompt/tools 只读路由不依赖队列武装；避免无 mxai_env 时 arm_work 拉配置失败
    return TestClient(app)


def test_assistant_tools_route_registered(mxai_client: TestClient, tmp_path: Path) -> None:
    profile_dir = tmp_path / "assistant"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        "platform_toolsets:\n  api_server: [hermes-api-server, mxai]\n",
        encoding="utf-8",
    )
    res = mxai_client.get("/api/plugins/mxai/agents/assistant/tools")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["profile_id"] == "assistant"
    assert body["toolsets"] == list(MXAI_PER_TOOL_TOOLSETS)
    assert "tools" in body
    assert "groups" in body
    names = {t["name"] for t in body["tools"]}
    assert "web_search" not in names


def test_assistant_prompt_route_registered(mxai_client: TestClient, tmp_path: Path) -> None:
    seed_prompt_files(tmp_path / "assistant", "assistant")
    res = mxai_client.get("/api/plugins/mxai/agents/assistant/prompt")
    assert res.status_code == 200, res.text
    assert res.json()["profile_id"] == "assistant"


def test_tools_route_forbidden_when_module_not_entitled(
    mxai_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        "core.platform.device.device_auth_service.is_profile_entitled",
        lambda pid: pid != "boss",
    )
    AgentRegistry.register(
        AgentDefinition(profile_id="boss", module="rpa", clone_from="main")
    )
    profile_dir = tmp_path / "boss"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        "platform_toolsets:\n  api_server: [mxai]\n",
        encoding="utf-8",
    )
    res = mxai_client.get("/api/plugins/mxai/agents/boss/tools")
    assert res.status_code == 403, res.text
    assert "not entitled" in res.json()["detail"]
