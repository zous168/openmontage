"""本机 IPC 门禁 + 营销租户注入（Marketing Hub 集成 Dashboard）.

Hub 集成模式下本模块为**唯一**鉴权门禁（IPC + 设备登录 + tenant 注入）；
``gated_auth_middleware`` 在 ``hub_ipc_token_validator`` 已配置时为 no-op。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from urllib.parse import quote

from fastapi import Request, Response
from fastapi.responses import JSONResponse, RedirectResponse

from core.platform.device.local_device_auth import LocalDeviceAuthStore
from core.platform.device.local_ipc import validate_ipc_token as _default_validate_ipc_token
from core.platform.tenant_context import current_tenant_id_var
from hermes_cli.dashboard_auth.public_paths import PUBLIC_API_PATHS

DEV_IPC_PATH = "/api/auth/dev/local-ipc-token"
LOGIN_PATH = "/login"
HEALTH_PATH = "/health"
IPC_TOKEN_COOKIE = "local_ipc_token"

# FastAPI 自带 OpenAPI/Swagger（§10 活契约）；本机免 IPC，非本机拒绝。
_PUBLIC_DOCS_EXACT_PATHS: frozenset[str] = frozenset({
    "/docs",
    "/redoc",
    "/openapi.json",
    "/docs/oauth2-redirect",
    "/openapi/api-server.json",
})
_PUBLIC_DOCS_PREFIXES: tuple[str, ...] = (
    "/docs/",
    "/redoc/",
)

_PUBLIC_AUTH_PREFIXES: tuple[str, ...] = (
    LOGIN_PATH,
    "/auth/",
    "/api/auth/",
)

_PUBLIC_STATIC_PREFIXES: tuple[str, ...] = (
    "/assets/",
    "/favicon.ico",
    "/fonts/",
    "/fonts-terminal/",
    "/ds-assets/",
)

_ROUTE_AUTH_PREFIXES: tuple[str, ...] = (
    "/api/v1/ingest",
    "/ws/realtime",
)

# MxAI 统一 WS（GUI + RPA Worker）；本机升级免 IPC，由 ws handler 首包分流
_MXAI_WS_EXACT_PATHS: frozenset[str] = frozenset({
    "/api/v1/ws",
    "/api/plugins/mxai/ws",
    "/api/plugins/mxai/rpa/ws",
})

# 本机已设备登录时，Gateway 启停允许免 IPC（浏览器 SPA 常无 X-Hub-Local-Token）。
_GATEWAY_CONTROL_PATHS: frozenset[str] = frozenset({
    "/api/gateway/start",
    "/api/gateway/stop",
    "/api/gateway/restart",
})

_LOCALHOST = frozenset({"127.0.0.1", "::1", "localhost"})


def _ipc_configured(request: Request) -> bool:
    return callable(getattr(request.app.state, "hub_ipc_token_validator", None))


def _client_is_local(request: Request) -> bool:
    client = request.client
    if client is None:
        return False
    return (client.host or "").lower() in _LOCALHOST


def _path_matches_prefix(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix or path.startswith(prefix) for prefix in prefixes)


def _is_public_auth_path(path: str) -> bool:
    if path == DEV_IPC_PATH or path == HEALTH_PATH:
        return True
    return _path_matches_prefix(path, _PUBLIC_AUTH_PREFIXES)


def _is_public_static_path(path: str) -> bool:
    return _path_matches_prefix(path, _PUBLIC_STATIC_PREFIXES)


def is_public_docs_path(path: str) -> bool:
    """FastAPI Swagger/Redoc/OpenAPI 文档路径（本机可免 IPC 访问）。"""
    if path in _PUBLIC_DOCS_EXACT_PATHS:
        return True
    return _path_matches_prefix(path, _PUBLIC_DOCS_PREFIXES)


def is_hub_gated_public_path(request: Request) -> bool:
    """OAuth gated 模式下本机可直通的文档/健康/登录引导路径。"""
    if not _client_is_local(request):
        return False
    path = request.url.path
    if is_public_docs_path(path):
        return True
    return _is_public_auth_path(path)


def is_mxai_websocket_path(path: str) -> bool:
    return path in _MXAI_WS_EXACT_PATHS


def is_mxai_ws_local_upgrade(request: Request) -> bool:
    """本机 WebSocket 升级至 MxAI 统一端点 — 免 dashboard IPC（RPA Mock / agent-client）."""
    if not is_mxai_websocket_path(request.url.path):
        return False
    if (request.headers.get("upgrade") or "").lower() != "websocket":
        return False
    return _client_is_local(request)


def _has_route_level_auth(path: str) -> bool:
    if is_mxai_websocket_path(path):
        return True
    return _path_matches_prefix(path, _ROUTE_AUTH_PREFIXES)


def _hub_bootstrap_api_paths(request: Request) -> tuple[str, ...]:
    return tuple(getattr(request.app.state, "hub_public_prefixes", ()) or ())


def _is_ipc_bootstrap_path(request: Request, path: str) -> bool:
    """拿 IPC token / 设备登录之前的引导路径（免 IPC）。"""
    if path == DEV_IPC_PATH or path == HEALTH_PATH:
        return True
    if path == "/api/auth/providers":
        return True
    if _path_matches_prefix(path, (LOGIN_PATH, "/auth/")):
        return True
    return any(
        path == prefix or path.startswith(prefix)
        for prefix in _hub_bootstrap_api_paths(request)
    )


def _is_ipc_exempt_path(request: Request, path: str) -> bool:
    """免 IPC 的路径（仍可能要求本机 loopback）。"""
    if _has_route_level_auth(path):
        return True
    if _is_public_static_path(path):
        return True
    if is_public_docs_path(path):
        return True
    if _is_ipc_bootstrap_path(request, path):
        return True
    if path in PUBLIC_API_PATHS:
        return True
    return False


def extract_ipc_credential(request: Request) -> str | None:
    """IPC 提取（header → Bearer → cookie）."""
    header = request.headers.get("X-Hub-Local-Token")
    if header and header.strip():
        return header.strip()
    auth = request.headers.get("authorization") or request.headers.get("Authorization")
    if auth and auth.lower().startswith("bearer "):
        bearer = auth.split(" ", 1)[1].strip()
        if bearer and bearer.count(".") < 2:
            return bearer
    cookie = request.cookies.get(IPC_TOKEN_COOKIE)
    if cookie and cookie.strip():
        return cookie.strip()
    for key in ("token", "hub_local_token"):
        query_token = request.query_params.get(key)
        if query_token and query_token.strip():
            return query_token.strip()
    return None


def _validate_ipc_token(request: Request, token: str | None) -> bool:
    validator = getattr(request.app.state, "hub_ipc_token_validator", None)
    if callable(validator):
        try:
            return bool(validator(token))
        except Exception:  # noqa: BLE001
            return False
    return _default_validate_ipc_token(token)


def _prefers_html_login(request: Request) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    accept = (request.headers.get("accept") or "").lower()
    return "text/html" in accept and not accept.strip().startswith("application/json")


# 401 codes that mean "redirect to /login" (HTML) or return login_url (API JSON).
_AUTH_REDIRECT_CODES: frozenset[str] = frozenset({
    "device_not_logged_in",
    "local_token_missing",
    "local_token_invalid",
})


def _needs_tenant(path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    if path.startswith("/api/auth/"):
        return False
    if path in PUBLIC_API_PATHS:
        return False
    return True


def _needs_device_login(path: str) -> bool:
    """业务 API 与 SPA 路由须设备已登录；bootstrap / 只读公开 API 除外。"""
    if _needs_tenant(path):
        return True
    if not path.startswith("/api/"):
        return True
    return False


def _device_logged_in() -> bool:
    from core.platform.device.device_auth_service import ensure_device_access_fresh

    ensure_device_access_fresh()
    return bool(LocalDeviceAuthStore().tenant_id)


def _login_url(request: Request) -> str:
    """Build ``/login?next=...`` for SPA routes; bare ``/login`` for ``/api/*``.

    Mirrors ``gated_auth_middleware._safe_next_target``: never put an API URL
    in ``next=`` — after login the user would see raw JSON, not the dashboard.
    """
    path = request.url.path
    if path == "/api" or path.startswith("/api/"):
        return LOGIN_PATH
    if path == LOGIN_PATH or path.startswith("/auth/") or path.startswith("/api/auth/"):
        return LOGIN_PATH
    next_target = path
    query = request.url.query
    if query:
        next_target = f"{path}?{query}"
    return f"{LOGIN_PATH}?next={quote(next_target, safe='')}"


def _guard_json(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
) -> JSONResponse | RedirectResponse:
    if status_code == 401:
        from hermes_cli.dashboard_auth.auth_diag import log_auth_denial

        log_auth_denial(
            request,
            layer="local_guard",
            code=code,
            message=message,
            spa_route=not request.url.path.startswith("/api/"),
        )
    if status_code == 401 and code in _AUTH_REDIRECT_CODES:
        login_url = _login_url(request)
        if _prefers_html_login(request) and request.url.path != LOGIN_PATH:
            resp = RedirectResponse(url=login_url, status_code=302)
            if code == "local_token_invalid":
                resp.delete_cookie(IPC_TOKEN_COOKIE, path="/")
            return resp
        if request.url.path.startswith("/api/"):
            trace_id = getattr(request.state, "trace_id", None)
            error_code = (
                "session_expired"
                if code == "local_token_invalid"
                else "unauthenticated"
            )
            return JSONResponse(
                status_code=401,
                content={
                    "error": error_code,
                    "detail": {"code": code, "message": message},
                    "login_url": login_url,
                    "trace_id": trace_id,
                },
            )
    trace_id = getattr(request.state, "trace_id", None)
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": {"code": code, "message": message},
            "trace_id": trace_id,
        },
    )


def _require_localhost(request: Request) -> JSONResponse | RedirectResponse | None:
    if _client_is_local(request):
        return None
    return _guard_json(
        request,
        status_code=403,
        code="local_forbidden",
        message="local API is localhost only",
    )


def _require_ipc(request: Request) -> JSONResponse | RedirectResponse | None:
    token = extract_ipc_credential(request)
    if not token:
        return _guard_json(
            request,
            status_code=401,
            code="local_token_missing",
            message="X-Hub-Local-Token or Authorization Bearer required",
        )
    if not _validate_ipc_token(request, token):
        return _guard_json(
            request,
            status_code=401,
            code="local_token_invalid",
            message="invalid local IPC token",
        )
    request.state.hub_ipc_authenticated = True
    return None


def _inject_tenant(path: str) -> object | None:
    from core.platform.device.device_auth_service import ensure_device_access_fresh

    ensure_device_access_fresh()
    tenant_id = LocalDeviceAuthStore().tenant_id
    if not tenant_id:
        return None
    return current_tenant_id_var.set(tenant_id)


async def local_guard_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    """本机 IPC + 设备登录统一门禁；受保护 ``/api/*`` 注入 tenant_id。

    未配置 ``hub_ipc_token_validator`` 时为 no-op（独立 Hermes dashboard）。
    """
    if not _ipc_configured(request):
        return await call_next(request)

    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path

    if _is_ipc_exempt_path(request, path):
        denied = _require_localhost(request)
        if denied is not None:
            return denied
        return await call_next(request)

    denied = _require_localhost(request)
    if denied is not None:
        return denied

    # 本机 + 设备已登录：Gateway 启停免 IPC（与 lifespan 自启互补，供设置页按钮）。
    if path in _GATEWAY_CONTROL_PATHS and _device_logged_in():
        request.state.hub_ipc_authenticated = True
    else:
        denied = _require_ipc(request)
        if denied is not None:
            return denied

    if _needs_device_login(path):
        if not _device_logged_in():
            return _guard_json(
                request,
                status_code=401,
                code="device_not_logged_in",
                message="call POST /api/auth/login first",
            )

    tenant_token = None
    if _needs_tenant(path):
        tenant_token = _inject_tenant(path)
        if tenant_token is None:
            return _guard_json(
                request,
                status_code=401,
                code="device_not_logged_in",
                message="call POST /api/auth/login first",
            )

    try:
        return await call_next(request)
    finally:
        if tenant_token is not None:
            current_tenant_id_var.reset(tenant_token)
