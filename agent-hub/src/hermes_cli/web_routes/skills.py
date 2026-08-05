"""Skills hub, local skills, and toolset routes."""

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

router = APIRouter(tags=["skills"])


class SkillInstallRequest(BaseModel):
    identifier: str
    profile: Optional[str] = None


class SkillUninstallRequest(BaseModel):
    name: str
    profile: Optional[str] = None


class SkillsUpdateRequest(BaseModel):
    profile: Optional[str] = None


class SkillToggle(BaseModel):
    name: str
    enabled: bool
    profile: Optional[str] = None


def _profile_cli_args(profile: Optional[str]) -> List[str]:
    """Return ``["-p", <name>]`` for a validated non-default profile."""
    requested = (profile or "").strip()
    if not requested or requested.lower() == "current":
        return []
    from hermes_cli import profiles as profiles_mod

    resolve_profile_dir(requested)
    return ["-p", profiles_mod.normalize_profile_name(requested)]


@router.post("/api/skills/hub/install")
async def install_skill_hub(body: SkillInstallRequest, profile: Optional[str] = None):
    identifier = (body.identifier or "").strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier is required")
    try:
        proc = spawn_hermes_action(
            _profile_cli_args(body.profile or profile) + ["skills", "install", identifier],
            "skills-install",
        )
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("Failed to spawn skills install")
        raise HTTPException(status_code=500, detail=f"Failed to install skill: {exc}")
    return {"ok": True, "pid": proc.pid, "name": "skills-install"}


@router.post("/api/skills/hub/uninstall")
async def uninstall_skill_hub(body: SkillUninstallRequest, profile: Optional[str] = None):
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    try:
        proc = spawn_hermes_action(
            _profile_cli_args(body.profile or profile) + ["skills", "uninstall", name, "--yes"],
            "skills-uninstall",
        )
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("Failed to spawn skills uninstall")
        raise HTTPException(status_code=500, detail=f"Failed to uninstall skill: {exc}")
    return {"ok": True, "pid": proc.pid, "name": "skills-uninstall"}


@router.post("/api/skills/hub/update")
async def update_skills_hub(
    body: Optional[SkillsUpdateRequest] = None, profile: Optional[str] = None
):
    try:
        effective = (body.profile if body else None) or profile
        proc = spawn_hermes_action(
            _profile_cli_args(effective) + ["skills", "update"], "skills-update"
        )
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("Failed to spawn skills update")
        raise HTTPException(status_code=500, detail=f"Failed to update skills: {exc}")
    return {"ok": True, "pid": proc.pid, "name": "skills-update"}


# Human-readable labels for each hub source id (matches `hermes skills search`
# provenance).  Keep in sync with create_source_router()'s source list.
_SKILL_HUB_SOURCE_LABELS = {
    "official": "Official (Nous)",
    "hermes-index": "Hermes Index",
    "skills-sh": "skills.sh",
    "well-known": "Well-Known",
    "url": "Direct URL",
    "github": "GitHub",
    "clawhub": "ClawHub",
    "claude-marketplace": "Claude Marketplace",
    "lobehub": "LobeHub",
    "browse-sh": "browse.sh",
}


def _skill_meta_to_payload(m) -> dict:
    return {
        "name": m.name,
        "description": m.description,
        "source": m.source,
        "identifier": m.identifier,
        "trust_level": m.trust_level,
        "repo": m.repo,
        "tags": list(m.tags or []),
    }


