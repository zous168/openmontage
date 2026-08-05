"""Dashboard OpenAPI 注入 Hub IPC 鉴权方案."""

from __future__ import annotations

from fastapi import FastAPI

from hermes_cli.openapi_security import (
    HUB_LOCAL_BEARER_SCHEME,
    HUB_LOCAL_TOKEN_SCHEME,
    apply_hub_security_to_openapi_schema,
    install_hub_openapi_security,
)


def test_apply_hub_security_injects_schemes_and_global() -> None:
    schema = {
        "openapi": "3.0.3",
        "info": {"title": "t", "version": "1"},
        "paths": {
            "/api/credentials/pool": {
                "get": {"summary": "pool", "responses": {"200": {"description": "OK"}}},
            },
            "/api/status": {
                "get": {"summary": "status", "responses": {"200": {"description": "OK"}}},
            },
            "/api/auth/login": {
                "post": {"summary": "login", "responses": {"200": {"description": "OK"}}},
            },
            "/health": {
                "get": {"summary": "health", "responses": {"200": {"description": "OK"}}},
            },
        },
    }
    apply_hub_security_to_openapi_schema(schema)

    schemes = schema["components"]["securitySchemes"]
    assert HUB_LOCAL_TOKEN_SCHEME in schemes
    assert schemes[HUB_LOCAL_TOKEN_SCHEME]["name"] == "X-Hub-Local-Token"
    assert HUB_LOCAL_BEARER_SCHEME in schemes
    assert schema["security"] == [
        {HUB_LOCAL_TOKEN_SCHEME: []},
        {HUB_LOCAL_BEARER_SCHEME: []},
    ]
    assert "X-Hub-Local-Token" in schema["info"]["description"]

    assert schema["paths"]["/api/credentials/pool"]["get"]["security"] == schema["security"]
    assert schema["paths"]["/api/status"]["get"]["security"] == []
    assert schema["paths"]["/api/auth/login"]["post"]["security"] == []
    assert schema["paths"]["/health"]["get"]["security"] == []


def test_install_hub_openapi_security_idempotent() -> None:
    app = FastAPI(title="Hub", version="0.0.0")

    @app.get("/api/credentials/pool")
    def pool():
        return {"ok": True}

    @app.get("/api/status")
    def status():
        return {"ok": True}

    install_hub_openapi_security(app)
    install_hub_openapi_security(app)

    schema = app.openapi()
    assert HUB_LOCAL_TOKEN_SCHEME in schema["components"]["securitySchemes"]
    assert schema["paths"]["/api/credentials/pool"]["get"]["security"]
    assert schema["paths"]["/api/status"]["get"]["security"] == []
