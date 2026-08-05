"""
Hermes Agent — Web UI server.

Provides a FastAPI backend serving the Vite/React frontend and REST API
endpoints for managing configuration, environment variables, and sessions.

Usage:
    python -m hermes_cli.main web          # Start on http://127.0.0.1:9119
    python -m hermes_cli.main web --port 8080
"""

from contextlib import asynccontextmanager, contextmanager

import asyncio
import base64
import binascii
import copy
from dataclasses import dataclass
from datetime import datetime, timezone
import hmac
import importlib.util
import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hermes_cli import __version__, __release_date__
from hermes_cli.config import (
    cfg_get,
    DEFAULT_CONFIG,
    OPTIONAL_ENV_VARS,
    get_config_path,
    get_env_path,
    get_hermes_home,
    load_config,
    load_env,
    save_config,
    save_env_value,
    remove_env_value,
    check_config_version,
    detect_install_method,
    format_docker_update_message,
    recommended_update_command_for_method,
    redact_key,
)
from gateway.status import get_running_pid, read_runtime_status
from utils import env_var_enabled

try:
    from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
    from fastapi.staticfiles import StaticFiles
    from pydantic import BaseModel
except ImportError:
    # First try lazy-installing the dashboard extras. Only the user actually
    # running `hermes dashboard` needs fastapi+uvicorn; lazy install keeps
    # them out of every other install path. After install, re-import.
    try:
        from tools.lazy_deps import ensure as _lazy_ensure
        _lazy_ensure("tool.dashboard", prompt=False)
        from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
        from fastapi.staticfiles import StaticFiles
        from pydantic import BaseModel
    except Exception:
        raise SystemExit(
            "Web UI requires fastapi and uvicorn.\n"
            f"Install with: {sys.executable} -m pip install 'fastapi' 'uvicorn[standard]'"
        )

WEB_DIST = Path(os.environ["HERMES_WEB_DIST"]) if "HERMES_WEB_DIST" in os.environ else Path(__file__).parent / "web_dist"
_log = logging.getLogger(__name__)

from hermes_cli.model_trace import log_model_trace as _model_trace
from hermes_cli.web_routes.helpers import (
    spawn_hermes_action as _spawn_hermes_action,
    record_completed_action as _record_completed_action,
    spawn_gateway_restart as _spawn_gateway_restart,
    restart_gateway_after_webhook_enable as _restart_gateway_after_webhook_enable,
    restart_gateway_after_telegram_onboarding as _restart_gateway_after_telegram_onboarding,
    action_log_dir as _action_log_dir,
    tail_lines as _tail_lines,
    ACTION_LOG_FILES as _ACTION_LOG_FILES,
    ACTION_PROCS as _ACTION_PROCS,
    ACTION_RESULTS as _ACTION_RESULTS,
)


# ---------------------------------------------------------------------------
# Per-channel subscriber registry used by /api/pub (PTY-side gateway → dashboard)
# and /api/events (dashboard → browser sidebar).  Keyed by an opaque channel id
# the chat tab generates on mount; entries auto-evict when the last subscriber
# drops AND the publisher has disconnected.
#
# State lives on app.state (not module-level globals) so that asyncio.Lock is
# created on the running event loop during lifespan startup.  A module-level
# asyncio.Lock() binds to whatever loop was active at import time, which breaks
# when the same module is used across TestClient instances or uvicorn reloads.
# ---------------------------------------------------------------------------

def _start_desktop_cron_ticker(stop_event: "threading.Event", interval: int = 60) -> None:
    """Tick the cron scheduler from inside the desktop dashboard backend.

    The scheduler tick loop normally lives in ``hermes gateway run`` — but the
    desktop app spawns a ``hermes dashboard`` backend, not a gateway, so a cron
    a user creates in the app would never fire. We run a minimal ticker here
    (no live adapters; delivery falls back to the per-platform send path).

    Cross-process safe: ``cron.scheduler.tick`` takes the ``cron/.tick.lock``
    file lock, so this never double-fires alongside a real gateway on the same
    HERMES_HOME — whichever process grabs the lock first wins the tick.
    """
    from cron.scheduler import tick as cron_tick

    _log.info("Desktop cron ticker started (interval=%ds)", interval)
    # Tick once up front (catches jobs due at launch), then on the interval.
    while not stop_event.is_set():
        try:
            cron_tick(verbose=False, sync=False)
        except Exception as e:
            _log.debug("Desktop cron tick error: %s", e)
        stop_event.wait(interval)


@asynccontextmanager
async def _lifespan(app: "FastAPI"):
    app.state.event_channels = {}  # dict[str, set]
    app.state.event_lock = asyncio.Lock()

    # Desktop-spawned backends (HERMES_DESKTOP=1) fire cron jobs themselves,
    # since the app has no gateway running the scheduler. Server `hermes
    # dashboard` is unaffected — it relies on its own gateway.
    cron_stop: "threading.Event | None" = None
    cron_thread: "threading.Thread | None" = None
    if os.getenv("HERMES_DESKTOP") == "1":
        cron_stop = threading.Event()
        cron_thread = threading.Thread(
            target=_start_desktop_cron_ticker,
            args=(cron_stop,),
            daemon=True,
            name="desktop-cron-ticker",
        )
        cron_thread.start()

    try:
        yield
    finally:
        if cron_stop is not None:
            cron_stop.set()


def _get_event_state(app: "FastAPI"):
    """Return (event_channels, event_lock) from app.state.

    Lazily initialises the state if the lifespan hasn't run (e.g. when
    TestClient is constructed without a ``with`` block).  The lifespan
    path is preferred because it guarantees the Lock is created on the
    correct event loop, but the lazy path lets existing non-``with``
    TestClient usages keep working.
    """
    try:
        return app.state.event_channels, app.state.event_lock
    except AttributeError:
        app.state.event_channels = {}
        app.state.event_lock = asyncio.Lock()
        return app.state.event_channels, app.state.event_lock


app = FastAPI(
    title="Marketing Hub Gateway",
    version=__version__,
    lifespan=_lifespan,
    docs_url="/docs/dashboard",
    redoc_url="/redoc/dashboard",
    openapi_url="/openapi.json",
    swagger_ui_parameters={
        # 与统一 /docs 对齐：默认折叠，减轻大 spec 首屏压力
        "docExpansion": "none",
        "defaultModelsExpandDepth": -1,
        "defaultModelExpandDepth": -1,
        "filter": True,
        "persistAuthorization": True,
        "tryItOutEnabled": False,
        "tagsSorter": "alpha",
        "operationsSorter": "alpha",
    },
)

# ---------------------------------------------------------------------------
# Session token for protecting sensitive endpoints (reveal).
# The desktop shell mints the token and injects it via
# HERMES_DASHBOARD_SESSION_TOKEN so its main process can authenticate the
# /api calls it makes on the user's behalf; otherwise we generate one fresh
# on every server start. Either way it dies when the process exits and is
# injected into the SPA HTML so only the legitimate web UI can use it.
# ---------------------------------------------------------------------------
_SESSION_TOKEN = os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN") or secrets.token_urlsafe(32)
_SESSION_HEADER_NAME = "X-Hermes-Session-Token"

# In-browser Chat tab (/chat, /api/pty, /api/ws, …).  Always enabled: the
# desktop app and the dashboard's own Chat tab both drive the agent over the
# `/api/ws` + `/api/pty` WebSockets, so the embedded-chat surface is an
# unconditional part of the dashboard.  Kept as a module-level constant (rather
# than inlining ``True`` at every gate) so the WS endpoints and the SPA token
# injection share a single, testable seam.
_DASHBOARD_EMBEDDED_CHAT_ENABLED = True

# Simple rate limiter for the reveal endpoint
_reveal_timestamps: List[float] = []
_REVEAL_MAX_PER_WINDOW = 5
_REVEAL_WINDOW_SECONDS = 30

# CORS: restrict to localhost origins only.  The web UI is intended to run
# locally; binding to 0.0.0.0 with allow_origins=["*"] would let any website
# read/modify config and secrets.

app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Endpoints that do NOT require the session token.  Everything else under
# /api/ is gated by the auth middleware below.
#
# This list is defined in ``hermes_cli.dashboard_auth.public_paths`` so the
# OAuth gate middleware can honour the same allowlist — keeping the two
# gates in lockstep avoids drift like the wildcard-subdomain regression
# where ``/api/status`` was public under the legacy gate but 401'd under
# the OAuth gate (breaking the portal's liveness probe).
#
# Keep the upstream list minimal — only truly non-sensitive, read-only
# endpoints belong there.
# ---------------------------------------------------------------------------
from hermes_cli.dashboard_auth.public_paths import (
    PUBLIC_API_PATHS as _PUBLIC_API_PATHS,
)