def _installed_hub_identifiers(profile: Optional[str] = None) -> dict:
    """Map identifier -> installed lock entry for hub-installed skills.

    Lets the UI mark search results that are already installed.  Scoped to
    ``profile``'s skills/.hub/lock.json when provided (HubLockFile takes an
    explicit path, sidestepping the import-time LOCK_FILE binding).
    Best-effort: returns an empty dict if the lock file can't be read.
    """
    try:
        from tools.skills_hub import HubLockFile

        requested = (profile or "").strip()
        if requested and requested.lower() != "current":
            profile_dir = resolve_profile_dir(requested)
            lock = HubLockFile(profile_dir / "skills" / ".hub" / "lock.json")
        else:
            lock = HubLockFile()
        out = {}
        for entry in lock.list_installed():
            ident = entry.get("identifier")
            if ident:
                out[ident] = {
                    "name": entry.get("name"),
                    "trust_level": entry.get("trust_level"),
                    "scan_verdict": entry.get("scan_verdict"),
                }
        return out
    except Exception:
        return {}


@router.get("/api/skills/hub/sources")
async def list_skills_hub_sources(profile: Optional[str] = None):
    """List the configured skill-hub sources and installed-skill provenance.

    Gives the dashboard something to show BEFORE a search runs — which hubs
    are wired up, their trust tier, and a set of featured skills pulled from
    the centralized index (zero extra API calls).  Without this the Browse-hub
    tab is a blank page with no indication it's even connected to anything.
    ``profile`` scopes the installed-skill provenance to that profile.
    """

    def _run():
        from tools.skills_hub import create_source_router

        sources = create_source_router()
        out = []
        index_available = False
        featured = []
        for src in sources:
            sid = src.source_id()
            entry = {
                "id": sid,
                "label": _SKILL_HUB_SOURCE_LABELS.get(sid, sid),
            }
            # GitHub exposes a rate-limit flag; the index an availability flag.
            if sid == "github":
                try:
                    entry["rate_limited"] = bool(getattr(src, "is_rate_limited", False))
                except Exception:
                    entry["rate_limited"] = False
            if sid == "hermes-index":
                try:
                    index_available = bool(getattr(src, "is_available", False))
                except Exception:
                    index_available = False
                entry["available"] = index_available
                # Empty-query search on the index returns featured/popular skills.
                if index_available:
                    try:
                        featured = [
                            _skill_meta_to_payload(m) for m in src.search("", limit=12)
                        ]
                    except Exception:
                        featured = []
            out.append(entry)
        return {
            "sources": out,
            "index_available": index_available,
            "featured": featured,
            "installed": _installed_hub_identifiers(profile),
        }

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("skills hub sources listing failed")
        raise HTTPException(status_code=502, detail=f"Hub sources failed: {exc}")


@router.get("/api/skills/hub/search")
async def search_skills_hub(
    q: str = "", source: str = "all", limit: int = 20, profile: Optional[str] = None
):
    """Search the skill hub across all configured sources.

    Network-bound (parallel source search); runs in a thread so the FastAPI
    loop isn't blocked.  Returns structured results the UI installs by
    identifier via POST /api/skills/hub/install, previews via
    /api/skills/hub/preview, and scans via /api/skills/hub/scan.
    """
    query = (q or "").strip()
    if not query:
        return {"results": [], "source_counts": {}, "timed_out": [], "installed": {}}

    def _run():
        from tools.skills_hub import create_source_router, parallel_search_sources

        sources = create_source_router()
        capped = min(max(limit, 1), 50)
        all_results, source_counts, timed_out = parallel_search_sources(
            sources, query=query, source_filter=source or "all", overall_timeout=30
        )

        # Dedupe by identifier, preferring higher trust (mirrors unified_search).
        _rank = {"builtin": 2, "trusted": 1, "community": 0}
        seen = {}
        for r in all_results:
            if r.identifier not in seen:
                seen[r.identifier] = r
            elif _rank.get(r.trust_level, 0) > _rank.get(seen[r.identifier].trust_level, 0):
                seen[r.identifier] = r
        deduped = list(seen.values())[:capped]

        return {
            "results": [_skill_meta_to_payload(m) for m in deduped],
            "source_counts": source_counts,
            "timed_out": timed_out,
            "installed": _installed_hub_identifiers(profile),
        }

    try:
        return await asyncio.to_thread(_run)
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("skills hub search failed")
        raise HTTPException(status_code=502, detail=f"Hub search failed: {exc}")


