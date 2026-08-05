"""HTTP routes for the dashboard-auth OAuth round trip.

Mounted at root (no prefix) by ``web_server.py``. The router does not
auto-gate; gating is performed by ``gated_auth_middleware``, which
allowlists everything under ``/auth/*`` and ``/api/auth/providers``.

The routes:

  GET  /login              → server-rendered login page
  GET  /auth/login?provider=N → 302 to IDP, sets PKCE cookie
  GET  /auth/callback?code,state → completes login, sets session cookies
  POST /auth/logout        → clears cookies, best-effort revoke
  GET  /api/auth/providers → list registered providers (login bootstrap)
  GET  /api/auth/me        → current Session or Hub device identity (auth-required)
  GET  /api/auth/dev/local-ipc-token → dev IPC token bootstrap
  POST /api/auth/login → device login (development)
  POST /api/auth/logout → device logout (integrated mode)
  GET/PUT /api/auth/login-prefs → 本机记住账号/密码（device/login_prefs.json）
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections import defaultdict, deque
from typing import Any, Deque, Dict, Tuple

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field

from hermes_cli.dashboard_auth import (
    get_provider,
    list_providers,
)
from hermes_cli.dashboard_auth.audit import AuditEvent, audit_log
from hermes_cli.dashboard_auth.base import (
    InvalidCodeError,
    InvalidCredentialsError,
    ProviderError,
)
from hermes_cli.dashboard_auth.cookies import (
    clear_pkce_cookie,
    clear_session_cookies,
    detect_https,
    read_pkce_cookie,
    read_session_cookies,
    set_pkce_cookie,
    set_session_cookies,
)
from hermes_cli.dashboard_auth.login_page import (
    render_integrated_login_html,
    render_login_html,
)

_log = logging.getLogger(__name__)

router = APIRouter()


def _redirect_uri(request: Request) -> str:
    """Reconstruct the absolute callback URL the IDP redirects back to.

    Three resolution tiers:

      1. ``HERMES_DASHBOARD_PUBLIC_URL`` env var or
         ``dashboard.public_url`` in config.yaml — when set, this is
         the complete authority (scheme + host + optional path prefix)
         and we append ``/auth/callback`` verbatim. ``X-Forwarded-Prefix``
         is IGNORED on this code path because the operator has declared
         the public URL — we no longer need to guess from proxy headers,
         and stacking the prefix on top would double-prefix the common
         case where the prefix is already baked into ``public_url``.
         Relief valve for deploys behind reverse proxies whose forwarded
         headers aren't reliable.

      2. ``X-Forwarded-Prefix: /hermes`` (Mission Control deploys) — we
         prepend the prefix to the path FastAPI's ``url_for`` produces
         (it doesn't natively honour this header — it isn't part of the
         Starlette/uvicorn proxy_headers set).

      3. Bare ``request.url_for("auth_callback")`` — under uvicorn's
         ``proxy_headers=True`` this picks up the public https URL from
         ``X-Forwarded-Host`` plus ``X-Forwarded-Proto``. Fly.io's
         default path.
    """
    from urllib.parse import urlparse, urlunparse

    from hermes_cli.dashboard_auth.prefix import (
        prefix_from_request,
        resolve_public_url,
    )

    # Tier 1: operator-declared public URL.
    public_url = resolve_public_url()
    if public_url:
        # ``public_url`` is the complete authority (possibly with a
        # path prefix already baked in). Append the auth callback path
        # verbatim. ``resolve_public_url`` already stripped any trailing
        # slash so we don't produce ``//auth/callback`` double-slashes.
        return f"{public_url}/auth/callback"

    # Tier 2 + 3: reconstruct from the request URL, optionally with
    # X-Forwarded-Prefix layered on top of the path.
    base = str(request.url_for("auth_callback"))
    prefix = prefix_from_request(request)
    if not prefix:
        return base
    parsed = urlparse(base)
    return urlunparse(parsed._replace(path=f"{prefix}{parsed.path}"))


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def _prefix(request: Request) -> str:
    """Resolve the X-Forwarded-Prefix header for the active request.

    Local indirection so the routes pass a consistent value to the
    cookie helpers (cookie name + Path attribute) and the gate's
    redirect builders (login_url construction). See
    ``hermes_cli.dashboard_auth.prefix`` for the normalisation rules.
    """
    from hermes_cli.dashboard_auth.prefix import prefix_from_request
    return prefix_from_request(request)


# ---------------------------------------------------------------------------
# Public: login page (server-rendered HTML, no SPA bundle)
# ---------------------------------------------------------------------------


@router.get("/login", name="login_page", response_model=None)
async def login_page(request: Request):
    # Read the ``next=`` query the gate's ``_unauth_response`` set on
    # the redirect URL. Validate against the same same-origin rules the
    # callback applies (defence in depth — the gate already filters,
    # but /login is reachable directly too).
    from hermes_cli.integrated_mount import hub_ipc_auth_configured

    next_path = _validate_post_login_target(
        request.query_params.get("next", "")
    )
    cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate"}
    if hub_ipc_auth_configured(request):
        # MxAI client 已设备登录 → 与 Hub Dashboard 共享会话，直接进站
        from core.platform.device.device_auth_service import ensure_device_access_fresh
        from core.platform.device.local_device_auth import LocalDeviceAuthStore
        from core.platform.device.local_ipc import get_or_create_ipc_token
        from core.platform.device.login_prefs import load_login_prefs
        from hermes_cli.dashboard_auth.local_guard import IPC_TOKEN_COOKIE

        ensure_device_access_fresh()
        if LocalDeviceAuthStore().tenant_id:
            target = next_path or "/"
            resp = RedirectResponse(url=target, status_code=302, headers=cache_headers)
            resp.set_cookie(
                key=IPC_TOKEN_COOKIE,
                value=get_or_create_ipc_token(),
                path="/",
                httponly=False,
                samesite="lax",
            )
            return resp

        # 未登录：表单预填本机凭证区（device/login_prefs.json）
        prefs = load_login_prefs()
        return HTMLResponse(
            render_integrated_login_html(
                next_path=next_path or "/",
                default_login_name=prefs.login_name,
                default_password=prefs.password if prefs.remember_password else "",
            ),
            headers=cache_headers,
        )
    return HTMLResponse(
        render_login_html(next_path=next_path),
        headers=cache_headers,
    )


# ---------------------------------------------------------------------------
# Public: provider list for the login-page bootstrap
# ---------------------------------------------------------------------------


@router.get("/api/auth/providers", name="auth_providers")
async def api_auth_providers() -> Any:
    providers = list_providers()
    if not providers:
        # Q13: fail-closed when zero providers are registered.
        return JSONResponse(
            {"detail": "no auth providers registered"},
            status_code=503,
        )
    return {
        "providers": [
            {
                "name": p.name,
                "display_name": p.display_name,
                "supports_password": bool(
                    getattr(p, "supports_password", False)
                ),
            }
            for p in providers
        ],
    }


# ---------------------------------------------------------------------------
# Public: OAuth round trip
# ---------------------------------------------------------------------------


@router.get("/auth/login", name="auth_login")
async def auth_login(request: Request, provider: str, next: str = ""):
    p = get_provider(provider)
    if p is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown provider: {provider!r}",
        )

    try:
        ls = p.start_login(redirect_uri=_redirect_uri(request))
    except ProviderError as e:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=provider,
            reason="provider_unreachable",
            ip=_client_ip(request),
        )
        raise HTTPException(
            status_code=503,
            detail=f"Provider unreachable: {e}",
        )

    audit_log(
        AuditEvent.LOGIN_START,
        provider=provider,
        ip=_client_ip(request),
    )

    resp = RedirectResponse(url=ls.redirect_url, status_code=302)
    # Pack the provider name into the PKCE cookie so the callback can
    # find it without a separate cookie. Provider may or may not have
    # already included a ``provider=`` segment.
    pkce = ls.cookie_payload.get("hermes_session_pkce", "")
    if "provider=" not in pkce:
        pkce = f"provider={provider};{pkce}" if pkce else f"provider={provider}"
    # Carry ``next=`` through the round trip in the PKCE cookie. Real
    # IDPs only echo back ``code`` + ``state`` on the callback URL, so
    # query-string transport would lose the value — the cookie is the
    # only server-controlled channel that survives. Validate before we
    # store it so an attacker who reaches /auth/login directly with
    # ``next=//evil.example`` can't poison the cookie.
    safe_next = _validate_post_login_target(next)
    if safe_next:
        from urllib.parse import quote
        pkce = f"{pkce};next={quote(safe_next, safe='')}"
    set_pkce_cookie(
        resp, payload=pkce, use_https=detect_https(request),
        prefix=_prefix(request),
    )
    return resp


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(
    request: Request,
    code: str = "",
    state: str = "",
    error: str = "",
    error_description: str = "",
):
    pkce_raw = read_pkce_cookie(request)
    if not pkce_raw:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            reason="missing_pkce_cookie",
            ip=_client_ip(request),
        )
        raise HTTPException(
            status_code=400,
            detail="Missing PKCE state cookie",
        )

    # Parse ``provider=...;state=...;verifier=...;next=...`` — the
    # ``next`` segment is optional (only present when /auth/login was
    # given a next= query). All keys live in the same flat namespace;
    # ``next`` carries a URL-encoded path so it never contains ``;``.
    parts = dict(
        seg.split("=", 1) for seg in pkce_raw.split(";") if "=" in seg
    )
    provider_name = parts.get("provider", "")
    expected_state = parts.get("state", "")
    verifier = parts.get("verifier", "")
    # Read next= from the cookie ONLY. The IDP doesn't echo next= back
    # on the callback URL (it only carries ``code`` + ``state``), so any
    # next= query parameter on the callback URL is attacker-controlled
    # and MUST be ignored.
    next_from_cookie = parts.get("next", "")

    p = get_provider(provider_name)
    if p is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown provider in cookie: {provider_name!r}",
        )

    if error:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=provider_name,
            reason="idp_error",
            error=error,
            ip=_client_ip(request),
        )
        raise HTTPException(
            status_code=400,
            detail=f"OAuth error from provider: {error} ({error_description})",
        )

    if not state or state != expected_state:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=provider_name,
            reason="state_mismatch",
            ip=_client_ip(request),
        )
        raise HTTPException(
            status_code=400,
            detail="OAuth state mismatch (CSRF check failed)",
        )

    try:
        session = p.complete_login(
            code=code,
            state=state,
            code_verifier=verifier,
            redirect_uri=_redirect_uri(request),
        )
    except InvalidCodeError as e:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=provider_name,
            reason="invalid_code",
            ip=_client_ip(request),
        )
        raise HTTPException(status_code=400, detail=f"Invalid code: {e}")
    except ProviderError as e:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=provider_name,
            reason="provider_unreachable",
            ip=_client_ip(request),
        )
        raise HTTPException(
            status_code=503,
            detail=f"Provider unreachable: {e}",
        )

    audit_log(
        AuditEvent.LOGIN_SUCCESS,
        provider=provider_name,
        user_id=session.user_id,
        email=session.email,
        org_id=session.org_id,
        ip=_client_ip(request),
    )

    expires_in = max(60, session.expires_at - int(time.time()))
    # Honour the ``next=`` value the gate's _unauth_response set in the
    # /login redirect URL and that /auth/login persisted into the PKCE
    # cookie. We re-validate against the same-origin rules here — the
    # cookie is server-set so this is defence in depth, but a regression
    # that lets attacker-controlled bytes into the cookie would otherwise
    # produce an open redirect.
    landing = _validate_post_login_target(next_from_cookie) or "/"
    resp = RedirectResponse(url=landing, status_code=302)
    set_session_cookies(
        resp,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        access_token_expires_in=expires_in,
        use_https=detect_https(request),
        prefix=_prefix(request),
    )
    clear_pkce_cookie(resp, prefix=_prefix(request))
    return resp


def _validate_post_login_target(raw: str) -> str:
    """Return ``raw`` if it's a safe same-origin path, else empty string.

    The ``next`` query param survives a full OAuth round trip — the gate
    encodes it into the /login redirect, the login page emits it back into
    /auth/login, and the IDP preserves it across /authorize/callback. We
    have to re-validate here because the value came back in via the
    URL (an attacker could craft a /auth/callback URL with their own
    ``next=https://evil.example``).
    """
    if not raw:
        return ""
    from urllib.parse import unquote
    decoded = unquote(raw)
    if not decoded.startswith("/") or decoded.startswith("//"):
        return ""
    # Don't loop back to login pages or auth flow.
    if any(
        decoded == p or decoded.startswith(p)
        for p in ("/login", "/auth/", "/api/auth/")
    ):
        return ""
    # Reject any ``/api/*`` target. The gate's ``_safe_next_target``
    # already filters these out before they reach the cookie, but a
    # malicious or stale ``next=`` value that re-enters via the
    # callback URL must not be honoured: a successful redirect to an
    # API endpoint renders raw JSON in the browser address bar — never
    # a useful post-login destination, and indistinguishable from an
    # attacker trying to weaponise the redirect.
    if decoded == "/api" or decoded.startswith("/api/"):
        return ""
    return decoded


# ---------------------------------------------------------------------------
# Public: password (non-redirect) login
# ---------------------------------------------------------------------------
#
# Brute-force throttle. The OAuth flow has no guessable secret on our side
# (the IDP owns credentials), but ``/auth/password-login`` accepts a
# password we verify locally, so it's a credential-stuffing target. A
# simple in-process sliding-window limiter per client IP raises the cost
# of online guessing without any external dependency. It is intentionally
# best-effort: process-local (resets on restart), and behind a trusting
# proxy the IP is the proxy's unless X-Forwarded-For is set — which is why
# this is defence-in-depth on top of the provider's own constant-time
# verify, not the only line of defence.

_PW_RATE_MAX_ATTEMPTS = 10
_PW_RATE_WINDOW_SEC = 60.0
_pw_attempts: Dict[str, Deque[float]] = defaultdict(deque)
_pw_attempts_lock = threading.Lock()


def _password_rate_limited(ip: str) -> bool:
    """True if ``ip`` has exceeded the password-login attempt budget.

    Sliding window: prune attempts older than the window, then check the
    count. Records the attempt timestamp when allowed. An empty IP (no
    discernible client) shares a single bucket — fail-safe toward
    throttling rather than letting unattributable traffic through
    unmetered.
    """
    now = time.monotonic()
    cutoff = now - _PW_RATE_WINDOW_SEC
    key = ip or "_unknown_"
    with _pw_attempts_lock:
        bucket = _pw_attempts[key]
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= _PW_RATE_MAX_ATTEMPTS:
            return True
        bucket.append(now)
        return False


def _reset_password_rate_limit() -> None:
    """Test-only: clear all rate-limit buckets."""
    with _pw_attempts_lock:
        _pw_attempts.clear()


class _PasswordLoginBody(BaseModel):
    provider: str
    username: str
    password: str
    next: str = ""


@router.post("/auth/password-login", name="auth_password_login")
async def auth_password_login(request: Request, body: _PasswordLoginBody):
    """Authenticate a username/password against a password provider.

    Mirrors the cookie-minting tail of ``/auth/callback`` but skips the
    PKCE/state/code machinery (those are OAuth-only). On success sets the
    session cookies and returns JSON ``{"ok": true, "next": <path>}`` —
    the credential form POSTs via fetch and navigates client-side, so a
    302 (which fetch follows opaquely) is the wrong shape here.

    Failure modes, all deliberately generic so the endpoint can't be used
    as a username oracle or a provider-enumeration oracle:
      * unknown provider / provider lacks password support → 404
      * bad credentials → 401 ("Invalid credentials")
      * backing store unreachable → 503
      * too many attempts from this IP → 429
    """
    ip = _client_ip(request)
    if _password_rate_limited(ip):
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=body.provider,
            reason="rate_limited",
            ip=ip,
        )
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again shortly.",
        )

    p = get_provider(body.provider)
    if p is None or not getattr(p, "supports_password", False):
        # Don't leak which providers exist or which support passwords —
        # same 404 whether the provider is unknown or OAuth-only.
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=body.provider,
            reason="unknown_password_provider",
            ip=ip,
        )
        raise HTTPException(status_code=404, detail="Unknown provider")

    try:
        session = p.complete_password_login(
            username=body.username, password=body.password
        )
    except InvalidCredentialsError:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=body.provider,
            reason="invalid_credentials",
            ip=ip,
        )
        # Generic message — never distinguish unknown-user from wrong-password.
        raise HTTPException(status_code=401, detail="Invalid credentials")
    except NotImplementedError:
        # supports_password was True but the method isn't actually
        # implemented — a provider bug, not a client error.
        raise HTTPException(status_code=500, detail="Provider misconfigured")
    except ProviderError as e:
        audit_log(
            AuditEvent.LOGIN_FAILURE,
            provider=body.provider,
            reason="provider_unreachable",
            ip=ip,
        )
        raise HTTPException(status_code=503, detail=f"Provider unreachable: {e}")

    audit_log(
        AuditEvent.LOGIN_SUCCESS,
        provider=body.provider,
        user_id=session.user_id,
        email=session.email,
        org_id=session.org_id,
        ip=ip,
    )

    expires_in = max(60, session.expires_at - int(time.time()))
    landing = _validate_post_login_target(body.next) or "/"
    resp = JSONResponse({"ok": True, "next": landing})
    set_session_cookies(
        resp,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        access_token_expires_in=expires_in,
        use_https=detect_https(request),
        prefix=_prefix(request),
    )
    return resp


@router.post("/auth/logout", name="auth_logout")
async def auth_logout(request: Request):
    _at, rt = read_session_cookies(request)
    if rt:
        # Best-effort revoke. Try every provider so a session minted by
        # any registered provider is revoked correctly. Failures are
        # logged but never raised.
        for provider in list_providers():
            try:
                provider.revoke_session(refresh_token=rt)
            except Exception as e:  # noqa: BLE001 — best-effort
                _log.warning(
                    "dashboard-auth: revoke on %r failed: %s",
                    provider.name, e,
                )

    sess = getattr(request.state, "session", None)
    audit_log(
        AuditEvent.LOGOUT,
        provider=(sess.provider if sess else "unknown"),
        user_id=(sess.user_id if sess else ""),
        ip=_client_ip(request),
    )

    prefix = _prefix(request)
    resp = RedirectResponse(url=f"{prefix}/login", status_code=302)
    clear_session_cookies(resp, prefix=prefix)
    clear_pkce_cookie(resp, prefix=prefix)
    return resp


# ---------------------------------------------------------------------------
# Integrated: IPC bootstrap + device login (public under local guard)
# ---------------------------------------------------------------------------


@router.get("/api/auth/dev/local-ipc-token")
async def dev_local_ipc_token() -> dict[str, str]:
    # 本机 IPC token 引导：不再按环境判断，仅靠 local_guard 的 loopback 门放行
    # （该路径已在 local_guard 中被 _client_is_local 卡死，只有 127.0.0.1 能到这）。
    from core.platform.device.local_ipc import get_or_create_ipc_token

    return {"token": get_or_create_ipc_token()}


class DeviceLoginBody(BaseModel):
    login_name: str = ""
    password: str = Field(min_length=1)
    remember_password: bool | None = None
    auto_login: bool | None = None


class LoginPrefsBody(BaseModel):
    login_name: str = ""
    password: str = ""
    remember_password: bool = False
    auto_login: bool = False


@router.get("/api/auth/login-prefs", name="device_login_prefs_get")
async def device_login_prefs_get() -> dict[str, object]:
    """本机登录表单凭证（登录前可读；仅 loopback 门禁放行）。"""
    from core.platform.device.login_prefs import load_login_prefs

    return load_login_prefs().to_api()


@router.put("/api/auth/login-prefs", name="device_login_prefs_put")
async def device_login_prefs_put(body: LoginPrefsBody) -> dict[str, object]:
    from core.platform.device.login_prefs import save_login_prefs

    prefs = save_login_prefs(
        login_name=body.login_name,
        password=body.password,
        remember_password=body.remember_password,
        auto_login=body.auto_login,
    )
    return prefs.to_api()


@router.post("/api/auth/login", name="device_auth_login")
async def device_auth_login(body: DeviceLoginBody) -> dict[str, object]:
    from core.platform.control_server import (
        ControlServerConfigError,
        ControlServerError,
        InvalidCredentialsError,
    )
    from core.platform.device.device_auth_service import (
        device_login_api_payload,
        perform_device_login,
    )

    from core.platform.control_server import EntitlementExpiredError

    try:
        auth = perform_device_login(
            login_name=body.login_name.strip() or None,
            password=body.password,
        )
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_credentials",
                "message": "invalid login_name or password",
            },
        )
    except EntitlementExpiredError as exc:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "entitlement_expired",
                "message": str(exc) or "产品授权已到期或未授权",
            },
        ) from exc
    except ControlServerConfigError as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "control_server_unconfigured", "message": str(exc)},
        )
    except ControlServerError as exc:
        raise HTTPException(
            status_code=502,
            detail={"code": "control_server_error", "message": str(exc)},
        )
    # 登录成功且调用方带了记住选项 → 写入本机凭证区（与 client / Hub 登录页统一）
    if body.remember_password is not None:
        from core.platform.device.login_prefs import save_login_prefs

        save_login_prefs(
            login_name=body.login_name,
            password=body.password,
            remember_password=bool(body.remember_password),
            auto_login=bool(body.auto_login),
        )
    return device_login_api_payload(auth)


@router.post("/api/auth/logout", name="device_auth_logout")
async def device_auth_logout(request: Request) -> dict[str, bool]:
    import logging

    from hermes_cli.integrated_mount import hub_ipc_auth_configured

    _log = logging.getLogger(__name__)
    if not hub_ipc_auth_configured(request):
        raise HTTPException(status_code=404, detail="not found")
    from core.platform.device.local_device_auth import LocalDeviceAuthStore

    client = request.client.host if request.client else "?"
    _log.warning(
        "device auth logout requested client=%s path=%s referer=%s",
        client,
        request.url.path,
        (request.headers.get("referer") or "")[:120],
    )
    LocalDeviceAuthStore().clear()
    return {"ok": True}


def _device_me_payload() -> dict[str, object] | None:
    from core.platform.device.local_device_auth import LocalDeviceAuthStore

    auth = LocalDeviceAuthStore().load()
    if not auth or not auth.access_token:
        return None
    return {
        "user_id": auth.user_id,
        "email": "",
        "login_name": auth.login_name,
        "display_name": auth.display_name or auth.login_name,
        "org_id": auth.tenant_id,
        "provider": "ai_worker",
        "expires_at": int(auth.expires_at),
        "tenant_name": auth.tenant_name,
        "device_id": auth.device_id,
        "enabled_modules": list(auth.enabled_modules or []),
        "entitlement_expires_at": auth.entitlement_expires_at,
        "product_grant_count": auth.product_grant_count,
        "credit_balance": auth.credit_balance,
        "compute_point_tokens": auth.compute_point_tokens,
        "industry": auth.industry or "",
        "contact_name": auth.contact_name or "",
        "contact_email": auth.contact_email or "",
    }


# ---------------------------------------------------------------------------
# Auth-required: identity probe for the SPA
# ---------------------------------------------------------------------------


@router.get("/api/auth/me", name="auth_me")
async def api_auth_me(request: Request):
    """Return OAuth session or Hub device identity as JSON."""
    from hermes_cli.integrated_mount import hub_ipc_auth_configured

    if hub_ipc_auth_configured(request):
        if not getattr(request.state, "hub_ipc_authenticated", False):
            raise HTTPException(status_code=401, detail="Unauthorized")
        payload = _device_me_payload()
        if payload is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return payload

    sess = getattr(request.state, "session", None)
    if sess is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return {
        "user_id": sess.user_id,
        "email": sess.email,
        "display_name": sess.display_name,
        "org_id": sess.org_id,
        "provider": sess.provider,
        "expires_at": sess.expires_at,
    }


# ---------------------------------------------------------------------------
# Auth-required: WS upgrade ticket (Phase 5)
# ---------------------------------------------------------------------------


@router.post("/api/auth/ws-ticket", name="auth_ws_ticket")
async def api_auth_ws_ticket(request: Request):
    """Mint a short-lived single-use ticket for the authenticated session.

    Browsers cannot set ``Authorization`` on a WebSocket upgrade, so in
    gated mode the SPA POSTs this endpoint to get a ``?ticket=`` value to
    append to ``/api/pty``, ``/api/ws``, ``/api/pub``, or ``/api/events``.

    The ticket has a 30-second TTL and is single-use. Calling this endpoint
    multiple times in quick succession (e.g. one ticket per WS) is the
    expected pattern.
    """
    sess = getattr(request.state, "session", None)
    if callable(getattr(request.app.state, "hub_ipc_token_validator", None)):
        if not getattr(request.state, "hub_ipc_authenticated", False):
            raise HTTPException(status_code=401, detail="Unauthorized")
        from hermes_cli.dashboard_auth.ws_tickets import TTL_SECONDS, mint_ticket

        ticket = mint_ticket(user_id="hub-ipc", provider="hub")
        audit_log(
            AuditEvent.WS_TICKET_MINTED,
            provider="hub",
            user_id="hub-ipc",
            ip=_client_ip(request),
        )
        return {"ticket": ticket, "ttl_seconds": TTL_SECONDS}

    if sess is None:
        # Middleware should already have rejected, but check defensively.
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Import here so the routes module stays usable in test contexts that
    # don't load the ticket store.
    from hermes_cli.dashboard_auth.ws_tickets import TTL_SECONDS, mint_ticket

    ticket = mint_ticket(user_id=sess.user_id, provider=sess.provider)
    audit_log(
        AuditEvent.WS_TICKET_MINTED,
        provider=sess.provider,
        user_id=sess.user_id,
        ip=_client_ip(request),
    )
    return {"ticket": ticket, "ttl_seconds": TTL_SECONDS}
