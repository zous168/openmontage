"""Cron job management routes."""

from __future__ import annotations

import asyncio
import base64
import binascii
import copy
import json
import logging
import mimetypes
import os
import re
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
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from hermes_cli import __version__, __release_date__
from hermes_cli.config import (
    DEFAULT_CONFIG,
    OPTIONAL_ENV_VARS,
    cfg_get,
    check_config_version,
    detect_install_method,
    format_docker_update_message,
    get_config_path,
    get_env_path,
    get_hermes_home,
    load_config,
    load_env,
    recommended_update_command_for_method,
    redact_key,
    remove_env_value,
    save_config,
    save_env_value,
)
from hermes_cli.web_routes.deps import profile_scope, resolve_profile_dir
from hermes_cli.web_routes.helpers import (
    ACTION_LOG_FILES,
    ACTION_PROCS,
    ACTION_RESULTS,
    PROJECT_ROOT,
    action_log_dir,
    record_completed_action,
    restart_gateway_after_telegram_onboarding,
    restart_gateway_after_webhook_enable,
    spawn_gateway_restart,
    spawn_hermes_action,
    tail_lines,
)

_log = logging.getLogger(__name__)

router = APIRouter(tags=["cron"])

class CronJobCreate(BaseModel):
    prompt: str = ""
    schedule: str
    name: str = ""
    deliver: str = "local"
    skills: Optional[List[str]] = None
    script: Optional[str] = None
    no_agent: bool = False
    http: Optional[Dict[str, Any]] = None


class CronJobUpdate(BaseModel):
    updates: dict


_CRON_PROFILE_LOCK = threading.RLock()


def _cron_profile_dicts() -> List[Dict[str, Any]]:
    """Return dashboard profile records, falling back to a directory scan."""
    from hermes_cli import profiles as profiles_mod
    from hermes_cli.web_routes.profiles import _fallback_profile_dicts, profile_to_dict
    try:
        return [profile_to_dict(p) for p in profiles_mod.list_profiles()]
    except Exception:
        _log.exception("Failed to list profiles for cron dashboard; falling back to directory scan")
        return _fallback_profile_dicts(profiles_mod)