@router.get("/api/skills/hub/preview")
async def preview_skill_hub(identifier: str = ""):
    """Fetch a hub skill's SKILL.md content + metadata for in-dashboard reading.

    Resolves the identifier across configured sources (same path the CLI
    installer uses), then returns the rendered SKILL.md text and the file
    manifest WITHOUT installing anything.  This is the 'read the actual skill
    before installing' affordance the Browse-hub tab was missing.
    """
    ident = (identifier or "").strip()
    if not ident:
        raise HTTPException(status_code=400, detail="identifier is required")

    def _run():
        from hermes_cli.skills_hub import _resolve_source_meta_and_bundle
        from tools.skills_hub import create_source_router

        sources = create_source_router()
        meta, bundle, _src = _resolve_source_meta_and_bundle(ident, sources)
        if not bundle and not meta:
            return None

        files = {}
        skill_md = ""
        if bundle:
            for rel, content in (bundle.files or {}).items():
                if isinstance(content, bytes):
                    # Some sources (e.g. official optional skills) store every
                    # file as bytes.  Decode text so SKILL.md / docs render;
                    # only fall back to a placeholder for genuinely-binary data.
                    try:
                        files[rel] = content.decode("utf-8")
                    except UnicodeDecodeError:
                        files[rel] = "(binary file)"
                else:
                    files[rel] = content
            skill_md = files.get("SKILL.md", "") or ""

        m = meta or bundle
        return {
            "name": getattr(m, "name", ident),
            "description": getattr(m, "description", "") or "",
            "source": getattr(m, "source", "") or "",
            "identifier": getattr(m, "identifier", ident) or ident,
            "trust_level": getattr(m, "trust_level", "community") or "community",
            "repo": getattr(m, "repo", None),
            "tags": list(getattr(m, "tags", None) or []),
            "skill_md": skill_md,
            "files": sorted(files.keys()),
        }

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        _log.exception("skills hub preview failed")
        raise HTTPException(status_code=502, detail=f"Hub preview failed: {exc}")
    if result is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {ident}")
    return result


@router.get("/api/skills/hub/scan")
async def scan_skill_hub(identifier: str = ""):
    """Run the install-time security scan on a hub skill WITHOUT installing it.

    Fetches the bundle, quarantines it, and runs the same `scan_skill` /
    `should_allow_install` pipeline the CLI installer uses — then cleans up the
    quarantine.  Returns the verdict, per-finding detail, trust tier, and the
    install-policy decision so the dashboard can show a visual safety result
    on demand (the 'scan' button the Browse-hub tab was missing).
    """
    ident = (identifier or "").strip()
    if not ident:
        raise HTTPException(status_code=400, detail="identifier is required")

    def _run():
        import shutil as _shutil

        from hermes_cli.skills_hub import _resolve_source_meta_and_bundle
        from tools.skills_hub import create_source_router, quarantine_bundle
        from tools.skills_guard import scan_skill, should_allow_install

        sources = create_source_router()
        meta, bundle, _src = _resolve_source_meta_and_bundle(ident, sources)
        if not bundle:
            return None

        if bundle.source == "official":
            scan_source = "official"
        else:
            scan_source = (
                getattr(bundle, "identifier", "")
                or getattr(meta, "identifier", "")
                or ident
            )

        q_path = None
        try:
            q_path = quarantine_bundle(bundle)
            result = scan_skill(q_path, source=scan_source)
        finally:
            if q_path is not None:
                _shutil.rmtree(q_path, ignore_errors=True)

        allowed, reason = should_allow_install(result, force=False)
        # `allowed` may be None ("ask") for agent-created/dangerous gates.
        if allowed is True:
            policy = "allow"
        elif allowed is None:
            policy = "ask"
        else:
            policy = "block"

        findings = [
            {
                "severity": f.severity,
                "category": f.category,
                "file": f.file,
                "line": f.line,
                "description": f.description,
            }
            for f in result.findings
        ]
        # Per-severity tally for an at-a-glance summary.
        counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        for f in result.findings:
            if f.severity in counts:
                counts[f.severity] += 1

        return {
            "name": result.skill_name,
            "identifier": ident,
            "source": result.source,
            "trust_level": result.trust_level,
            "verdict": result.verdict,
            "summary": result.summary,
            "policy": policy,
            "policy_reason": reason,
            "findings": findings,
            "severity_counts": counts,
        }

    try:
        result = await asyncio.to_thread(_run)
    except Exception as exc:
        _log.exception("skills hub scan failed")
        raise HTTPException(status_code=502, detail=f"Hub scan failed: {exc}")
    if result is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {ident}")
    return result


