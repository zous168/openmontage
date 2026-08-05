"""8642 统一 API 文档（Dashboard + api_server）."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_cli.api_docs_routes import (
    api_server_openapi_document,
    render_unified_swagger_html,
    router as api_docs_router,
)
from hermes_cli.dashboard_auth.local_guard import local_guard_middleware


def test_render_unified_swagger_lists_both_specs() -> None:
    html = render_unified_swagger_html()
    assert "/openapi.json" in html
    assert "/openapi/api-server.json" in html
    assert "Dashboard 8642" in html
    assert "Agent API Server 18789" in html
    assert "SwaggerUIStandalonePreset" in html
    assert "StandaloneLayout" in html
    assert 'docExpansion: "none"' in html
    assert "defaultModelsExpandDepth: -1" in html
    assert "HUB_COMMON_TAGS" in html
    assert "expandCommonTags" in html
    assert "filter: true" in html


def test_api_server_openapi_document_uses_env_port(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_SERVER_PORT", "19999")
    monkeypatch.setenv("API_SERVER_HOST", "127.0.0.1")
    spec = api_server_openapi_document()
    assert spec["servers"][0]["url"] == "http://127.0.0.1:19999"
    assert "/v1/chat/completions" in spec["paths"]


def test_unified_docs_routes_on_8642(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()
    app.include_router(api_docs_router)
    app.state.hub_ipc_token_validator = lambda token: True
    app.middleware("http")(local_guard_middleware)

    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )

    client = TestClient(app)
    docs = client.get("/docs")
    assert docs.status_code == 200
    assert "swagger-ui" in docs.text

    spec = client.get("/openapi/api-server.json")
    assert spec.status_code == 200
    body = spec.json()
    assert body["openapi"] == "3.0.3"
    assert "/api/sessions" in body["paths"]


@pytest.fixture
def hub_data(tmp_path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    yield data_dir
