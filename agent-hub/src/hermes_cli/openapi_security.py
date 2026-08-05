"""Hub Dashboard OpenAPI 鉴权方案（Swagger Authorize）。

集成模式下为 ``/openapi.json`` 注入 ``X-Hub-Local-Token`` / Bearer IPC 安全方案，
与 ``local_guard_middleware`` 实际门禁对齐。
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi

from hermes_cli.dashboard_auth.public_paths import PUBLIC_API_PATHS

HUB_LOCAL_TOKEN_SCHEME = "HubLocalToken"
HUB_LOCAL_BEARER_SCHEME = "HubLocalBearer"

_SECURITY_SCHEMES: dict[str, Any] = {
    HUB_LOCAL_TOKEN_SCHEME: {
        "type": "apiKey",
        "in": "header",
        "name": "X-Hub-Local-Token",
        "description": (
            "本机 IPC token（文件 ``{HUB_DATA_DIR}/device/local_ipc.token``）。"
            "开发态可先 ``POST /api/auth/login``，再 ``GET /api/auth/dev/local-ipc-token``。"
            "业务接口另需设备已登录。"
        ),
    },
    HUB_LOCAL_BEARER_SCHEME: {
        "type": "http",
        "scheme": "bearer",
        "description": "同 IPC token：``Authorization: Bearer {token}``（非 JWT）。",
    },
}

_GLOBAL_SECURITY: list[dict[str, list[str]]] = [
    {HUB_LOCAL_TOKEN_SCHEME: []},
    {HUB_LOCAL_BEARER_SCHEME: []},
]

_EXACT_PUBLIC_PATHS: frozenset[str] = frozenset(
    {
        *PUBLIC_API_PATHS,
        "/health",
        "/api/auth/providers",
        "/api/auth/login",
        "/api/auth/dev/local-ipc-token",
    }
)

_PUBLIC_PREFIXES: tuple[str, ...] = (
    "/api/auth/login",
    "/api/auth/dev/local-ipc-token",
)


def _is_openapi_public_path(path: str) -> bool:
    if path in _EXACT_PUBLIC_PATHS:
        return True
    return any(path == p or path.startswith(p + "/") for p in _PUBLIC_PREFIXES)


def apply_hub_security_to_openapi_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """就地注入 securitySchemes + 全局 security；公开路径 ``security: []``。"""
    info = schema.setdefault("info", {})
    desc = str(info.get("description") or "").strip()
    auth_note = (
        "鉴权（Marketing Hub 集成）：业务接口须本机 localhost + "
        "``X-Hub-Local-Token``（或 Bearer 同 token）+ 设备已登录（``POST /api/auth/login``）。"
        "Swagger 右上角 **Authorize** 填入 IPC token；同源 Cookie ``local_ipc_token`` 也会被门禁接受。"
    )
    if "X-Hub-Local-Token" not in desc:
        info["description"] = f"{desc}\n\n{auth_note}".strip() if desc else auth_note

    components = schema.setdefault("components", {})
    schemes = components.setdefault("securitySchemes", {})
    schemes.update(_SECURITY_SCHEMES)
    schema["security"] = list(_GLOBAL_SECURITY)

    for path, methods in (schema.get("paths") or {}).items():
        if not isinstance(methods, dict):
            continue
        public = _is_openapi_public_path(str(path))
        for method, op in methods.items():
            if method.startswith("x-") or not isinstance(op, dict):
                continue
            if public:
                op["security"] = []
            else:
                op.setdefault("security", list(_GLOBAL_SECURITY))
    return schema


def install_hub_openapi_security(app: FastAPI) -> None:
    """覆盖 ``app.openapi``，使 Swagger Authorize 可用。幂等。"""
    if getattr(app.state, "hub_openapi_security_installed", False):
        return

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is not None:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
        apply_hub_security_to_openapi_schema(schema)
        app.openapi_schema = schema
        return app.openapi_schema

    app.openapi_schema = None
    app.openapi = custom_openapi  # type: ignore[method-assign]
    app.state.hub_openapi_security_installed = True
