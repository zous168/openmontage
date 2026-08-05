"""Dashboard 鉴权诊断 — 401 / 跳转登录排查用结构化日志."""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import Request

_log = logging.getLogger(__name__)


def ipc_credential_sources(request: Request) -> dict[str, bool]:
    """IPC 凭证来源探测（不记录 token 值）."""
    from hermes_cli.dashboard_auth.local_guard import IPC_TOKEN_COOKIE

    has_header = bool((request.headers.get("X-Hub-Local-Token") or "").strip())
    auth_hdr = request.headers.get("authorization") or request.headers.get("Authorization")
    has_bearer_short = bool(
        auth_hdr
        and auth_hdr.lower().startswith("bearer ")
        and auth_hdr.split(" ", 1)[1].strip().count(".") < 2
    )
    has_cookie = bool((request.cookies.get(IPC_TOKEN_COOKIE) or "").strip())
    has_query = any(
        bool((request.query_params.get(key) or "").strip())
        for key in ("token", "hub_local_token")
    )
    from hermes_cli.dashboard_auth.local_guard import extract_ipc_credential

    return {
        "has_ipc_header": has_header,
        "has_ipc_cookie": has_cookie,
        "has_ipc_bearer_short": has_bearer_short,
        "has_ipc_query": has_query,
        "ipc_resolved": extract_ipc_credential(request) is not None,
    }


def device_session_snapshot() -> dict[str, Any]:
    """设备登录态快照（不含 access/refresh token）."""
    from core.platform.device.local_device_auth import LocalDeviceAuthStore, _auth_path

    path = _auth_path()
    auth = LocalDeviceAuthStore().load()
    if auth is None:
        snap: dict[str, Any] = {"device_auth": "absent", "auth_file_exists": path.is_file()}
        if path.is_file():
            try:
                snap["auth_file_bytes"] = path.stat().st_size
            except OSError:
                pass
        return snap
    expires_in = auth.expires_at - time.time()
    return {
        "device_auth": "present",
        "login_name": auth.login_name or None,
        "has_tenant": bool(auth.tenant_id),
        "expires_in_sec": round(expires_in),
        "needs_refresh_soon": expires_in <= 300,
        "has_refresh_token": bool(auth.refresh_token),
    }


def log_auth_denial(
    request: Request,
    *,
    layer: str,
    code: str,
    message: str,
    **extra: Any,
) -> None:
    """记录一次鉴权拒绝，便于对照前端跳转与 Hub 终端日志."""
    client = request.client.host if request.client else "?"
    trace_id = getattr(request.state, "trace_id", None)
    referer = (request.headers.get("referer") or "")[:120] or None
    diag: dict[str, Any] = {
        **ipc_credential_sources(request),
        **device_session_snapshot(),
        **extra,
    }
    if referer:
        diag["referer"] = referer
    _log.warning(
        "dashboard-auth-deny layer=%s code=%s method=%s path=%s client=%s "
        "trace_id=%s msg=%s diag=%s",
        layer,
        code,
        request.method,
        request.url.path,
        client,
        trace_id,
        message,
        diag,
    )
