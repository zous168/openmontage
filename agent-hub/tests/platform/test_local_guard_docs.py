"""local_guard 放行本机 Swagger/OpenAPI 文档路径."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hermes_cli.dashboard_auth.local_guard import (
    is_public_docs_path,
    local_guard_middleware,
)


@pytest.mark.parametrize(
    "path",
    [
        "/docs",
        "/docs/",
        "/docs/dashboard",
        "/redoc",
        "/redoc/",
        "/redoc/dashboard",
        "/openapi.json",
        "/openapi/api-server.json",
        "/docs/oauth2-redirect",
    ],
)
def test_is_public_docs_path_true(path: str) -> None:
    assert is_public_docs_path(path) is True


def test_is_public_docs_path_false() -> None:
    assert is_public_docs_path("/memory") is False


def test_docs_localhost_passes_without_ipc(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()

    @app.get("/docs")
    async def docs_page():
        return {"swagger": True}

    @app.get("/openapi.json")
    async def openapi():
        return {"openapi": "3.0.3"}

    app.state.hub_ipc_token_validator = lambda token: True
    app.middleware("http")(local_guard_middleware)

    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )

    client = TestClient(app)
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_non_localhost_forbidden(hub_data, monkeypatch: pytest.MonkeyPatch) -> None:
    app = FastAPI()

    @app.get("/docs")
    async def docs_page():
        return {"swagger": True}

    app.state.hub_ipc_token_validator = lambda token: True
    app.middleware("http")(local_guard_middleware)

    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: False,
    )

    client = TestClient(app)
    res = client.get("/docs")
    assert res.status_code == 403
    assert res.json()["detail"]["code"] == "local_forbidden"


def test_gated_auth_allows_local_docs_without_login(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hermes_cli.dashboard_auth.middleware import gated_auth_middleware

    app = FastAPI()
    app.state.auth_required = True
    app.state.hub_ipc_token_validator = lambda token: True

    @app.get("/docs")
    async def docs():
        return {"swagger": True}

    @app.get("/openapi.json")
    async def openapi():
        return {"openapi": "3.0.3", "paths": {}}

    @app.get("/openapi/api-server.json")
    async def api_server_openapi():
        return {"openapi": "3.0.3", "paths": {"/health": {}}}

    app.middleware("http")(gated_auth_middleware)

    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: True,
    )

    client = TestClient(app)
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200
    assert client.get("/openapi/api-server.json").status_code == 200


def test_gated_auth_blocks_remote_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    """独立 OAuth gated 模式（无 Hub IPC）仍拦截远端文档访问。"""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from hermes_cli.dashboard_auth.middleware import gated_auth_middleware

    app = FastAPI()
    app.state.auth_required = True

    @app.get("/docs")
    async def docs():
        return {"swagger": True}

    app.middleware("http")(gated_auth_middleware)

    monkeypatch.setattr(
        "hermes_cli.dashboard_auth.local_guard._client_is_local",
        lambda request: False,
    )

    client = TestClient(app, follow_redirects=False)
    res = client.get("/docs", headers={"Accept": "text/html"})
    assert res.status_code == 302
    assert "/login" in res.headers.get("location", "")


@pytest.fixture
def hub_data(tmp_path, monkeypatch: pytest.MonkeyPatch):
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    yield data_dir
