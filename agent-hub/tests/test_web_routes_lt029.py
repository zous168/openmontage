"""LT-029 acceptance: web_routes modularization smoke tests."""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest
from starlette.testclient import TestClient

WEB_ROUTES_MODULES = (
    "deps",
    "helpers",
    "memory",
    "credentials",
    "files",
    "status",
    "gateway",
    "config",
    "sessions",
    "oauth_messaging",
    "cron",
    "mcp",
    "pairing_webhooks",
    "ops",
    "skills",
    "profiles",
    "misc",
    "dashboard_plugins",
)

KEY_OPENAPI_PATHS = (
    "/api/status",
    "/api/memory",
    "/api/config",
    "/api/sessions",
    "/api/profiles",
    "/api/gateway/restart",
    "/api/cron/jobs",
    "/api/mcp/servers",
    "/api/pairing",
    "/api/webhooks",
    "/api/skills/hub/sources",
    "/api/credentials/pool",
    "/api/dashboard/plugins",
    "/api/dashboard/plugins/hub",
)


@pytest.mark.parametrize("mod", WEB_ROUTES_MODULES)
def test_web_routes_module_imports(mod: str) -> None:
    importlib.import_module(f"hermes_cli.web_routes.{mod}")


def test_helpers_spawn_import() -> None:
    from hermes_cli.web_routes.helpers import spawn_hermes_action

    assert callable(spawn_hermes_action)


def test_web_server_has_no_app_rest_routes() -> None:
    web_server = Path(__file__).resolve().parents[1] / "src" / "hermes_cli" / "web_server.py"
    text = web_server.read_text(encoding="utf-8")
    rest = re.findall(r'@app\.(get|post|put|delete|patch)\("([^"]+)"', text)
    assert rest == [], f"unexpected @app REST in web_server: {rest}"


def test_mount_plugin_api_routes_callable() -> None:
    from hermes_cli.web_routes.dashboard_plugins import mount_plugin_api_routes

    assert callable(mount_plugin_api_routes)


def test_openapi_includes_modular_routes() -> None:
    from hermes_cli.web_server import app

    spec = app.openapi()
    paths = spec.get("paths", {})
    api_paths = [p for p in paths if p.startswith("/api/")]
    assert len(api_paths) >= 150
    for path in KEY_OPENAPI_PATHS:
        assert path in paths, f"missing openapi path: {path}"


@pytest.fixture
def client() -> TestClient:
    from hermes_cli.web_server import app

    return TestClient(app)


@pytest.mark.parametrize("path", ["/api/status"])
def test_public_or_reachable_get(client: TestClient, path: str) -> None:
    r = client.get(path)
    assert r.status_code in (200, 401)


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/config", "get"),
        ("/api/memory", "get"),
        ("/api/sessions", "get"),
        ("/api/profiles", "get"),
    ],
)
def test_auth_gated_routes_respond(client: TestClient, path: str, method: str) -> None:
    r = getattr(client, method)(path)
    assert r.status_code in (200, 401, 403)