def _has_valid_session_token(request: Request) -> bool:
    """True if the request carries a valid dashboard session token.

    The dedicated session header avoids collisions with reverse proxies that
    already use ``Authorization`` (for example Caddy ``basic_auth``). We still
    accept the legacy Bearer path for backward compatibility with older
    dashboard bundles.
    """
    session_header = request.headers.get(_SESSION_HEADER_NAME, "")
    if session_header and hmac.compare_digest(
        session_header.encode(),
        _SESSION_TOKEN.encode(),
    ):
        return True

    auth = request.headers.get("authorization", "")
    expected = f"Bearer {_SESSION_TOKEN}"
    return hmac.compare_digest(auth.encode(), expected.encode())


def _is_dashboard_api_authorized(request: Request) -> bool:
    """Hub 走 IPC；无 IPC 校验器时回退 session token（独立 dashboard 单测）."""
    from hermes_cli.integrated_mount import try_integrated_ipc_auth

    if try_integrated_ipc_auth(request):
        return True
    return _has_valid_session_token(request)




# Accepted Host header values for loopback binds. DNS rebinding attacks
# point a victim browser at an attacker-controlled hostname (evil.test)
# which resolves to 127.0.0.1 after a TTL flip — bypassing same-origin
# checks because the browser now considers evil.test and our dashboard
# "same origin". Validating the Host header at the app layer rejects any
# request whose Host isn't one we bound for. See GHSA-ppp5-vxwm-4cf7.
_LOOPBACK_HOST_VALUES: frozenset = frozenset({
    "localhost", "127.0.0.1", "::1",
})


def should_require_auth(host: str, allow_public: bool) -> bool:
    """Return True iff the dashboard OAuth auth gate must be active.

    Truth table:
      host == loopback                              → False (no auth)
      host != loopback AND allow_public (--insecure)→ False (legacy escape hatch)
      host != loopback AND NOT allow_public         → True  (gate engages)

    "Loopback" matches the same set used by ``--insecure`` enforcement in
    ``start_server``: 127.0.0.1, localhost, ::1. RFC1918 / CGNAT / link-local
    are deliberately treated as PUBLIC — a hostile device on the same LAN is
    exactly the threat model the gate is designed for.
    """
    return (host not in _LOOPBACK_HOST_VALUES) and (not allow_public)


def _is_accepted_host(host_header: str, bound_host: str) -> bool:
    """True if the Host header targets the interface we bound to.

    Accepts:
    - Exact bound host (with or without port suffix)
    - Loopback aliases when bound to loopback
    - Any host when bound to 0.0.0.0 (explicit opt-in to non-loopback,
      no protection possible at this layer)
    """
    if not host_header:
        return False
    # Strip port suffix. IPv6 addresses use bracket notation:
    #   [::1]         — no port
    #   [::1]:9119    — with port
    # Plain hosts/v4:
    #   localhost:9119
    #   127.0.0.1:9119
    h = host_header.strip()
    if h.startswith("["):
        # IPv6 bracketed — port (if any) follows "]:"
        close = h.find("]")
        if close != -1:
            host_only = h[1:close]  # strip brackets
        else:
            host_only = h.strip("[]")
    else:
        host_only = h.rsplit(":", 1)[0] if ":" in h else h
    host_only = host_only.lower()

    # 0.0.0.0 bind means operator explicitly opted into all-interfaces
    # (requires --insecure per web_server.start_server). No Host-layer
    # defence can protect that mode; rely on operator network controls.
    if bound_host in {"0.0.0.0", "::"}:
        return True

    # Loopback bind: accept the loopback names
    bound_lc = bound_host.lower()
    if bound_lc in _LOOPBACK_HOST_VALUES:
        return host_only in _LOOPBACK_HOST_VALUES

    # Explicit non-loopback bind: require exact host match
    return host_only == bound_lc


@app.middleware("http")
async def host_header_middleware(request: Request, call_next):
    """Reject requests whose Host header doesn't match the bound interface.

    Defends against DNS rebinding: a victim browser on a localhost
    dashboard is tricked into fetching from an attacker hostname that
    TTL-flips to 127.0.0.1. CORS and same-origin checks don't help —
    the browser now treats the attacker origin as same-origin with the
    dashboard. Host-header validation at the app layer catches it.

    See GHSA-ppp5-vxwm-4cf7.
    """
    # Store the bound host on app.state so this middleware can read it —
    # set by start_server() at listen time.
    bound_host = getattr(app.state, "bound_host", None)
    if bound_host:
        host_header = request.headers.get("host", "")
        if not _is_accepted_host(host_header, bound_host):
            return JSONResponse(
                status_code=400,
                content={
                    "detail": (
                        "Invalid Host header. Dashboard requests must use "
                        "the hostname the server was bound to."
                    ),
                },
            )
    return await call_next(request)


# ---------------------------------------------------------------------------
# Dashboard OAuth auth gate — engaged only when start_server flags the
# bind as non-loopback-without-insecure.  No-op pass-through in loopback
# mode so the legacy auth_middleware (below) handles those binds via
# the injected ``_SESSION_TOKEN``.  Registered between host_header and
# auth_middleware so the order is: host check → cookie auth → token auth.
# ---------------------------------------------------------------------------


@app.middleware("http")
async def _dashboard_auth_gate(request: Request, call_next):
    from hermes_cli.dashboard_auth.middleware import gated_auth_middleware
    return await gated_auth_middleware(request, call_next)


@app.middleware("http")
async def _hub_local_guard(request: Request, call_next):
    from hermes_cli.dashboard_auth.local_guard import local_guard_middleware
    return await local_guard_middleware(request, call_next)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Require the session token on all /api/ routes except the public list."""
    # When the OAuth gate is active, cookie-based auth (gated_auth_middleware
    # above) is authoritative.  The legacy _SESSION_TOKEN path is loopback-only
    # and is skipped here so the gate's session attachment isn't overridden.
    if getattr(request.app.state, "auth_required", False):
        return await call_next(request)
    path = request.url.path
    if path.startswith("/api/") and path not in _PUBLIC_API_PATHS:
        from hermes_cli.dashboard_auth.local_guard import is_mxai_ws_local_upgrade

        if is_mxai_ws_local_upgrade(request):
            return await call_next(request)
        if not _is_dashboard_api_authorized(request):
            return JSONResponse(
                status_code=401,
                content={"detail": "Unauthorized"},
            )
    return await call_next(request)


from hermes_cli.web_routes import register_routes

register_routes(app)

from hermes_cli.api_docs_routes import router as _api_docs_router  # noqa: E402

app.include_router(_api_docs_router)


# ── 客服会话 HTTP 接口（dashboard 侧，两套独立命名）────────────────────────────
# · /api/customer-sim/*（hermes_cli/sim_api.py）：客户模拟浮窗客户端（建客户 / 发消息，
#   send/stream 代理到网关 api_server）。
# · /api/cs-seat/*（hermes_cli/seat_api.py）：坐席接待只读监控（列会话 + 读历史）。
# 真正的「通用」Agent 聊天在网关 api_server 的 /api/sessions/*，不在 dashboard。
from hermes_cli.sim_api import router as _customer_sim_router  # noqa: E402
from hermes_cli.seat_api import router as _cs_seat_router  # noqa: E402

app.include_router(_customer_sim_router)
app.include_router(_cs_seat_router)
# /api/pty — PTY-over-WebSocket bridge for the dashboard "Chat" tab.
#
# The endpoint spawns the same ``hermes --tui`` binary the CLI uses, behind
# a POSIX pseudo-terminal, and forwards bytes + resize escapes across a
# WebSocket.  The browser renders the ANSI through xterm.js (see
# web/src/pages/ChatPage.tsx).
#
# Auth: ``?token=<session_token>`` query param (browsers can't set
# Authorization on the WS upgrade).  Same ephemeral ``_SESSION_TOKEN`` as
# REST.  Localhost-only — we defensively reject non-loopback clients even
# though uvicorn binds to 127.0.0.1.
# ---------------------------------------------------------------------------

# PTY bridge: POSIX uses pty_bridge (fcntl/termios/ptyprocess); native Windows
# uses win_pty_bridge (pywinpty/ConPTY, already a declared dependency).  Both
# expose the same public surface — spawn/read/write/resize/close/is_available —
# so the /api/pty WebSocket handler needs no platform guards.
if sys.platform.startswith("win"):
    try:
        from hermes_cli.win_pty_bridge import WinPtyBridge as PtyBridge, PtyUnavailableError
        _PTY_BRIDGE_AVAILABLE = True
    except ImportError:  # pragma: no cover - pywinpty missing
        PtyBridge = None  # type: ignore[assignment]
        _PTY_BRIDGE_AVAILABLE = False

        class PtyUnavailableError(RuntimeError):  # type: ignore[no-redef]
            """Stub when win_pty_bridge cannot be imported."""
            pass
else:
    try:
        from hermes_cli.pty_bridge import PtyBridge, PtyUnavailableError
        _PTY_BRIDGE_AVAILABLE = True
    except ImportError:  # pragma: no cover - dev env without ptyprocess
        PtyBridge = None  # type: ignore[assignment]
        _PTY_BRIDGE_AVAILABLE = False

        class PtyUnavailableError(RuntimeError):  # type: ignore[no-redef]
            """Stub on platforms where pty_bridge can't be imported."""
            pass