def _cron_profile_home(profile: Optional[str]) -> Tuple[str, Path]:
    """Resolve a profile query value to (profile_name, HERMES_HOME)."""
    from hermes_cli import profiles as profiles_mod

    raw = (profile or "default").strip() or "default"
    try:
        canon = profiles_mod.normalize_profile_name(raw)
        profiles_mod.validate_profile_name(canon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not profiles_mod.profile_exists(canon):
        raise HTTPException(status_code=404, detail=f"Profile '{canon}' does not exist.")
    return canon, profiles_mod.get_profile_dir(canon)


def _annotate_cron_job(job: Dict[str, Any], profile: str, home: Path) -> Dict[str, Any]:
    annotated = dict(job)
    annotated["profile"] = profile
    annotated["profile_name"] = profile
    annotated["hermes_home"] = str(home)
    annotated["is_default_profile"] = profile == "default"
    return annotated


def _call_cron_for_profile(profile: Optional[str], func_name: str, *args, **kwargs):
    """Run cron.jobs helpers against the selected profile's cron directory.

    Uses ``profile_scope`` so ``cron.jobs`` resolves storage via
    ``get_hermes_home()`` at call time (same mechanism as agent chat sessions).
    """
    profile_name, home = _cron_profile_home(profile)
    scope_profile = None if profile_name == "default" else profile_name
    with _CRON_PROFILE_LOCK:
        with profile_scope(scope_profile):
            from cron import jobs as cron_jobs

            result = getattr(cron_jobs, func_name)(*args, **kwargs)

    if isinstance(result, list):
        return [_annotate_cron_job(j, profile_name, home) for j in result]
    if isinstance(result, dict):
        return _annotate_cron_job(result, profile_name, home)
    return result


def _find_cron_job_profile(job_id: str) -> Optional[str]:
    for profile in _cron_profile_dicts():
        name = str(profile.get("name") or "")
        if not name:
            continue
        jobs = _call_cron_for_profile(name, "list_jobs", True)
        if any(j.get("id") == job_id or j.get("name") == job_id for j in jobs):
            return name
    return None


def _normalize_dashboard_deliver(spec: Dict[str, Any]) -> Dict[str, Any]:
    """Dashboard jobs should notify via WeChat/WeCom bots, not HTTP sessions."""
    deliver = str(spec.get("deliver") or "local").strip().lower()
    if deliver not in {"", "origin"}:
        return spec
    from cron.scheduler import _resolve_clawbot_target, _resolve_wecom_bot_target

    if _resolve_clawbot_target():
        spec["deliver"] = "clawbot"
    elif _resolve_wecom_bot_target():
        spec["deliver"] = "wecom"
    return spec


def _tick_cron_for_profile(profile: Optional[str]) -> None:
    """Run due jobs immediately for a profile (used after manual trigger)."""
    profile_name, _home = _cron_profile_home(profile)
    scope_profile = None if profile_name == "default" else profile_name
    with _CRON_PROFILE_LOCK:
        with profile_scope(scope_profile):
            from cron.scheduler import tick

            tick(verbose=False, sync=False)


@router.get("/api/cron/jobs")
async def list_cron_jobs(profile: str = "all"):
    requested = (profile or "all").strip()
    if requested.lower() != "all":
        return _call_cron_for_profile(requested, "list_jobs", True)

    jobs: List[Dict[str, Any]] = []
    for item in _cron_profile_dicts():
        name = str(item.get("name") or "")
        if not name:
            continue
        try:
            jobs.extend(_call_cron_for_profile(name, "list_jobs", True))
        except Exception:
            _log.exception("Failed to list cron jobs for profile %s", name)
    return jobs


@router.get("/api/cron/jobs/{job_id}")
async def get_cron_job(job_id: str, profile: Optional[str] = None):
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _call_cron_for_profile(selected, "get_job", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/api/cron/jobs/{job_id}/outputs")
async def list_cron_job_outputs(job_id: str, profile: Optional[str] = None, limit: int = 30):
    """Saved markdown outputs for a cron job (includes failed runs)."""
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        limit_n = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit_n = 30
    outputs = _call_cron_for_profile(selected, "list_job_outputs", job_id, limit=limit_n)
    return {"outputs": outputs, "limit": limit_n}


@router.get("/api/cron/jobs/{job_id}/outputs/{output_id}")
async def get_cron_job_output(job_id: str, output_id: str, profile: Optional[str] = None):
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        item = _call_cron_for_profile(selected, "get_job_output", job_id, output_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not item:
        raise HTTPException(status_code=404, detail="Output not found")
    return item


@router.get("/api/cron/jobs/{job_id}/runs")
async def list_cron_job_runs(job_id: str, profile: Optional[str] = None, limit: int = 20):
    """Run sessions produced by a cron job, newest first.

    Cron runs are stored as ordinary sessions whose id is
    ``cron_{job_id}_{timestamp}`` (see cron/scheduler.run_job). A job's history
    is therefore every session whose id carries that prefix; ``source='cron'``
    narrows it and the id prefix binds it to this job. Powers the run-history
    list under each job in the desktop cron detail. Same row shape as
    ``/api/sessions`` so the frontend can reuse SessionInfo.

    Backed by ``SessionDB.list_cron_job_runs`` — a bounded ``[prefix, hi)``
    id-range scan, not the compression-chain CTE used for the recents list,
    so the cost scales with the requested window and not the (unbounded) total
    cron history.
    """
    selected = profile or _find_cron_job_profile(job_id)
    # job_id may be a human name; resolve to the canonical id used in run-session ids.
    canonical = job_id
    if selected:
        job = _call_cron_for_profile(selected, "get_job", job_id)
        if job and job.get("id"):
            canonical = str(job["id"])

    try:
        limit_n = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit_n = 20

    from hermes_cli.web_routes.sessions import _open_session_db_for_profile

    db = _open_session_db_for_profile(selected)
    try:
        runs = db.list_cron_job_runs(canonical, limit=limit_n, offset=0)
        now = time.time()
        for s in runs:
            s["is_active"] = (
                s.get("ended_at") is None
                and (now - s.get("last_active", s.get("started_at", 0))) < 300
            )
            s["archived"] = bool(s.get("archived"))
            if selected:
                s["profile"] = selected
        return {"runs": runs, "limit": limit_n}
    finally:
        db.close()


def _validate_dashboard_cron_script(script: Optional[str]) -> None:
    if not script or not str(script).strip():
        return
    from tools.cronjob_tools import _validate_cron_script_path

    err = _validate_cron_script_path(str(script).strip())
    if err:
        raise HTTPException(status_code=400, detail=err)


@router.post("/api/cron/jobs")
async def create_cron_job(body: CronJobCreate, profile: str = "default"):
    try:
        is_http = bool(body.http)
        if is_http:
            # http 是通用一等执行类型：url 必填，其余 agent/script 校验一律跳过。
            if not str((body.http or {}).get("url") or "").strip():
                raise HTTPException(status_code=400, detail="http job requires a non-empty 'url'.")
        elif body.no_agent and not (body.script or "").strip():
            raise HTTPException(
                status_code=400,
                detail="no_agent=True requires a script — the script is the job.",
            )
        elif not body.no_agent and not (body.prompt or "").strip() and not body.skills:
            raise HTTPException(
                status_code=400,
                detail="Agent jobs require a prompt or at least one skill.",
            )
        _validate_dashboard_cron_script(body.script)
        spec = {
            "prompt": body.prompt,
            "schedule": body.schedule,
            "name": body.name,
            "deliver": body.deliver,
            "skills": body.skills,
            "script": None if is_http else ((body.script or "").strip() or None),
            "no_agent": False if is_http else bool(body.no_agent),
            "http": body.http if is_http else None,
        }
        _normalize_dashboard_deliver(spec)
        return _call_cron_for_profile(profile, "create_job", **spec)
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("POST /api/cron/jobs failed")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/api/cron/delivery-targets")
async def get_cron_delivery_targets():
    """Delivery targets the cron dropdown should offer.

    Always includes the implicit ``local`` option. Beyond that, the list is
    derived dynamically from the configured gateway platforms via
    ``cron.scheduler.cron_delivery_targets()`` — no hardcoded platform list. A
    configured platform that hasn't set its cron home channel is still returned
    with ``home_target_set: false`` so the UI can surface it as "configure a
    home channel first" rather than hiding it.
    """
    targets = [
        {
            "id": "local",
            "name": "Local (save only)",
            "home_target_set": True,
            "home_env_var": None,
        }
    ]
    try:
        from cron.scheduler import cron_delivery_targets

        targets.extend(cron_delivery_targets())
    except Exception:
        _log.exception("GET /api/cron/delivery-targets failed")
    return {"targets": targets}


@router.put("/api/cron/jobs/{job_id}")
async def update_cron_job(job_id: str, body: CronJobUpdate, profile: Optional[str] = None):
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        updates = dict(body.updates or {})
        if "script" in updates:
            _validate_dashboard_cron_script(updates.get("script"))
            raw_script = updates.get("script")
            if raw_script in {None, "", False}:
                updates["script"] = None
            elif isinstance(raw_script, str):
                updates["script"] = raw_script.strip() or None
        if updates.get("no_agent"):
            effective_script = updates.get("script")
            if effective_script is None and "script" not in updates:
                existing = _call_cron_for_profile(selected, "get_job", job_id)
                effective_script = (existing or {}).get("script")
            if not effective_script:
                raise HTTPException(
                    status_code=400,
                    detail="no_agent=True requires a script — set script in the same update.",
                )
        job = _call_cron_for_profile(selected, "update_job", job_id, updates)
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/cron/jobs/{job_id}/pause")
async def pause_cron_job(job_id: str, profile: Optional[str] = None):
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _call_cron_for_profile(selected, "pause_job", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/cron/jobs/{job_id}/resume")
async def resume_cron_job(job_id: str, profile: Optional[str] = None):
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _call_cron_for_profile(selected, "resume_job", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/cron/jobs/{job_id}/trigger")
async def trigger_cron_job(job_id: str, profile: Optional[str] = None):
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    job = _call_cron_for_profile(selected, "trigger_job", job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        _tick_cron_for_profile(selected)
        job = _call_cron_for_profile(selected, "get_job", job_id) or job
    except Exception:
        _log.exception("immediate cron tick after trigger failed for job %s", job_id)
    return job


class CronCallbackBody(BaseModel):
    success: bool = True
    message: str = ""
    run_id: str = ""


@router.post("/api/cron/jobs/{job_id}/callback")
async def cron_job_callback(
    job_id: str, body: CronCallbackBody, profile: Optional[str] = None
):
    """http job 执行回调（cron 通用能力）：每次 http 任务执行后由 ``_run_http_job`` POST 此处，
    带 ``{success, message}``。用 job **自己配置的 ``deliver`` 通道**投递 ``message`` + 更新执行状态
    （``mark_job_run``）。投递通道不在此另指——以 cron job 上的 deliver 为准。"""
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    profile_name, _home = _cron_profile_home(selected)
    scope_profile = None if profile_name == "default" else profile_name
    delivery_error: Optional[str] = None
    with _CRON_PROFILE_LOCK:
        with profile_scope(scope_profile):
            from cron import jobs as cron_jobs
            from cron.scheduler import _deliver_result

            job = cron_jobs.get_job(job_id)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            msg = (body.message or "").strip()
            if msg:
                try:
                    delivery_error = _deliver_result(job, msg)
                except Exception as exc:  # noqa: BLE001
                    delivery_error = str(exc)
                    _log.exception("cron callback delivery failed for job %s", job_id)
            cron_jobs.mark_job_run(
                job_id,
                bool(body.success),
                None if body.success else (msg or "callback reported failure"),
                delivery_error=delivery_error,
            )
            # 把这次**异步回调**的「Callback 返回」段**追加到那次执行的同一条记录**里
            # （按 run_id 定位），使一条记录里顺序为：执行信息 → 同步返回 → Callback 返回。
            from hermes_time import now as _now

            deliver = str(job.get("deliver") or "local")
            deliver_line = (
                f" → {delivery_error}"
                if delivery_error
                else (" → sent" if msg and deliver != "local" else " → (local, not pushed)")
            )
            appendix = (
                "\n---\n\n"
                "## Callback 返回（异步）\n\n"
                f"**Callback Time:** {_now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"**Success:** {bool(body.success)}\n"
                f"**Deliver:** {deliver}{deliver_line}\n\n"
                f"{msg or '(empty message)'}\n"
            )
            try:
                appended = cron_jobs.append_job_output_for_run(job_id, body.run_id, appendix)
                if not appended:
                    # 兜底：找不到同步记录（异常时序）→ 单独存一条，回调信息不丢
                    cron_jobs.save_job_output(job_id, f"# Cron Callback: {job.get('name', job_id)}\n{appendix}")
            except Exception:  # noqa: BLE001
                _log.debug("cron callback output append failed", exc_info=True)
    return {"ok": True, "run_id": body.run_id, "delivery_error": delivery_error}


@router.delete("/api/cron/jobs/{job_id}")
async def delete_cron_job(job_id: str, profile: Optional[str] = None):
    selected = profile or _find_cron_job_profile(job_id)
    if not selected:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        removed = _call_cron_for_profile(selected, "remove_job", job_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Automation Blueprints — parameterized automation blueprints. The dashboard renders the
# slot schema as a form; submitting instantiates a real cron job via the same
# create_job path. See cron/blueprint_catalog.py for the single source of truth.
# ---------------------------------------------------------------------------
class AutomationBlueprintInstantiate(BaseModel):
    blueprint: str                      # blueprint key, e.g. "morning-brief"
    values: Dict[str, Any] = {}      # filled slot values from the form


@router.get("/api/cron/blueprints")
async def list_cron_blueprints():
    """Return the blueprint catalog as form schemas for the dashboard gallery.

    The ``deliver`` slot's options are rewritten from the user's actually
    configured gateway platforms (plus the universal origin/local/all), so the
    form never offers a platform that isn't connected.
    """
    try:
        from cron.blueprint_catalog import CATALOG, blueprint_catalog_entry

        deliver_options = None
        try:
            from cron.scheduler import cron_delivery_targets

            platforms = [t["id"] for t in cron_delivery_targets() if t.get("id")]
            deliver_options = ["origin", "local", *platforms]
        except Exception:
            _log.debug("cron_delivery_targets unavailable; using static deliver options", exc_info=True)

        entries = []
        for r in CATALOG:
            entry = blueprint_catalog_entry(r)
            if deliver_options:
                for f in entry.get("fields", []):
                    if f.get("name") == "deliver":
                        f["options"] = deliver_options
            entries.append(entry)
        return {"blueprints": entries}
    except Exception as e:
        _log.exception("GET /api/cron/blueprints failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/cron/blueprints/instantiate")
async def instantiate_blueprint(body: AutomationBlueprintInstantiate, profile: str = "default"):
    """Fill a blueprint's slots and create the cron job (form-submit path)."""
    try:
        from cron.blueprint_catalog import fill_blueprint, get_blueprint, BlueprintFillError

        blueprint = get_blueprint(body.blueprint)
        if blueprint is None:
            raise HTTPException(status_code=404, detail=f"Unknown blueprint: {body.blueprint}")
        try:
            spec = fill_blueprint(blueprint, body.values)
        except BlueprintFillError as exc:
            # Field-level validation error — 422 so the form can show it inline.
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        _normalize_dashboard_deliver(spec)
        # Blueprint-created jobs deliver to the dashboard's configured target by
        # default; the form's deliver slot overrides via spec["deliver"].
        spec.pop("origin", None)
        return _call_cron_for_profile(profile, "create_job", **spec)
    except HTTPException:
        raise
    except Exception as e:
        _log.exception("POST /api/cron/blueprints/instantiate failed")
        raise HTTPException(status_code=400, detail=str(e))


# ---------------------------------------------------------------------------
# MCP server endpoints — list / add / remove / test.
#
# Wraps the same config data layer the CLI uses (hermes_cli.mcp_config), so
# servers managed here show up under `hermes mcp list` and vice versa.  Secrets
# in stdio `env` blocks are redacted on read; the agent picks them up from
# config.yaml at session start exactly as with CLI-added servers.
# ---------------------------------------------------------------------------


class MCPServerCreate(BaseModel):
    name: str
    url: Optional[str] = None
    command: Optional[str] = None
    args: List[str] = []
    # env: KEY=VALUE map for stdio servers (API keys, etc.)
    env: Dict[str, str] = {}
    # auth: "oauth" | "header" | None
    auth: Optional[str] = None
    profile: Optional[str] = None


def _redact_mcp_env(env: Dict[str, Any]) -> Dict[str, str]:
    """Mask secret-shaped MCP env values for read responses."""
    out: Dict[str, str] = {}
    for k, v in (env or {}).items():
        try:
            out[str(k)] = redact_key(str(v)) if v else ""
        except Exception:
            out[str(k)] = "***"
    return out


def _mcp_server_summary(name: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    transport = "http" if cfg.get("url") else ("stdio" if cfg.get("command") else "unknown")
    return {
        "name": name,
        "transport": transport,
        "url": cfg.get("url"),
        "command": cfg.get("command"),
        "args": list(cfg.get("args") or []),
        "env": _redact_mcp_env(cfg.get("env") or {}),
        "auth": cfg.get("auth"),
        "enabled": cfg.get("enabled", True) is not False,
        # Tool selection: list of enabled tool names, or None = all.
        "tools": cfg.get("tools"),
    }