@router.get("/api/skills")
async def get_skills(profile: Optional[str] = None):
    from tools.skills_tool import _find_all_skills
    from hermes_cli.skills_config import get_disabled_skills
    with profile_scope(profile):
        config = load_config()
        disabled = get_disabled_skills(config)
        skills = _find_all_skills(skip_disabled=True)
    for s in skills:
        s["enabled"] = s["name"] not in disabled
    return skills


@router.put("/api/skills/toggle")
async def toggle_skill(body: SkillToggle, profile: Optional[str] = None):
    from hermes_cli.skills_config import get_disabled_skills, save_disabled_skills
    with profile_scope(body.profile or profile):
        config = load_config()
        disabled = get_disabled_skills(config)
        if body.enabled:
            disabled.discard(body.name)
        else:
            disabled.add(body.name)
        save_disabled_skills(config, disabled)
    return {"ok": True, "name": body.name, "enabled": body.enabled}


class SkillCreate(BaseModel):
    name: str
    content: str
    category: Optional[str] = None
    profile: Optional[str] = None


class SkillContentUpdate(BaseModel):
    name: str
    content: str
    profile: Optional[str] = None


def _clear_skills_prompt_cache() -> None:
    """Best-effort: invalidate the skills system-prompt snapshot after a write.

    Mirrors what ``skill_manage`` does so a dashboard-authored skill is picked
    up by the next session without a manual cache reset.
    """
    try:
        from agent.prompt_builder import clear_skills_system_prompt_cache
        clear_skills_system_prompt_cache(clear_snapshot=True)
    except Exception:
        pass


@router.get("/api/skills/content")
async def get_skill_content(name: str, profile: Optional[str] = None):
    """Return the raw SKILL.md text for a skill, for the dashboard editor."""
    from tools.skill_manager_tool import _find_skill

    with profile_scope(profile):
        found = _find_skill(name)
        if not found:
            raise HTTPException(status_code=404, detail=f"Skill '{name}' not found.")
        skill_md = found["path"] / "SKILL.md"
        if not skill_md.exists():
            raise HTTPException(status_code=404, detail=f"Skill '{name}' has no SKILL.md.")
        try:
            content = skill_md.read_text(encoding="utf-8")
        except OSError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return {"name": name, "content": content, "path": str(skill_md)}


@router.post("/api/skills")
async def create_skill(body: SkillCreate):
    """Create a new custom skill (SKILL.md) from the dashboard editor.

    Calls the same validated write path as the agent's ``skill_manage``
    tool (frontmatter validation, name/category validation, size limit,
    optional security scan) — but bypasses the agent write-approval gate:
    a write from the authenticated dashboard IS the user acting directly.
    """
    from tools.skill_manager_tool import _create_skill

    with profile_scope(body.profile):
        result = _create_skill(body.name, body.content, body.category or None)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Failed to create skill."))
    _clear_skills_prompt_cache()
    return result