_RESIZE_RE = re.compile(rb"\x1b\[RESIZE:(\d+);(\d+)\]")
_PTY_READ_CHUNK_TIMEOUT = 0.2
_VALID_CHANNEL_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
# Starlette's TestClient reports the peer as "testclient"; treat it as
# loopback so tests don't need to rewrite request scope.
_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost", "testclient"})


def _ws_client_reason(ws: "WebSocket") -> Optional[str]:
    """Return a rejection reason for the client IP, or None when allowed.

    Reasons are short machine-parseable tokens logged on the rejection path
    so a "WS keeps closing" report can be diagnosed from agent.log without a
    repro. ``None`` means the peer IP passed this gate.

    See :func:`_ws_client_is_allowed` for the full policy rationale.
    """
    if getattr(app.state, "auth_required", False):
        return None
    bound_host = (getattr(app.state, "bound_host", "") or "").strip().lower()
    if bound_host and bound_host not in _LOOPBACK_HOSTS:
        return None
    client_host = ws.client.host if ws.client else ""
    if not client_host:
        return None
    if client_host in _LOOPBACK_HOSTS:
        return None
    return f"peer_not_loopback peer={client_host} bound={bound_host or '?'}"


def _ws_client_is_allowed(ws: "WebSocket") -> bool:
    """Check if the WebSocket client IP is acceptable.

    Loopback bind: only loopback clients allowed — the legacy
    ``?token=<_SESSION_TOKEN>`` path is the only auth we have, so we
    don't want LAN hosts guessing tokens.

    Explicit non-loopback bind (``--host 0.0.0.0``, ``--host ::``, or a
    specific address such as a Tailscale/LAN IP, always with
    ``--insecure``): allow any peer. The operator explicitly opted into
    non-loopback exposure, so the loopback-only peer restriction does not
    apply. DNS-rebinding is still blocked by the Host/Origin guard in
    :func:`_ws_host_origin_is_allowed`, which mirrors the HTTP layer and
    requires the Host header to match the bound interface — the same
    defence ``_is_accepted_host`` applies to non-loopback HTTP requests.

    Gated mode: any peer is allowed — uvicorn's ``proxy_headers=True``
    (enabled when the OAuth gate is active so cookies can pick up
    ``X-Forwarded-Proto``) rewrites ``ws.client.host`` to the
    X-Forwarded-For value, which is the real internet client IP. The
    OAuth gate + single-use ``?ticket=`` is the auth at that point; the
    Host/Origin guard in :func:`_ws_host_origin_is_allowed` is what
    blocks DNS-rebinding here, not the peer IP.
    """
    if getattr(app.state, "auth_required", False):
        return True
    # Any explicit non-loopback bind (0.0.0.0, ::, or a specific LAN /
    # Tailscale address) means the operator opted into non-loopback
    # access via --insecure.  The loopback-only peer gate only applies to
    # an actual loopback bind; otherwise the WS handshake is rejected even
    # though same-bind HTTP requests pass _is_accepted_host.
    bound_host = (getattr(app.state, "bound_host", "") or "").strip().lower()
    if bound_host and bound_host not in _LOOPBACK_HOSTS:
        return True
    client_host = ws.client.host if ws.client else ""
    if not client_host:
        return True
    return client_host in _LOOPBACK_HOSTS


def _ws_host_origin_reason(ws: "WebSocket") -> Optional[str]:
    """Return a Host/Origin rejection reason, or None when allowed.

    Mirrors :func:`_ws_host_origin_is_allowed` but yields a short
    machine-parseable token (``host_mismatch …`` / ``origin_mismatch …``)
    on rejection so the close path can log *why* the upgrade was refused.
    """
    bound_host = getattr(app.state, "bound_host", None)
    if not bound_host:
        return None

    host_header = ws.headers.get("host", "")
    if not _is_accepted_host(host_header, bound_host):
        return f"host_mismatch host={host_header or '?'} bound={bound_host}"

    origin = ws.headers.get("origin", "")
    if not origin:
        return None

    parsed = urllib.parse.urlparse(origin)
    if parsed.scheme not in {"http", "https"}:
        # Non-web origin (packaged Electron: file://, null, app://). The
        # upstream credential check is the real auth boundary; trust it.
        # See _ws_host_origin_is_allowed for the full rationale.
        return None

    if not parsed.netloc:
        return f"origin_mismatch origin={origin} bound={bound_host}"

    if not _is_accepted_host(parsed.netloc, bound_host):
        return f"origin_mismatch origin={origin} bound={bound_host}"
    return None


def _ws_host_origin_is_allowed(ws: "WebSocket") -> bool:
    """Apply the dashboard Host/Origin guard to WebSocket upgrades.

    FastAPI HTTP middleware does not run for WebSocket routes, so the
    DNS-rebinding Host check used for normal dashboard HTTP requests must be
    repeated here before accepting the upgrade.  Browsers also send an Origin
    header on WebSocket handshakes; when present, require it to target the
    same bound dashboard host.
    """
    return _ws_host_origin_reason(ws) is None


def _ws_request_reason(ws: "WebSocket") -> Optional[str]:
    """First Host/Origin or peer-IP rejection reason, or None when allowed."""
    return _ws_host_origin_reason(ws) or _ws_client_reason(ws)


def _ws_request_is_allowed(ws: "WebSocket") -> bool:
    """Return True when the WebSocket upgrade matches dashboard boundaries."""
    return _ws_host_origin_is_allowed(ws) and _ws_client_is_allowed(ws)


def _ws_auth_mode() -> str:
    """Short label for the active WS auth mode — logged on every connection."""
    if getattr(app.state, "auth_required", False):
        return "gated"
    bound_host = (getattr(app.state, "bound_host", "") or "").strip().lower()
    if bound_host and bound_host not in _LOOPBACK_HOSTS:
        return "insecure"
    return "loopback"


