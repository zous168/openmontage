"""Agent model binding config + HTTP routes（CR-76）."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from plugins.mxai.agents.registry import AgentDefinition, AgentRegistry
from plugins.mxai.api.router import router as mxai_router
from plugins.mxai.cfg.agent_model_config import (
    get_agent_model,
    put_agent_model,
    resolve_profile_id_from_agent_ref,
)


@pytest.fixture(autouse=True)
def _register_agents():
    AgentRegistry.clear()
    AgentRegistry.register(
        AgentDefinition(profile_id="assistant", module="chat", clone_from="main")
    )
    AgentRegistry.register(
        AgentDefinition(profile_id="douyin", module="douyin", clone_from="main")
    )
    yield
    AgentRegistry.clear()


@pytest.fixture
def mxai_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.prompt_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    app = FastAPI()
    app.include_router(mxai_router, prefix="/api/plugins/mxai")
    from tests.conftest import arm_test_queue

    arm_test_queue()
    return TestClient(app)


def test_resolve_profile_id_from_agent_ref():
    # 渠道 key → 业务 Agent default；已是 Agent profile 则原样
    assert resolve_profile_id_from_agent_ref("wecom") == "qiyeweixin_chat"
    assert resolve_profile_id_from_agent_ref("qiyeweixin") == "qiyeweixin_chat"
    assert resolve_profile_id_from_agent_ref("douyin") == "douyin_comment"
    assert resolve_profile_id_from_agent_ref("qiyeweixin_chat") == "qiyeweixin_chat"
    assert resolve_profile_id_from_agent_ref(None) is None


def test_get_inherit_global_by_default(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._read_global_main_model",
        lambda: ("deepseek", "deepseek-chat"),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._load_global_model_options_payload",
        lambda: {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "providers": [{"slug": "deepseek", "authenticated": True}],
        },
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._effective_config_model",
        lambda _d: (None, None),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._read_config_model",
        lambda _d: (None, None),
    )
    data = get_agent_model("assistant")
    assert data["inherit_global"] is True
    assert data["effective_model"] == "deepseek-chat"
    assert data["global_model"] == "deepseek-chat"


def test_put_and_clear_binding(tmp_path: Path, monkeypatch) -> None:
    profile_dir = tmp_path / "douyin"
    profile_dir.mkdir(parents=True)
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._load_global_model_options_payload",
        lambda: {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "providers": [
                {"slug": "deepseek", "authenticated": True},
                {"slug": "ollama", "authenticated": True},
            ],
        },
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._read_global_main_model",
        lambda: ("deepseek", "deepseek-chat"),
    )

    written: list[tuple[str, str]] = []

    def fake_write(pdir: Path, provider: str, model: str) -> None:
        written.append((provider, model))
        cfg = {"model": {"provider": provider, "default": model}}
        (pdir / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")

    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._write_profile_main_model",
        fake_write,
    )

    def eff_model(pdir: Path):
        cfg_path = pdir / "config.yaml"
        if cfg_path.is_file():
            cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            m = cfg.get("model") or {}
            if isinstance(m, dict) and m.get("default"):
                return m.get("default"), m.get("provider")
        return "deepseek-chat", "deepseek"

    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._effective_config_model",
        eff_model,
    )

    def read_local(pdir: Path):
        cfg_path = pdir / "config.yaml"
        if not cfg_path.is_file():
            return None, None
        cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
        m = cfg.get("model") or {}
        if not isinstance(m, dict) or not m.get("default"):
            return None, None
        return m.get("default"), m.get("provider")

    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._read_config_model",
        read_local,
    )

    out = put_agent_model("douyin", provider="ollama", model="qwen2.5:7b")
    assert written == [("ollama", "qwen2.5:7b")]
    assert out["inherit_global"] is False
    assert out["provider"] == "ollama"
    assert out["model"] == "qwen2.5:7b"
    # 独立绑定时 effective 须与本地一致，不能仍回退全局 deepseek
    assert out["effective_provider"] == "ollama"
    assert out["effective_model"] == "qwen2.5:7b"

    cleared = put_agent_model("douyin", inherit_global=True)
    assert cleared["inherit_global"] is True
    if (profile_dir / "config.yaml").exists():
        cfg = yaml.safe_load((profile_dir / "config.yaml").read_text(encoding="utf-8")) or {}
        assert "model" not in cfg


def test_effective_uses_local_when_not_inheriting(tmp_path: Path, monkeypatch) -> None:
    """独立绑定时 effective 须跟本地 model 段，勿被 load_config 全局合并覆盖."""
    profile_dir = tmp_path / "assistant"
    profile_dir.mkdir(parents=True)
    (profile_dir / "config.yaml").write_text(
        yaml.safe_dump({"model": {"provider": "zai", "default": "glm-4-flash"}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._read_global_main_model",
        lambda: ("deepseek", "deepseek-v4-flash"),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._load_global_model_options_payload",
        lambda: {
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "providers": [
                {"slug": "deepseek", "authenticated": True},
                {"slug": "zai", "authenticated": True},
            ],
        },
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._read_config_model",
        lambda pdir: ("glm-4-flash", "zai") if pdir == profile_dir else (None, None),
    )
    # 模拟 load_config 合并仍返回全局主模型
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._effective_config_model",
        lambda _d: ("deepseek-v4-flash", "deepseek"),
    )

    data = get_agent_model("assistant")
    assert data["inherit_global"] is False
    assert data["provider"] == "zai"
    assert data["model"] == "glm-4-flash"
    assert data["effective_provider"] == "zai"
    assert data["effective_model"] == "glm-4-flash"


def test_put_rejects_unauthenticated_provider(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config.get_profile_dir",
        lambda pid: tmp_path / pid,
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._load_global_model_options_payload",
        lambda: {"providers": [{"slug": "deepseek", "authenticated": False}]},
    )
    with pytest.raises(HTTPException) as exc:
        put_agent_model("assistant", provider="deepseek", model="deepseek-chat")
    assert exc.value.status_code == 422


def test_agent_model_http_routes(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._read_global_main_model",
        lambda: ("deepseek", "deepseek-chat"),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._load_global_model_options_payload",
        lambda: {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "providers": [{"slug": "deepseek", "authenticated": True}],
        },
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._effective_config_model",
        lambda _d: (None, None),
    )
    monkeypatch.setattr(
        "plugins.mxai.cfg.agent_model_config._read_config_model",
        lambda _d: (None, None),
    )
    res = mxai_client.get("/api/plugins/mxai/agents/assistant/model")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["profile_id"] == "assistant"
    assert body["inherit_global"] is True