@router.put("/api/skills/content")
async def update_skill_content(body: SkillContentUpdate):
    """Replace the SKILL.md of an existing skill (full rewrite) from the editor."""
    from tools.skill_manager_tool import _edit_skill

    with profile_scope(body.profile):
        result = _edit_skill(body.name, body.content)
    if not result.get("success"):
        err = result.get("error", "Failed to update skill.")
        status = 404 if "not found" in str(err).lower() else 400
        raise HTTPException(status_code=status, detail=err)
    _clear_skills_prompt_cache()
    return result


def _resolve_dashboard_toolset_platform(platform: Optional[str]) -> str:
    """Skills 页读写 toolset 绑定的平台键（默认 api_server = GUI/API 对话通道）。"""
    raw = (platform or "api_server").strip()
    return raw or "api_server"


@router.get("/api/tools/toolsets")
async def get_toolsets(
    profile: Optional[str] = None,
    platform: Optional[str] = None,
):
    from hermes_cli.tools_config import (
        _get_effective_configurable_toolsets,
        _get_platform_tools,
        _toolset_has_keys,
        _mxai_bundle_all_enabled,
        _mxai_tool_enabled_states,
        gui_toolset_label,
        MXAI_COMPOSITE_TOOLSET,
    )
    from toolsets import resolve_toolset

    plat = _resolve_dashboard_toolset_platform(platform)
    with profile_scope(profile):
        config = load_config()
        enabled_toolsets = _get_platform_tools(
            config,
            plat,
            include_default_mcp_servers=False,
        )
    result = []
    for name, label, desc in _get_effective_configurable_toolsets():
        try:
            tools = sorted(set(resolve_toolset(name)))
        except Exception:
            tools = []
        if not tools:
            try:
                from hermes_cli.plugins import get_manifest_toolset_tools

                tools = get_manifest_toolset_tools(name)
            except Exception:
                tools = []
        is_enabled = name in enabled_toolsets
        if name == MXAI_COMPOSITE_TOOLSET and tools:
            is_enabled = _mxai_bundle_all_enabled(
                config, plat, enabled_toolsets, tools,
            )
        entry = {
            "name": name,
            "label": gui_toolset_label(label),
            "description": desc,
            "enabled": is_enabled,
            "available": is_enabled,
            "configured": _toolset_has_keys(name, config),
            "tools": tools,
        }
        if name == MXAI_COMPOSITE_TOOLSET and tools:
            entry["tool_enabled"] = _mxai_tool_enabled_states(
                config, plat, enabled_toolsets, tools,
            )
        result.append(entry)
    return result


class ToolsetToggle(BaseModel):
    enabled: bool
    profile: Optional[str] = None
    platform: Optional[str] = None


@router.put("/api/tools/toolsets/{name}")
async def toggle_toolset(name: str, body: ToolsetToggle, profile: Optional[str] = None):
    """Enable/disable a configurable toolset for a gateway platform.

    Dashboard Skills 页默认写入 ``platform_toolsets.api_server``（GUI/API
    对话与 agent-client 同源）。``body.platform`` / query ``platform`` 可改为
    ``cli`` 等与 ``hermes tools --platform`` 对齐。Scoped to ``body.profile``
    when provided. Returns 400 for unknown toolset keys.
    """
    from hermes_cli.tools_config import (
        _get_effective_configurable_toolsets,
        _dashboard_configurable_toolset_keys,
        toggle_dashboard_platform_toolset,
    )

    valid = _dashboard_configurable_toolset_keys()
    if name not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown toolset: {name}")

    plat = _resolve_dashboard_toolset_platform(body.platform)
    with profile_scope(body.profile or profile):
        config = load_config()
        try:
            toggle_dashboard_platform_toolset(config, plat, name, body.enabled)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "name": name, "enabled": body.enabled}