def _ws_auth_reason(ws: "WebSocket") -> tuple[Optional[str], str]:
    """Validate WS-upgrade auth; return ``(reason, credential)``.

    ``reason`` is None when the credential is accepted, else a short
    machine-parseable token explaining the rejection (``no_credential``,
    ``token_mismatch``, ``ticket_invalid``, ``internal_invalid``).
    ``credential`` names which credential type was presented (``ticket``,
    ``internal``, ``token``, or ``none``) so the accepted path can log *how*
    a peer authed, not just that it did.

    Loopback / ``--insecure``: legacy ``?token=<_SESSION_TOKEN>`` query
    parameter, constant-time compared.

    Gated (public bind, no ``--insecure``): one of two credentials —

    * ``?ticket=<single-use>`` — a browser-minted, single-use, 30s-TTL ticket
      consumed against the dashboard-auth ticket store. This is what the SPA
      (and native clients) use.
    * ``?internal=<process-credential>`` — the process-lifetime internal
      credential, used only by WS clients the server spawns itself (the
      embedded-TUI PTY child attaching to ``/api/ws`` and ``/api/pub``). It
      is multi-use and never expires so the child can reconnect, and is never
      injected into the SPA — see ``dashboard_auth.ws_tickets`` for the
      threat model.

    The legacy ``?token=`` path is unconditionally rejected in gated mode
    (the SPA bundle isn't carrying the token any longer, and a leaked
    ``_SESSION_TOKEN`` must not grant WS access once the gate is engaged).

    Audit-logs the rejection so operators can debug "WS keeps closing"
    issues from the log.
    """
    token_validator = getattr(app.state, "hub_ipc_token_validator", None)
    if callable(token_validator):
        from hermes_cli.integrated_mount import extract_ipc_from_ws_headers

        try:
            if token_validator(extract_ipc_from_ws_headers(ws.headers)):
                return None, "hub_ipc"
        except Exception:  # noqa: BLE001
            pass
        internal = ws.query_params.get("internal", "")
        if internal:
            from hermes_cli.dashboard_auth.ws_tickets import (
                TicketInvalid,
                consume_internal_credential,
            )

            try:
                consume_internal_credential(internal)
                return None, "internal"
            except TicketInvalid:
                return "internal_invalid", "internal"
        return "no_credential", "none"

    auth_required = bool(getattr(app.state, "auth_required", False))
    if auth_required:
        # Lazy import — keeps this function importable in test harnesses
        # that don't bring in the dashboard_auth layer.
        from hermes_cli.dashboard_auth.audit import AuditEvent, audit_log
        from hermes_cli.dashboard_auth.ws_tickets import (
            TicketInvalid,
            consume_internal_credential,
            consume_ticket,
        )

        # Server-spawned children (PTY child → /api/ws, /api/pub) present the
        # multi-use internal credential rather than a single-use ticket, so
        # they survive reconnects and slow cold boots.
        internal = ws.query_params.get("internal", "")
        if internal:
            try:
                consume_internal_credential(internal)
                return None, "internal"
            except TicketInvalid as exc:
                audit_log(
                    AuditEvent.WS_TICKET_REJECTED,
                    reason=f"internal: {exc}",
                    ip=(ws.client.host if ws.client else ""),
                    path=ws.url.path,
                )
                return "internal_invalid", "internal"

        ticket = ws.query_params.get("ticket", "")
        if not ticket:
            return "no_credential", "none"

        try:
            consume_ticket(ticket)
            return None, "ticket"
        except TicketInvalid as exc:
            audit_log(
                AuditEvent.WS_TICKET_REJECTED,
                reason=str(exc),
                ip=(ws.client.host if ws.client else ""),
                path=ws.url.path,
            )
            return "ticket_invalid", "ticket"

    token = ws.query_params.get("token", "")
    if not token:
        return "no_credential", "none"
    if hmac.compare_digest(token.encode(), _SESSION_TOKEN.encode()):
        return None, "token"
    return "token_mismatch", "token"


def _ws_auth_ok(ws: "WebSocket") -> bool:
    """True when the WS-upgrade credential is accepted. See _ws_auth_reason."""
    return _ws_auth_reason(ws)[0] is None

# Per-channel subscriber registry used by /api/pub (PTY-side gateway → dashboard)
# and /api/events (dashboard → browser sidebar).  Keyed by an opaque channel id
# the chat tab generates on mount; entries auto-evict when the last subscriber
# drops AND the publisher has disconnected.
# (State is initialised in _lifespan on app startup — see above.)


def _resolve_chat_argv(
    resume: Optional[str] = None,
    sidecar_url: Optional[str] = None,
    profile: Optional[str] = None,
    locale: Optional[str] = None,
    gateway_host: Optional[str] = None,
) -> tuple[list[str], Optional[str], Optional[dict]]:
    """Resolve the argv + cwd + env for the chat PTY.

    Default: whatever ``hermes --tui`` would run.  Tests monkeypatch this
    function to inject a tiny fake command (``cat``, ``sh -c 'printf …'``)
    so nothing has to build Node or the TUI bundle.

    Session resume is propagated via the ``HERMES_TUI_RESUME`` env var —
    matching what ``hermes_cli.main._launch_tui`` does for the CLI path.
    Appending ``--resume <id>`` to argv doesn't work because ``ui-tui`` does
    not parse its argv.

    ``HERMES_TUI_GATEWAY_URL`` is injected so the PTY child can attach to
    this process's in-memory ``tui_gateway`` instance instead of spawning
    its own Python gateway subprocess.

    `sidecar_url` (when set) is forwarded as ``HERMES_TUI_SIDECAR_URL`` so
    the spawned ``tui_gateway.entry`` can mirror dispatcher emits to the
    dashboard's ``/api/pub`` endpoint (see :func:`pub_ws`).

    `profile` (when set) scopes the ENTIRE chat to that profile by pointing
    ``HERMES_HOME`` at the profile dir in the child env. Every spawned
    process (the TUI and the ``tui_gateway.entry`` it launches) resolves
    ``get_hermes_home()`` from that env var at its own import, so the child
    binds the profile's config, skills, memory, and state.db from the start
    — the same propagation ``hermes -p <name>`` performs. The in-process
    ``HERMES_TUI_GATEWAY_URL`` attach is SKIPPED for scoped chats: the
    dashboard's in-memory gateway runs under the dashboard's own profile,
    so a profile-scoped chat must spawn its own gateway subprocess.
    """
    from hermes_cli.main import PROJECT_ROOT, _make_tui_argv
    from hermes_cli.web_routes.deps import resolve_profile_dir

    profile_dir: Optional[Path] = None
    requested = (profile or "").strip()
    if requested and requested.lower() != "current":
        profile_dir = resolve_profile_dir(requested)

    argv, cwd = _make_tui_argv(PROJECT_ROOT / "ui-tui", tui_dev=False)
    env = os.environ.copy()
    env.setdefault("HERMES_PYTHON_SRC_ROOT", str(PROJECT_ROOT))
    env.setdefault("HERMES_PYTHON", sys.executable)
    try:
        from hermes_cli.config import apply_terminal_config_to_env
        apply_terminal_config_to_env(env=env)
    except Exception:
        _log.debug("Failed to apply terminal config bridge for dashboard chat", exc_info=True)
    env.setdefault("NODE_ENV", "production")
    # Browser-embedded chat should prefer stable wheel-based scrollback over
    # native terminal mouse tracking. When mouse tracking is enabled, wheel
    # events are consumed by the TUI and forwarded as terminal input, which
    # makes browser-side transcript scrolling feel broken. Keep the terminal
    # build unchanged for native CLI usage; only disable mouse tracking for
    # the dashboard PTY path.
    env.setdefault("HERMES_TUI_DISABLE_MOUSE", "1")
    env.setdefault("HERMES_TUI_INLINE", "1")

    if profile_dir is not None:
        profile_name = (profile or "").strip()
        if profile_name and profile_name.lower() != "current":
            from hermes_cli.profiles import normalize_profile_name

            env["HERMES_PROFILE"] = normalize_profile_name(profile_name)
    else:
        # Default chat must not inherit a sticky HERMES_PROFILE from the host
        # process — that would poison the in-process gateway and PTY child.
        env.pop("HERMES_PROFILE", None)

    from hermes_constants import get_default_hermes_root

    env.setdefault("HUB_DATA_DIR", str(get_default_hermes_root()))

    if resume:
        latest_resume, _latest_path = _session_latest_descendant(resume)
        if latest_resume:
            resume = latest_resume
        env["HERMES_TUI_RESUME"] = resume

    if sidecar_url:
        env["HERMES_TUI_SIDECAR_URL"] = sidecar_url

    # Profile-scoped chats must NOT attach to the dashboard's in-memory
    # gateway — it runs under the dashboard's own profile. Without the
    # attach URL, gatewayClient spawns its own `tui_gateway.entry`, which
    # inherits the profile HERMES_HOME set above.
    if profile_dir is None:
        if gateway_ws_url := _build_gateway_ws_url(request_host=gateway_host):
            env["HERMES_TUI_GATEWAY_URL"] = gateway_ws_url
            try:
                _parsed = urllib.parse.urlparse(gateway_ws_url)
                _netloc = _parsed.netloc
            except Exception:
                _netloc = "<unparsable>"
            _log.info(
                "[diag] _resolve_chat_argv: default profile, "
                "HERMES_TUI_GATEWAY_URL netloc=%s (bound_host=%r bound_port=%r)",
                _netloc,
                getattr(app.state, "bound_host", None),
                getattr(app.state, "bound_port", None),
            )
        else:
            _log.warning(
                "[diag] _resolve_chat_argv: default profile, "
                "_build_gateway_ws_url returned None → TUI will spawn own gateway"
            )

    _apply_tui_locale_branding(env, locale)

    _model_trace(
        "pty.spawn",
        profile=requested or "",
        profile_dir=str(profile_dir) if profile_dir else "",
        resume=resume or "",
        gateway_attach="in_process" if profile_dir is None else "subprocess",
        child_hermes_profile=env.get("HERMES_PROFILE", ""),
        child_hub_data_dir=env.get("HUB_DATA_DIR", ""),
        child_hermes_tui_resume=env.get("HERMES_TUI_RESUME", ""),
        child_gateway_url=bool(env.get("HERMES_TUI_GATEWAY_URL")),
    )

    return list(argv), str(cwd) if cwd else None, env


