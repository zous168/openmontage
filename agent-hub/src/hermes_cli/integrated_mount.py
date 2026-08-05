"""Marketing Hub 一体挂载：gated 模式 + Hub IPC 校验."""

from __future__ import annotations

import logging
import os
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Request

logger = logging.getLogger(__name__)

_GATED_ENV = "HERMES_DASHBOARD_GATED"


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _falsy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"0", "false", "no", "off"}


# 进程级 profile 环境变量：在"单进程多 profile"（集成 dashboard）下绝不能存在。
# 它们是全进程共享、无法按 ContextVar 覆盖区分；留着会让 get_hermes_home() /
# _active_profile_name() 在无覆盖时回落到错误 profile（歧义源）。进程内 profile
# 只由 agent/profile_scope.hermes_profile_scope 的 ContextVar 覆盖决定；这些 env
# 变量仅用于向**子进程**注入（见 profiles.py / web_server PTY spawn）。
_PROFILE_ENV_VARS = ("HERMES_PROFILE", "HERMES_HOME")


def purge_profile_env() -> None:
    """从当前进程 env 移除"全局决定 profile"的变量（``HERMES_PROFILE`` / ``HERMES_HOME``）。

    集成 dashboard 单进程承载多 profile：profile 只能由 ContextVar 覆盖决定，任何
    残留的进程级 profile env 都是歧义源。幂等；只动当前进程 env，不影响子进程注入。
    """
    for _name in _PROFILE_ENV_VARS:
        os.environ.pop(_name, None)


def is_integrated_gated() -> bool:
    """Marketing Hub 默认 Hermes gated；``HERMES_DASHBOARD_GATED=0`` 可显式关闭."""
    explicit = os.environ.get(_GATED_ENV)
    if explicit is not None and explicit.strip():
        if _falsy(explicit):
            return False
        return _truthy(explicit)
    return True


def hub_ipc_auth_configured(request: Request) -> bool:
    """Hub 挂载时由 ``configure_integrated_dashboard`` 注入 IPC 校验器."""
    return callable(getattr(request.app.state, "hub_ipc_token_validator", None))


def extract_ipc_credential(request: Request) -> str | None:
    """与 ``local_guard_middleware`` 一致的 IPC 提取（header → Bearer → cookie）."""
    from hermes_cli.dashboard_auth.local_guard import extract_ipc_credential as _extract

    return _extract(request)


def extract_ipc_from_ws_headers(headers: Any) -> str | None:
    from hermes_cli.dashboard_auth.local_guard import IPC_TOKEN_COOKIE

    if headers is not None:
        header_token = headers.get("X-Hub-Local-Token") or headers.get("x-hub-local-token")
        if header_token and str(header_token).strip():
            return str(header_token).strip()
        auth = headers.get("authorization") or headers.get("Authorization")
        if auth and str(auth).lower().startswith("bearer "):
            bearer = str(auth).split(" ", 1)[1].strip()
            if bearer and bearer.count(".") < 2:
                return bearer
        cookie_header = headers.get("cookie", "") or headers.get("Cookie", "") or ""
        for part in cookie_header.split(";"):
            part = part.strip()
            if part.startswith(f"{IPC_TOKEN_COOKIE}="):
                value = part.split("=", 1)[1].strip()
                if value:
                    return value
    return None


def try_integrated_ipc_auth(request: Request) -> bool:
    """校验 Hub IPC；成功则标记 ``hub_ipc_authenticated``."""
    validator = getattr(request.app.state, "hub_ipc_token_validator", None)
    if not callable(validator):
        return False
    try:
        if validator(extract_ipc_credential(request)):
            request.state.hub_ipc_authenticated = True
            return True
    except Exception:  # noqa: BLE001
        return False
    return False


def configure_integrated_dashboard(
    hermes_app: FastAPI,
    *,
    host: str,
    port: int,
    ipc_token_validator: Callable[[str | None], bool],
) -> bool:
    """挂载 Hermes：注册 Hub IPC 校验，并按配置启用 gated.

    集成模式下 ``hub_ipc_token_validator`` 存在时，鉴权统一由
    ``local_guard_middleware`` 承担；``gated_auth_middleware`` 对该模式为 no-op。
    """
    # Dashboard process is the integrated default profile and hosts multiple
    # profiles in-process (per-customer agents scoped via ContextVar override).
    # A leaked process-global HERMES_PROFILE / HERMES_HOME would let an unscoped
    # get_hermes_home() fall back to the wrong profile — the exact ambiguity the
    # ContextVar scoping exists to remove. Strip both; profile is decided ONLY
    # by the override from now on. (Subprocess spawns inject env explicitly.)
    purge_profile_env()

    hermes_app.state.hub_ipc_token_validator = ipc_token_validator
    # 登录前 bootstrap 路径：网关须放行（拿 IPC token 之前的端点，LocalGuard 自身把关 localhost）。
    hermes_app.state.hub_public_prefixes = (
        "/api/auth/login",
        "/api/auth/login-prefs",
        "/api/auth/dev/local-ipc-token",
    )

    from hermes_cli.openapi_security import install_hub_openapi_security

    install_hub_openapi_security(hermes_app)

    # Always stash the integrated listen address so default-profile PTY attach
    # URLs (_build_gateway_ws_url) match the port uvicorn actually binds.
    # Previously only set when gated; missing bound_port → wrong/missing attach URL.
    hermes_app.state.bound_host = host
    hermes_app.state.bound_port = port

    gated = False
    if is_integrated_gated():
        hermes_app.state.auth_required = True
        gated = True
        logger.info(
            "hermes.integrated.gated.enabled host=%s port=%s auth=%s",
            host,
            port,
            "hub_ipc",
        )

    logger.info("hermes.integrated.hub_ipc.enabled")
    return gated