@router.get("/api/tools/toolsets/{name}/config")
async def get_toolset_config(name: str, profile: Optional[str] = None):
    """Return the provider matrix + key status for a toolset's config panel.

    Surfaces the same provider rows the CLI ``hermes tools`` picker shows
    (via ``_visible_providers``), each with its ``env_vars`` annotated with
    current ``is_set`` state so the GUI can render provider selection + key
    entry. Toolsets without a ``TOOL_CATEGORIES`` entry return an empty
    provider list and ``has_category: false``. Returns 400 for unknown keys.
    """
    from hermes_cli.tools_config import (
        TOOL_CATEGORIES,
        _get_effective_configurable_toolsets,
        _is_provider_active,
        _visible_providers,
    )
    from hermes_cli.config import get_env_value

    valid = {ts_key for ts_key, _, _ in _get_effective_configurable_toolsets()}
    if name not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown toolset: {name}")

    with profile_scope(profile):
        config = load_config()
        cat = TOOL_CATEGORIES.get(name)
        providers = []
        active_provider = None
        if cat:
            for prov in _visible_providers(cat, config, force_fresh=True):
                env_vars = [
                    {
                        "key": e["key"],
                        "prompt": e.get("prompt", e["key"]),
                        "url": e.get("url"),
                        "default": e.get("default"),
                        "is_set": bool(get_env_value(e["key"])),
                    }
                    for e in prov.get("env_vars", [])
                ]
                # Surface the same active-provider determination the CLI picker
                # uses (``_is_provider_active``) so the GUI highlights the provider
                # actually written to config (e.g. web.backend), not just the first
                # keyless one in the list.
                is_active = _is_provider_active(prov, config, force_fresh=True)
                if is_active and active_provider is None:
                    active_provider = prov["name"]
                providers.append({
                    "name": prov["name"],
                    "badge": prov.get("badge", ""),
                    "tag": prov.get("tag", ""),
                    "env_vars": env_vars,
                    "post_setup": prov.get("post_setup"),
                    "requires_nous_auth": bool(prov.get("requires_nous_auth")),
                    "is_active": is_active,
                })
    return {
        "name": name,
        "has_category": cat is not None,
        "providers": providers,
        "active_provider": active_provider,
    }


class ToolsetProviderSelect(BaseModel):
    provider: str
    profile: Optional[str] = None


@router.put("/api/tools/toolsets/{name}/provider")
async def select_toolset_provider(
    name: str, body: ToolsetProviderSelect, profile: Optional[str] = None
):
    """Persist a provider selection for a toolset (no key prompting).

    Delegates to ``apply_provider_selection`` — the shared, non-interactive
    core extracted from the CLI configurator — so the GUI and ``hermes tools``
    write identical config keys (``web.backend``, ``tts.provider``, etc.).
    API keys and post-setup flows are handled by separate endpoints. Returns
    400 for unknown toolset or provider names.
    """
    from hermes_cli.tools_config import (
        apply_provider_selection,
        _get_effective_configurable_toolsets,
    )

    valid = {ts_key for ts_key, _, _ in _get_effective_configurable_toolsets()}
    if name not in valid:
        raise HTTPException(status_code=400, detail=f"Unknown toolset: {name}")

    with profile_scope(body.profile or profile):
        config = load_config()
        try:
            apply_provider_selection(name, body.provider, config)
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc).strip('"'))
        save_config(config)
    return {"ok": True, "name": name, "provider": body.provider}


class ToolsetEnvUpdate(BaseModel):
    env: Dict[str, str]
    profile: Optional[str] = None