def _apply_tui_locale_branding(env: dict, locale: Optional[str]) -> None:
    """Inject dashboard UI locale into the embedded TUI PTY child."""
    loc = (locale or "").strip().lower().replace("_", "-")
    if loc in ("zh", "zh-cn", "zh-hans"):
        env["HERMES_TUI_TAGLINE"] = "您的个人AI助手"
        env["HERMES_TUI_WELCOME"] = "输入消息，或输入 /help 查看命令。"
    elif loc in ("zh-hant", "zh-tw", "zh-hk", "zh-mo"):
        env["HERMES_TUI_TAGLINE"] = "您的個人AI助手"
        env["HERMES_TUI_WELCOME"] = "輸入訊息，或輸入 /help 查看命令。"


def _loopback_connect_host(bound_host: str) -> str:
    """Translate a listen/bind address into a dialable loopback host.

    ``bound_host`` is what uvicorn binds to (often ``0.0.0.0`` / ``::``), not
    what a same-machine PTY child should connect to. Dialing the bind wildcard
    yields WS code 1006 and the TUI shows ``error: gateway exited``.
    """
    host_l = str(bound_host).strip().lower()
    if host_l in ("0.0.0.0", "*", ""):
        return "127.0.0.1"
    if host_l in ("::", "[::]", "::0", "0:0:0:0:0:0:0:0"):
        return "::1"
    return str(bound_host).strip()


def _gateway_connect_netloc(request_host: Optional[str] = None) -> Optional[str]:
    """Authoritative ``host:port`` a same-machine PTY child should dial.

    Source of truth priority:

    1. ``request_host`` — the ``Host`` header of the inbound dashboard request
       that is spawning this PTY. It is the address the browser JUST reached the
       server on, so it is by definition the real listening port. Using it makes
       the attach URL immune to ``HUB_API_HOST``/``HUB_API_PORT`` env drift
       (e.g. a stale ``0.0.0.0:8000`` in the launching shell while uvicorn
       actually binds ``127.0.0.1:8642``). The Host header was already validated
       against ``bound_host`` by ``_ws_host_origin_reason`` (DNS-rebinding gate).
    2. ``bound_host``/``bound_port`` — fallback when no request context.

    Wildcard bind hosts (``0.0.0.0`` / ``::``) are translated to loopback: they
    are listen addresses, not connect targets (dialing them yields WS 1006).
    """
    host = None
    port = None
    if request_host:
        parsed = urllib.parse.urlsplit(f"//{request_host.strip()}")
        if parsed.hostname:
            host = parsed.hostname
            port = parsed.port

    if not host or not port:
        host = getattr(app.state, "bound_host", None)
        port = getattr(app.state, "bound_port", None)

    if not host or not port:
        return None

    host = _loopback_connect_host(host)
    return (
        f"[{host}]:{port}"
        if ":" in host and not host.startswith("[")
        else f"{host}:{port}"
    )


def _build_gateway_ws_url(request_host: Optional[str] = None) -> Optional[str]:
    """ws:// URL the PTY child should attach to for JSON-RPC gateway traffic.

    Loopback / ``--insecure``: ``?token=<_SESSION_TOKEN>``.

    Gated mode: the legacy token path is rejected by ``_ws_auth_ok``, so the
    server-spawned PTY child authenticates with the process-lifetime internal
    credential (``?internal=``). It must NOT use a single-use browser ticket:
    the child reads this URL once at startup and reuses it on every reconnect,
    and a 30s-TTL ticket can expire before a slow cold boot even dials.

    ``request_host`` (inbound ``Host`` header) is the preferred netloc source —
    see :func:`_gateway_connect_netloc`.
    """
    netloc = _gateway_connect_netloc(request_host)
    if not netloc:
        return None

    # In integrated mode (hub_ipc_token_validator present), _ws_auth_reason
    # only accepts ?internal= or hub_ipc headers — ?token= is ignored entirely.
    # Use internal credential whenever the integrated validator is active,
    # regardless of auth_required.
    if callable(getattr(app.state, "hub_ipc_token_validator", None)) or getattr(app.state, "auth_required", False):
        from hermes_cli.dashboard_auth.ws_tickets import internal_ws_credential

        qs = urllib.parse.urlencode({"internal": internal_ws_credential()})
    else:
        qs = urllib.parse.urlencode({"token": _SESSION_TOKEN})

    return f"ws://{netloc}/api/ws?{qs}"


def _build_sidecar_url(channel: str, request_host: Optional[str] = None) -> Optional[str]:
    """ws:// URL the PTY child should publish events to, or None when unbound.

    Loopback / ``--insecure``: uses ``?token=<_SESSION_TOKEN>``.

    Gated mode: authenticates with the process-lifetime internal credential
    (``?internal=``), the same one ``_build_gateway_ws_url`` uses. The PTY
    child is a server-spawned process we trust; the credential is multi-use
    and never expires, so the child can reconnect ``/api/pub`` without a new
    URL. (This previously minted a single-use 30s ticket, which meant the
    child could not reconnect and could miss the window on a slow cold boot.)
    Connections authenticated this way are recorded under the
    ``server-internal`` identity in the audit log.

    ``request_host`` (inbound ``Host`` header) is the preferred netloc source —
    see :func:`_gateway_connect_netloc`.
    """
    netloc = _gateway_connect_netloc(request_host)
    if not netloc:
        return None

    if getattr(app.state, "auth_required", False):
        # Gated mode — use the internal credential so the WS upgrade survives
        # _ws_auth_ok and the child can reconnect.
        from hermes_cli.dashboard_auth.ws_tickets import internal_ws_credential

        qs = urllib.parse.urlencode(
            {"internal": internal_ws_credential(), "channel": channel}
        )
    else:
        qs = urllib.parse.urlencode({"token": _SESSION_TOKEN, "channel": channel})

    return f"ws://{netloc}/api/pub?{qs}"


async def _broadcast_event(app: Any, channel: str, payload: str) -> None:
    """Fan out one publisher frame to every subscriber on `channel`."""
    event_channels, event_lock = _get_event_state(app)
    async with event_lock:
        subs = list(event_channels.get(channel, ()))

    for sub in subs:
        try:
            await sub.send_text(payload)
        except Exception:
            # Subscriber went away mid-send; the /api/events finally clause
            # will remove it from the registry on its next iteration.
            _log.warning("broadcast send failed for subscriber on %s", channel, exc_info=True)


def _channel_or_close_code(ws: WebSocket) -> Optional[str]:
    """Return the channel id from the query string or None if invalid."""
    channel = ws.query_params.get("channel", "")

    return channel if _VALID_CHANNEL_RE.match(channel) else None


def _pty_child_exit_code(bridge) -> str:
    """Best-effort PTY child exit code for disconnect forensics."""
    try:
        if hasattr(bridge, "child_exit_code"):
            code = bridge.child_exit_code()
            if code is not None:
                return str(code)
            return "running" if bridge.is_alive() else "unknown"
        proc = getattr(bridge, "_proc", None)
        if proc is not None:
            is_alive = getattr(proc, "isalive", lambda: False)
            if is_alive():
                return "running"
            exitstatus = getattr(proc, "exitstatus", None)
            if exitstatus is not None:
                return str(exitstatus)
    except Exception:
        pass
    return "unknown"


def _ws_close_reason(text: str) -> str:
    """Clamp a WS close reason to the protocol's 123-byte UTF-8 limit.

    RFC 6455 caps the close-frame reason at 123 bytes; uvicorn raises if a
    longer string is passed. Our reasons embed an attacker-controlled origin,
    so truncate defensively rather than crash the close handler.
    """
    encoded = text.encode("utf-8", "replace")
    if len(encoded) <= 123:
        return text
    return encoded[:120].decode("utf-8", "ignore") + "..."


