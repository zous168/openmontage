"""Shared dependencies for Hermes Dashboard route modules."""

from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Request


_SKILLS_PROFILE_LOCK = threading.RLock()


def resolve_profile_dir(name: str) -> Path:
    """Validate ``name`` and resolve to its directory or raise HTTPException."""
    from hermes_cli import profiles as profiles_mod

    try:
        profiles_mod.validate_profile_name(name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not profiles_mod.profile_exists(name):
        raise HTTPException(status_code=404, detail=f"Profile '{name}' does not exist.")
    return profiles_mod.get_profile_dir(name)


@contextmanager
def profile_scope(profile: Optional[str]):
    """Scope config + skill-directory resolution to ``profile`` for one request.

    ``profile`` of None/""/"current" means the integrated **default** profile
    (``HUB_DATA_DIR`` root) — not whatever ``HERMES_PROFILE`` happens to be in
    the host process env.
    """
    requested = (profile or "").strip()

    from hermes_constants import (
        reset_hermes_home_override,
        set_hermes_home_override,
    )
    from tools import skill_manager_tool as _skill_mgr
    from tools import skills_tool as _skills_tool

    token = None
    if not requested or requested.lower() == "current":
        from hermes_constants import get_default_hermes_root

        profile_dir = get_default_hermes_root()
        token = set_hermes_home_override(str(profile_dir))
    else:
        profile_dir = resolve_profile_dir(requested)
        token = set_hermes_home_override(str(profile_dir))

    with _SKILLS_PROFILE_LOCK:
        old_home = _skills_tool.HERMES_HOME
        old_skills_dir = _skills_tool.SKILLS_DIR
        old_mgr_home = _skill_mgr.HERMES_HOME
        old_mgr_skills_dir = _skill_mgr.SKILLS_DIR
        _skills_tool.HERMES_HOME = profile_dir
        _skills_tool.SKILLS_DIR = profile_dir / "skills"
        _skill_mgr.HERMES_HOME = profile_dir
        _skill_mgr.SKILLS_DIR = profile_dir / "skills"
        try:
            from hermes_cli.model_trace import log_model_trace

            log_model_trace(
                "profile_scope",
                requested=requested or "default",
                profile_dir=str(profile_dir),
            )
            yield profile_dir
        finally:
            _skills_tool.HERMES_HOME = old_home
            _skills_tool.SKILLS_DIR = old_skills_dir
            _skill_mgr.HERMES_HOME = old_mgr_home
            _skill_mgr.SKILLS_DIR = old_mgr_skills_dir
            if token is not None:
                reset_hermes_home_override(token)

def require_token(request: "Request") -> None:
    """Authorize a sensitive endpoint (e.g. env reveal), raising 401 if denied."""
    import hmac
    import os

    from fastapi import HTTPException, Request

    session_token = (
        os.environ.get("HERMES_DASHBOARD_SESSION_TOKEN")
        or getattr(request.app.state, "dashboard_session_token", None)
        or getattr(request.app.state, "_session_token", None)
    )

    from hermes_cli.integrated_mount import hub_ipc_auth_configured, try_integrated_ipc_auth

    if hub_ipc_auth_configured(request):
        if try_integrated_ipc_auth(request):
            return
        raise HTTPException(status_code=401, detail="Unauthorized")

    if getattr(request.app.state, "auth_required", False):
        if getattr(request.state, "session", None) is not None:
            return
        raise HTTPException(status_code=401, detail="Unauthorized")

    if not session_token:
        raise HTTPException(status_code=401, detail="Unauthorized")

    header_name = "X-Hermes-Session-Token"
    session_header = request.headers.get(header_name, "")
    if session_header and hmac.compare_digest(
        session_header.encode(),
        str(session_token).encode(),
    ):
        return
    auth = request.headers.get("authorization", "")
    expected = f"Bearer {session_token}"
    if hmac.compare_digest(auth.encode(), expected.encode()):
        return
    raise HTTPException(status_code=401, detail="Unauthorized")