@router.put("/api/tools/toolsets/{name}/env")
async def save_toolset_env(name: str, body: ToolsetEnvUpdate, profile: Optional[str] = None):
    """Persist API keys for a toolset's provider env vars.

    Writes each ``key: value`` to ``~/.marketing_hub/.env`` via ``save_env_value`` —
    the same store ``hermes tools`` writes when it prompts for keys. Keys are
    validated against the env-var allowlist for the toolset's category (the
    union of every visible provider's ``env_vars``), so the GUI can't write an
    arbitrary env var through this endpoint. A blank value is treated as
    "leave unchanged" and skipped. Returns the saved/skipped key lists and the
    refreshed ``is_set`` status. Returns 400 for unknown toolset or env keys.
    """
    from hermes_cli.tools_config import (
        TOOL_CATEGORIES,
        _get_effective_configurable_toolsets,
        _visible_providers,
    )
    from hermes_cli.config import get_env_value, save_env_value

    valid_ts = {ts_key for ts_key, _, _ in _get_effective_configurable_toolsets()}
    if name not in valid_ts:
        raise HTTPException(status_code=400, detail=f"Unknown toolset: {name}")

    with profile_scope(body.profile or profile):
        config = load_config()
        cat = TOOL_CATEGORIES.get(name)
        allowed: set[str] = set()
        if cat:
            for prov in _visible_providers(cat, config, force_fresh=True):
                for e in prov.get("env_vars", []):
                    allowed.add(e["key"])

        unknown = [k for k in body.env if k not in allowed]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown env var(s) for toolset {name}: {', '.join(sorted(unknown))}",
            )

        saved: List[str] = []
        skipped: List[str] = []
        for key, value in body.env.items():
            if value and value.strip():
                try:
                    save_env_value(key, value.strip())
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc))
                saved.append(key)
            else:
                skipped.append(key)

        status = {k: bool(get_env_value(k)) for k in allowed}
    return {"ok": True, "name": name, "saved": saved, "skipped": skipped, "is_set": status}


class ToolsetPostSetup(BaseModel):
    key: str
    profile: Optional[str] = None


@router.post("/api/tools/toolsets/{name}/post-setup")
async def run_toolset_post_setup(
    name: str, body: ToolsetPostSetup, profile: Optional[str] = None
):
    """Spawn a provider's post-setup install hook as a background action.

    Post-setup hooks (npm install for browser/Camofox, pip install for
    KittenTTS/Piper/ddgs, cua-driver fetch, etc.) are long-running and
    text-output, so this follows the spawn-action pattern: it launches
    ``hermes tools post-setup <key>`` and the frontend tails the log via
    ``GET /api/actions/tools-post-setup/status``. The ``key`` is validated
    against the declared post-setup allowlist before spawning. Returns 400
    for unknown toolset or post-setup key.

    ``profile`` spawns the hook as ``hermes -p <profile> tools post-setup``.
    Most hooks install machine-level artifacts (repo node_modules, shared
    pip packages) where the scope is inert, but hooks that read config or
    write per-profile state must see the same HERMES_HOME the rest of the
    drawer's writes targeted — so the scope is threaded for consistency.
    """
    from hermes_cli.tools_config import (
        _get_effective_configurable_toolsets,
        valid_post_setup_keys,
    )

    valid_ts = {ts_key for ts_key, _, _ in _get_effective_configurable_toolsets()}
    if name not in valid_ts:
        raise HTTPException(status_code=400, detail=f"Unknown toolset: {name}")

    if body.key not in valid_post_setup_keys():
        raise HTTPException(
            status_code=400, detail=f"Unknown post-setup key: {body.key}"
        )

    try:
        proc = spawn_hermes_action(
            _profile_cli_args(body.profile or profile)
            + ["tools", "post-setup", body.key],
            "tools-post-setup",
        )
    except HTTPException:
        raise
    except Exception as exc:
        _log.exception("Failed to spawn tools post-setup")
        raise HTTPException(
            status_code=500, detail=f"Failed to run post-setup: {exc}"
        )
    return {"ok": True, "pid": proc.pid, "name": "tools-post-setup", "key": body.key}


# ---------------------------------------------------------------------------
# Raw YAML config endpoint
# ---------------------------------------------------------------------------


class RawConfigUpdate(BaseModel):
    yaml_text: str
    profile: Optional[str] = None