@app.websocket("/api/pty")
async def pty_ws(ws: WebSocket) -> None:
    peer = ws.client.host if ws.client else "?"

    if not _DASHBOARD_EMBEDDED_CHAT_ENABLED:
        _log.info("pty refused: embedded chat disabled peer=%s", peer)
        await ws.close(code=4404, reason="embedded chat disabled")
        return

    # --- auth + host/origin/peer check (before accept so we can close
    #     cleanly AND tell the client WHY via the close code + reason).
    #     Each gate maps to a distinct close code so the log and the
    #     browser banner agree on the cause:
    #       4401 bad credential   4403 host/origin mismatch
    #       4408 peer not allowed  4404 chat disabled
    auth_reason, cred = _ws_auth_reason(ws)
    mode = _ws_auth_mode()
    if auth_reason is not None:
        _log.warning(
            "pty auth rejected reason=%s mode=%s cred=%s peer=%s",
            auth_reason, mode, cred, peer,
        )
        await ws.close(code=4401, reason=_ws_close_reason(f"auth: {auth_reason}"))
        return

    host_origin_reason = _ws_host_origin_reason(ws)
    if host_origin_reason is not None:
        _log.warning("pty refused: %s peer=%s", host_origin_reason, peer)
        await ws.close(code=4403, reason=_ws_close_reason(host_origin_reason))
        return

    client_reason = _ws_client_reason(ws)
    if client_reason is not None:
        _log.warning("pty refused: %s", client_reason)
        await ws.close(code=4408, reason=_ws_close_reason(client_reason))
        return

    await ws.accept()
    _log.info("pty accepted peer=%s mode=%s cred=%s", peer, mode, cred)

    # On native Windows, the POSIX PTY bridge can't be imported.  Tell the
    # client and close cleanly rather than pretending the feature works.
    if not _PTY_BRIDGE_AVAILABLE:
        await ws.send_text(
            "\r\n\x1b[31mChat unavailable: the embedded terminal requires a "
            "POSIX PTY, which native Windows Python doesn't provide.\x1b[0m\r\n"
            "\x1b[33mInstall Hermes inside WSL2 to use the dashboard's /chat "
            "tab — the rest of the dashboard works here.\x1b[0m\r\n"
        )
        await ws.close(code=1011)
        return

    # --- spawn PTY ------------------------------------------------------
    resume = ws.query_params.get("resume") or None
    profile = ws.query_params.get("profile") or None
    locale = ws.query_params.get("locale") or None
    channel = _channel_or_close_code(ws)
    # The inbound Host header is the address the browser just reached this
    # server on — the authoritative netloc for the PTY child's loopback attach
    # (immune to HUB_API_HOST/PORT env drift). Already validated by the
    # host/origin gate above.
    request_host = ws.headers.get("host") if ws.headers else None
    sidecar_url = (
        _build_sidecar_url(channel, request_host=request_host) if channel else None
    )

    try:
        argv, cwd, env = _resolve_chat_argv(
            resume=resume,
            sidecar_url=sidecar_url,
            profile=profile,
            locale=locale,
            gateway_host=request_host,
        )
    except HTTPException as exc:
        # Unknown/invalid profile from _resolve_profile_dir.
        await ws.send_text(f"\r\n\x1b[31mChat unavailable: {exc.detail}\x1b[0m\r\n")
        await ws.close(code=1011)
        return
    except SystemExit as exc:
        # _make_tui_argv calls sys.exit(1) when node/npm is missing.
        _log.warning("pty spawn failed (SystemExit): %s peer=%s profile=%r", exc, peer, profile)
        await ws.send_text(f"\r\n\x1b[31mChat unavailable: {exc}\x1b[0m\r\n")
        await ws.close(code=1011)
        return
    except OSError as exc:
        # ui-tui 目录缺失 / 安装包未带 tui_dist 等情况（WinError 267 NotADirectoryError 等）.
        detail = str(exc).strip() or "TUI bundle not found"
        if "WinError 267" in detail or "目录名称无效" in detail:
            detail = (
                "内嵌 Chat 依赖的 TUI 未随安装包发布（缺少 hermes_cli/tui_dist/entry.js）。"
                "请重新安装/更新客户端，或联系管理员重打 agent-hub 安装包。"
            )
        _log.warning(
            "pty spawn failed (OSError): %s peer=%s profile=%r hermes_tui_dir=%r hermes_node=%r",
            detail,
            peer,
            profile,
            os.environ.get("HERMES_TUI_DIR"),
            os.environ.get("HERMES_NODE"),
        )
        await ws.send_text(
            f"\r\n\x1b[31mChat unavailable: TUI not installed ({detail})\x1b[0m\r\n"
        )
        await ws.close(code=1011)
        return

    try:
        bridge = PtyBridge.spawn(argv, cwd=cwd, env=env)
    except PtyUnavailableError as exc:
        await ws.send_text(f"\r\n\x1b[31mChat unavailable: {exc}\x1b[0m\r\n")
        await ws.close(code=1011)
        return
    except (FileNotFoundError, OSError) as exc:
        await ws.send_text(f"\r\n\x1b[31mChat failed to start: {exc}\x1b[0m\r\n")
        await ws.close(code=1011)
        return

    _spawn_profile = (profile or "").strip()
    gateway_attach = (
        "subprocess"
        if _spawn_profile and _spawn_profile.lower() != "current"
        else "in_process"
    )
    _log.info(
        "pty.spawned peer=%s profile=%r pid=%d gateway_attach=%s "
        "gateway_url=%s resume=%r channel=%r",
        peer,
        _spawn_profile or "default",
        bridge.pid,
        gateway_attach,
        bool(env.get("HERMES_TUI_GATEWAY_URL")),
        resume,
        channel,
    )

    loop = asyncio.get_running_loop()
    disconnect_reason = "unknown"

    # --- reader task: PTY master → WebSocket ----------------------------
    async def pump_pty_to_ws() -> None:
        nonlocal disconnect_reason
        while True:
            chunk = await loop.run_in_executor(
                None, bridge.read, _PTY_READ_CHUNK_TIMEOUT
            )
            if chunk is None:  # EOF
                disconnect_reason = "child_exit"
                return
            if not chunk:  # no data this tick; yield control and retry
                await asyncio.sleep(0)
                continue
            try:
                await ws.send_bytes(chunk)
            except Exception:
                return

    reader_task = asyncio.create_task(pump_pty_to_ws())

    # --- writer loop: WebSocket → PTY master ----------------------------
    try:
        while True:
            msg = await ws.receive()
            msg_type = msg.get("type")
            if msg_type == "websocket.disconnect":
                disconnect_reason = "client_disconnect"
                break
            raw = msg.get("bytes")
            if raw is None:
                text = msg.get("text")
                raw = text.encode("utf-8") if isinstance(text, str) else b""
            if not raw:
                continue

            # Resize escape is consumed locally, never written to the PTY.
            match = _RESIZE_RE.match(raw)
            if match and match.end() == len(raw):
                cols = int(match.group(1))
                rows = int(match.group(2))
                bridge.resize(cols=cols, rows=rows)
                continue

            bridge.write(raw)
    except WebSocketDisconnect:
        disconnect_reason = "client_disconnect"
    finally:
        reader_task.cancel()
        try:
            await reader_task
        except (asyncio.CancelledError, Exception):
            pass
        child_exit = _pty_child_exit_code(bridge)
        _log.info(
            "pty.closed peer=%s profile=%r channel=%r child_exit=%s disconnect=%s",
            peer,
            _spawn_profile or "default",
            channel,
            child_exit,
            disconnect_reason,
        )
        bridge.close()


# ---------------------------------------------------------------------------
# /api/ws — JSON-RPC WebSocket sidecar for the dashboard "Chat" tab.
#
# Drives the same `tui_gateway.dispatch` surface Ink uses over stdio, so the
# dashboard can render structured metadata (model badge, tool-call sidebar,
# slash launcher, session info) alongside the xterm.js terminal that PTY
# already paints. Both transports bind to the same session id when one is
# active, so a tool.start emitted by the agent fans out to both sinks.
# ---------------------------------------------------------------------------


@app.websocket("/api/ws")
async def gateway_ws(ws: WebSocket) -> None:
    if not _DASHBOARD_EMBEDDED_CHAT_ENABLED:
        _log.warning("[diag] /api/ws: embedded chat disabled, closing 4403")
        await ws.close(code=4403)
        return

    auth_reason, cred_type = _ws_auth_reason(ws)
    _log.info("[diag] /api/ws: auth_reason=%r cred_type=%r client=%s params=%s",
              auth_reason, cred_type, getattr(ws.client, "host", "?"), dict(ws.query_params))
    if auth_reason is not None:
        _log.warning("[diag] /api/ws: auth rejected reason=%r, closing 4401", auth_reason)
        await ws.close(code=4401)
        return

    if not _ws_request_is_allowed(ws):
        _log.warning("[diag] /api/ws: request not allowed (host/origin), closing 4403")
        await ws.close(code=4403)
        return

    from tui_gateway.ws import handle_ws

    await handle_ws(ws)


# ---------------------------------------------------------------------------
# /api/pub + /api/events — chat-tab event broadcast.
#
# The PTY-side ``tui_gateway.entry`` opens /api/pub at startup (driven by
# HERMES_TUI_SIDECAR_URL set in /api/pty's PTY env) and writes every
# dispatcher emit through it.  The dashboard fans those frames out to any
# subscriber that opened /api/events on the same channel id.  This is what
# gives the React sidebar its tool-call feed without breaking the PTY
# child's stdio handshake with Ink.
# ---------------------------------------------------------------------------


