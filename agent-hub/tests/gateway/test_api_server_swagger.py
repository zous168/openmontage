"""api_server OpenAPI / Swagger 文档端点."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

from gateway.platforms.api_server import (
    APIServerAdapter,
    build_api_server_openapi_spec,
    render_api_server_swagger_html,
)


def test_build_openapi_spec_contains_key_paths() -> None:
    spec = build_api_server_openapi_spec(host="127.0.0.1", port=18789)
    paths = spec["paths"]
    assert "/v1/chat/completions" in paths
    assert "post" in paths["/v1/chat/completions"]
    assert paths["/v1/chat/completions"]["post"].get("security") == [{"bearerAuth": []}]
    assert "/api/sessions" in paths
    assert "/health" in paths
    assert paths["/health"]["get"].get("security") is None
    assert spec["servers"][0]["url"] == "http://127.0.0.1:18789"
    assert "bearerAuth" in spec["components"]["securitySchemes"]


def test_render_swagger_html_points_at_openapi() -> None:
    html = render_api_server_swagger_html()
    assert "/openapi.json" in html
    assert "swagger-ui" in html
    assert "persistAuthorization" in html


def test_openapi_handler_no_auth() -> None:
    adapter = APIServerAdapter(MagicMock())
    adapter._host = "127.0.0.1"
    adapter._port = 18789
    request = MagicMock()

    async def _run():
        return await adapter._handle_openapi(request)

    resp = asyncio.run(_run())
    assert resp.status == 200
    data = json.loads(resp.body.decode())
    assert data["openapi"] == "3.0.3"
    assert "/v1/chat/completions" in data["paths"]


def test_swagger_docs_handler_returns_html() -> None:
    adapter = APIServerAdapter(MagicMock())
    request = MagicMock()

    async def _run():
        return await adapter._handle_swagger_docs(request)

    resp = asyncio.run(_run())
    assert resp.status == 200
    assert "text/html" in resp.content_type
    assert b"swagger-ui" in resp.body


def test_models_still_requires_auth() -> None:
    adapter = APIServerAdapter(MagicMock())
    adapter._api_key = "secret-key"
    request = MagicMock()
    request.headers = {}

    async def _run():
        return await adapter._handle_models(request)

    resp = asyncio.run(_run())
    assert resp.status == 401
