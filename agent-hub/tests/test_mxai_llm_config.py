"""大模型配置：MxAI 只负责 ok 判断，env/model 走 Hermes 原生 API。"""

from fastapi.testclient import TestClient

from plugins.mxai.cfg.llm_config import (
    DEPRECATED_CLIENT_LLM_KEYS,
    llm_config_ok,
    migrate_client_settings_llm,
    read_llm_status,
)

_FAKE_OPTIONS = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "providers": [
        {"slug": "deepseek", "authenticated": True, "models": ["deepseek-chat"]},
        {"slug": "openai", "authenticated": False, "models": []},
    ],
}

_FAKE_OPTIONS_NO_MODEL = {
    "provider": "deepseek",
    "model": "",
    "providers": _FAKE_OPTIONS["providers"],
}

_FAKE_OPTIONS_UNAUTHENTICATED = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "providers": [{"slug": "deepseek", "authenticated": False, "models": ["deepseek-chat"]}],
}


def test_llm_config_ok_authenticated(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.llm_config._load_model_options_payload",
        lambda: dict(_FAKE_OPTIONS),
    )
    assert llm_config_ok() is True


def test_llm_config_ok_missing_model(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.llm_config._load_model_options_payload",
        lambda: dict(_FAKE_OPTIONS_NO_MODEL),
    )
    assert llm_config_ok() is False


def test_llm_config_ok_unauthenticated(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.llm_config._load_model_options_payload",
        lambda: dict(_FAKE_OPTIONS_UNAUTHENTICATED),
    )
    assert llm_config_ok() is False


def test_read_llm_status(monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.llm_config._load_model_options_payload",
        lambda: dict(_FAKE_OPTIONS),
    )
    status = read_llm_status()
    assert status == {"ok": True}


def test_llm_api_get(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.llm_config._load_model_options_payload",
        lambda: dict(_FAKE_OPTIONS),
    )
    resp = mxai_client.get("/api/plugins/mxai/config/llm")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"ok": True}


def test_llm_api_get_not_ok(mxai_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "plugins.mxai.cfg.llm_config._load_model_options_payload",
        lambda: dict(_FAKE_OPTIONS_UNAUTHENTICATED),
    )
    resp = mxai_client.get("/api/plugins/mxai/config/llm")
    assert resp.status_code == 200
    assert resp.json()["ok"] is False


def test_client_settings_rejects_llm(mxai_client: TestClient) -> None:
    resp = mxai_client.put(
        "/api/plugins/mxai/settings/client",
        json={"api_key": "sk-should-not-land-here"},
    )
    assert resp.status_code == 422


def test_migrate_strips_llm_keys() -> None:
    legacy = {
        "model_mode": "local",
        "provider": "ollama",
        "api_key": "sk-x",
        "ollama_path": "http://127.0.0.1:11434",
        "small_big_split": True,
        "locale": "zh",
        "theme": "dark",
    }
    result = migrate_client_settings_llm(dict(legacy))
    for key in DEPRECATED_CLIENT_LLM_KEYS:
        assert key not in result
    assert result["locale"] == "zh"
    assert result["theme"] == "dark"