@app.websocket("/api/pub")
async def pub_ws(ws: WebSocket) -> None:
    if not _DASHBOARD_EMBEDDED_CHAT_ENABLED:
        await ws.close(code=4403)
        return

    if not _ws_auth_ok(ws):
        await ws.close(code=4401)
        return

    if not _ws_request_is_allowed(ws):
        await ws.close(code=4403)
        return

    channel = _channel_or_close_code(ws)
    if not channel:
        await ws.close(code=4400)
        return

    await ws.accept()

    try:
        while True:
            await _broadcast_event(ws.app, channel, await ws.receive_text())
    except WebSocketDisconnect:
        pass


@app.websocket("/api/events")
async def events_ws(ws: WebSocket) -> None:
    if not _DASHBOARD_EMBEDDED_CHAT_ENABLED:
        await ws.close(code=4403)
        return

    if not _ws_auth_ok(ws):
        await ws.close(code=4401)
        return

    if not _ws_request_is_allowed(ws):
        await ws.close(code=4403)
        return

    channel = _channel_or_close_code(ws)
    if not channel:
        await ws.close(code=4400)
        return

    await ws.accept()

    event_channels, event_lock = _get_event_state(ws.app)
    async with event_lock:
        event_channels.setdefault(channel, set()).add(ws)

    try:
        while True:
            # Subscribers don't speak — the receive() just blocks until
            # disconnect so the connection stays open as long as the
            # browser holds it.
            await ws.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        async with event_lock:
            subs = event_channels.get(channel)

            if subs is not None:
                subs.discard(ws)

                if not subs:
                    event_channels.pop(channel, None)


def _normalise_prefix(raw: Optional[str]) -> str:
    """Normalise an X-Forwarded-Prefix header value.

    Thin re-export of :func:`hermes_cli.dashboard_auth.prefix.normalise_prefix`
    — the single source of truth lives in the dashboard_auth package so
    the gate middleware, the OAuth routes, the cookie helpers, and the
    SPA mount all agree on validation rules.
    """
    from hermes_cli.dashboard_auth.prefix import normalise_prefix
    return normalise_prefix(raw)


def mount_spa(application: FastAPI):
    """Mount the built SPA. Falls back to index.html for client-side routing.

    The session token is injected into index.html via a ``<script>`` tag so
    the SPA can authenticate against protected API endpoints without a
    separate (unauthenticated) token-dispensing endpoint.

    When served behind a path-prefix reverse proxy (e.g.
    ``mission-control.tilos.com/hermes/*`` -> local Caddy -> :9119), the
    proxy injects ``X-Forwarded-Prefix: /hermes`` on every request. We
    rewrite the served ``index.html`` so absolute asset URLs (``/assets/...``)
    and the SPA's runtime ``__HERMES_BASE_PATH__`` honour that prefix
    without rebuilding the bundle.
    """
    if not WEB_DIST.exists():
        @application.get("/{full_path:path}")
        async def no_frontend(full_path: str):
            return JSONResponse(
                {"error": "Frontend not built. Run: cd web && npm run build"},
                status_code=404,
            )
        return

    _index_path = WEB_DIST / "index.html"

    def _serve_index(prefix: str = ""):
        """Return index.html with the session token + base-path injected.

        ``prefix`` is the normalised ``X-Forwarded-Prefix`` (e.g. ``/hermes``)
        or empty string when served at root.

        When the OAuth auth gate is active (``app.state.auth_required``),
        the legacy ``_SESSION_TOKEN`` is NOT injected — the SPA reads
        identity from ``/api/auth/me`` over cookie auth instead.  The
        ``__HERMES_AUTH_REQUIRED__`` flag lets the SPA pick the right
        auth scheme for /api/pty and /api/ws (ticket vs token).
        """
        html = _index_path.read_text(encoding="utf-8")
        chat_js = "true" if _DASHBOARD_EMBEDDED_CHAT_ENABLED else "false"
        gated = bool(getattr(app.state, "auth_required", False))
        gated_js = "true" if gated else "false"
        if gated:
            bootstrap_script = (
                f"<script>"
                f"window.__HERMES_DASHBOARD_EMBEDDED_CHAT__={chat_js};"
                f'window.__HERMES_BASE_PATH__="{prefix}";'
                f"window.__HERMES_AUTH_REQUIRED__={gated_js};"
                f"</script>"
            )
        else:
            bootstrap_script = (
                f'<script>window.__HERMES_SESSION_TOKEN__="{_SESSION_TOKEN}";'
                f"window.__HERMES_DASHBOARD_EMBEDDED_CHAT__={chat_js};"
                f'window.__HERMES_BASE_PATH__="{prefix}";'
                f"window.__HERMES_AUTH_REQUIRED__={gated_js};"
                f"</script>"
            )
        # 客服浮窗：装载即在右下角全局浮出气泡（点开 = 客户模拟 /api/customer-sim/* 聊天框）。
        # 自包含原生 JS（web_dist/chat-widget.js），bootstrap 脚本之后注入，
        # 以便它读到 __HERMES_SESSION_TOKEN__ / __HERMES_BASE_PATH__。
        bootstrap_script += f'<script src="{prefix}/chat-widget.js" defer></script>'
        if prefix:
            # Rewrite absolute asset URLs baked into the Vite build so the
            # browser fetches them through the same proxy prefix.
            html = html.replace('href="/assets/', f'href="{prefix}/assets/')
            html = html.replace('src="/assets/', f'src="{prefix}/assets/')
            html = html.replace('href="/favicon.ico"', f'href="{prefix}/favicon.ico"')
            html = html.replace('href="/fonts/', f'href="{prefix}/fonts/')
            html = html.replace('href="/ds-assets/', f'href="{prefix}/ds-assets/')
            html = html.replace('src="/ds-assets/', f'src="{prefix}/ds-assets/')
        html = html.replace("</head>", f"{bootstrap_script}</head>", 1)
        return HTMLResponse(
            html,
            headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
        )

    # When served behind a path-prefix proxy, the built CSS contains
    # absolute ``url(/fonts/...)`` and ``url(/ds-assets/...)`` references.
    # Browsers resolve those against the document origin, which means
    # under ``/hermes`` they'd hit ``mission-control.tilos.com/fonts/...``
    # (the MC Pages app), not the Hermes backend. Intercept CSS asset
    # requests BEFORE the StaticFiles mount and rewrite the absolute paths
    # when a prefix is in play.
    @application.get("/assets/{filename}.css")
    async def serve_css(filename: str, request: Request):
        css_path = WEB_DIST / "assets" / f"{filename}.css"
        if not css_path.is_file() or not css_path.resolve().is_relative_to(
            WEB_DIST.resolve()
        ):
            return JSONResponse({"error": "not found"}, status_code=404)
        prefix = _normalise_prefix(request.headers.get("x-forwarded-prefix"))
        css = css_path.read_text(encoding="utf-8")
        if prefix:
            for asset_dir in ("/fonts/", "/fonts-terminal/", "/ds-assets/", "/assets/"):
                css = css.replace(f"url({asset_dir}", f"url({prefix}{asset_dir}")
                css = css.replace(f"url(\"{asset_dir}", f"url(\"{prefix}{asset_dir}")
                css = css.replace(f"url('{asset_dir}", f"url('{prefix}{asset_dir}")
        return Response(content=css, media_type="text/css")

    application.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")

    @application.get("/{full_path:path}")
    async def serve_spa(full_path: str, request: Request):
        prefix = _normalise_prefix(request.headers.get("x-forwarded-prefix"))
        # An unmatched /api/* path is a missing/renamed endpoint, NOT a
        # client-side route. Falling through to index.html here returns
        # `<!doctype html>` with status 200, which makes JSON clients (the
        # desktop app's fetchJson, dashboard fetch wrappers) blow up with an
        # opaque `SyntaxError: Unexpected token '<'`. Return a real 404 JSON
        # so the caller sees a clear "no such endpoint" instead.
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse(
                {"detail": f"No such API endpoint: /{full_path}"},
                status_code=404,
            )
        file_path = WEB_DIST / full_path
        # Prevent path traversal via url-encoded sequences (%2e%2e/)
        if (
            full_path
            and file_path.resolve().is_relative_to(WEB_DIST.resolve())
            and file_path.exists()
            and file_path.is_file()
        ):
            return FileResponse(file_path)
        return _serve_index(prefix)
_ROUTES_FINALIZED_FLAG = "_hub_routes_finalized"
_SPA_CATCHALL_PATH = "/{full_path:path}"


def _move_spa_catchall_last(application: FastAPI) -> None:
    """把 SPA 贪婪兜底 ``/{full_path:path}`` 移到路由表末尾.

    Starlette 按注册序匹配；任何后注册的真实路由（如翻转后 Hub 系统路由、
    插件 register_routes）只要排在 catch-all 之前即可命中。每次 finalize 都
    复位，保证 catch-all 恒为最后（Hub 融入 Hermes 框架方案 §5.5 约束 2）。
    """
    routes = application.routes
    tail = [r for r in routes if str(getattr(r, "path", "")) == _SPA_CATCHALL_PATH]
    for r in tail:
        routes.remove(r)
        routes.append(r)


def finalize_routes(application: FastAPI | None = None) -> None:
    """收口所有路由并保证 SPA catch-all 最后挂（LT-007.01.02）.

    取代原 import 期的「插件 dashboard api + dashboard_auth + mount_spa」直挂段，
    供组合根在 **系统路由 + 插件 register_routes 就绪后** 调用，使 catch-all
    恒为路由表末位（§5.5 约束 2）。

    幂等 + 可重入：
    - 一次性段（dashboard-manifest 插件 api / dashboard_auth / mount_spa）仅挂一次
      （``app.state`` 标记守卫）；
    - 插件 ``register_routes`` 收口每次都 drain（发现后新登记可再次收口）；
    - 每次都把 catch-all 复位到末尾。

    ``application`` 缺省即本模块根 ``app``（翻转前后都是同一 Hermes app）。
    """
    target = application if application is not None else app

    if not getattr(target.state, _ROUTES_FINALIZED_FLAG, False):
        # Mount plugin API routes (dashboard_manifest 路径) before the SPA catch-all.
        from hermes_cli.web_routes.dashboard_plugins import mount_plugin_api_routes

        mount_plugin_api_routes(target)
        # Dashboard auth routes (/login, /auth/*, /api/auth/*) — always mounted;
        # the gate middleware decides whether to enforce auth, not whether the
        # routes exist.
        from hermes_cli.dashboard_auth.routes import router as _dashboard_auth_router
        target.include_router(_dashboard_auth_router)
        mount_spa(target)
        setattr(target.state, _ROUTES_FINALIZED_FLAG, True)

    # 插件 register_routes 收口（LT-007；发现后可再次调用，drain 新登记）。
    try:
        from hermes_cli.plugins import get_plugin_manager
        get_plugin_manager()._finalize_routes(target)
    except Exception as exc:  # noqa: BLE001 — 插件路由收口失败不拖垮宿主
        _log.warning("plugins.routes.finalize_failed: %s", exc)

    # catch-all 恒为末位（§5.5 约束 2）。
    _move_spa_catchall_last(target)


# import 期收口一次，保持既有启动路径行为不变（翻转后组合根会再次调用以复位顺序）。
finalize_routes(app)


def start_server(
    host: str = "127.0.0.1",
    port: int = 9119,
    open_browser: bool = True,
    allow_public: bool = False,
    initial_profile: str = "",
):
    """Start the web UI server.

    ``initial_profile`` (when set) is appended to the auto-opened browser
    URL as ``?profile=<name>`` so the SPA's profile switcher preselects it
    — used when a profile alias (``<profile> dashboard``) routes to the
    machine dashboard.
    """
    import uvicorn

    # Phase 0: stash the auth-gate flag on app.state so middleware / SPA-token
    # injection / WS-auth paths can branch on it consistently.  Phase 3.5
    # uses this to decide whether to refuse the bind, log the gate-on
    # banner, and enable uvicorn proxy_headers.
    app.state.auth_required = should_require_auth(host, allow_public)

    if app.state.auth_required:
        # Phase 3.5: the gate engages on non-loopback binds.  The legacy
        # "refusing to bind" guard is replaced by "require at least one
        # provider to be registered, else fail closed".
        from hermes_cli.dashboard_auth import list_providers
        if not list_providers():
            # Surface the *specific* reason any bundled provider declined
            # to register (e.g. missing HERMES_DASHBOARD_OAUTH_CLIENT_ID).
            # Each provider plugin that ships with Hermes Agent exposes a
            # module-level ``LAST_SKIP_REASON`` string for this purpose;
            # without it the operator would only see "no providers" which
            # is misleading when the provider IS installed but unconfigured.
            skip_reasons: list[str] = []
            try:
                from plugins.dashboard_auth import nous as _nous_plugin

                if _nous_plugin.LAST_SKIP_REASON:
                    skip_reasons.append(
                        f"  • nous: {_nous_plugin.LAST_SKIP_REASON}"
                    )
            except Exception:
                pass

            if skip_reasons:
                raise SystemExit(
                    f"Refusing to bind dashboard to {host} — the OAuth auth "
                    f"gate engages on non-loopback binds, but no auth "
                    f"providers are registered.\n"
                    f"\n"
                    f"Bundled providers reported these issues:\n"
                    + "\n".join(skip_reasons)
                    + "\n"
                    f"\n"
                    f"Or pass --insecure to skip the auth gate (NOT "
                    f"recommended on untrusted networks)."
                )
            raise SystemExit(
                f"Refusing to bind dashboard to {host} — the OAuth auth "
                f"gate engages on non-loopback binds, but no auth providers "
                f"are registered and no bundled plugin reported a reason "
                f"(was the dashboard_auth/nous plugin removed?).\n"
                f"Install a DashboardAuthProvider plugin, or pass --insecure "
                f"to skip the auth gate (NOT recommended on untrusted "
                f"networks)."
            )
        _log.info(
            "Dashboard binding to %s with OAuth auth gate enabled. "
            "Providers: %s",
            host,
            ", ".join(p.name for p in list_providers()),
        )
    elif host not in _LOOPBACK_HOST_VALUES and allow_public:
        # --insecure path — no auth, loud warning.
        _log.warning(
            "Binding to %s with --insecure — the dashboard has no robust "
            "authentication. Only use on trusted networks.", host,
        )

    # Record the bound host so host_header_middleware can validate incoming
    # Host headers against it. Defends against DNS rebinding (GHSA-ppp5-vxwm-4cf7).
    # bound_port is also stashed so /api/pty can build the back-WS URL the
    # PTY child uses to publish events to the dashboard sidebar.
    app.state.bound_host = host
    app.state.bound_port = port

    if open_browser:
        import webbrowser

        # On headless Linux (no DISPLAY or WAYLAND_DISPLAY) some registered
        # browsers are TUI programs (links, lynx, www-browser) that try to
        # take over the terminal.  That can send SIGHUP to the server process
        # and cause an immediate exit even though uvicorn bound successfully.
        # Skip the auto-open attempt on headless systems and let the user
        # open the URL manually.  macOS and Windows are always considered
        # display-capable.
        _has_display = (
            sys.platform != "linux"
            or bool(os.environ.get("DISPLAY"))
            or bool(os.environ.get("WAYLAND_DISPLAY"))
        )

        if _has_display:
            _open_url = f"http://{host}:{port}"
            if initial_profile:
                from urllib.parse import quote
                _open_url += f"/?profile={quote(initial_profile)}"

            def _open():
                try:
                    time.sleep(1.0)
                    webbrowser.open(_open_url)
                except Exception:
                    pass

            threading.Thread(target=_open, daemon=True).start()
        else:
            _log.debug(
                "Skipping browser-open: no DISPLAY or WAYLAND_DISPLAY detected "
                "(headless Linux). Pass --no-open to suppress this detection."
            )

    print(f"  Hermes Web UI → http://{host}:{port}")
    # proxy_headers defaults to False so _ws_client_is_allowed sees the real
    # connection peer rather than X-Forwarded-For's rewritten value (which
    # would defeat the loopback gate when behind a reverse proxy).  When the
    # OAuth gate is active we are explicitly running behind a TLS terminator
    # (Fly.io) and need X-Forwarded-Proto to decide cookie Secure flags, so
    # we flip proxy_headers on for that mode.
    uvicorn.run(
        app, host=host, port=port, log_level="warning",
        proxy_headers=bool(app.state.auth_required),
        # Detect half-open WS connections (reverse-proxy 524, dropped tunnels)
        # within ~20-40s so WebSocketDisconnect fires the disconnect→reap path.
        # 20s stays under Cloudflare Tunnel's idle timeout, keeping it warm.
        ws_ping_interval=20.0,
        ws_ping_timeout=20.0,
    )
