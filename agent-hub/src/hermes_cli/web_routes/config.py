"""Configuration, model assignment, and environment variable routes."""

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
from hermes_cli.model_trace import log_model_trace as _model_trace
from hermes_cli.web_routes.oauth_messaging import _channel_managed_env_keys
from hermes_cli.web_routes.helpers import (
    ACTION_LOG_FILES,
    ACTION_PROCS,
    ACTION_RESULTS,
    PROJECT_ROOT,
    action_log_dir,
    apply_llm_runtime_reload,
    record_completed_action,
    restart_gateway_after_telegram_onboarding,
    restart_gateway_after_webhook_enable,
    spawn_gateway_restart,
    spawn_hermes_action,
    tail_lines,
)

_log = logging.getLogger(__name__)

router = APIRouter(tags=["config"])

from hermes_cli.web_routes.deps import require_token

_reveal_timestamps: List[float] = []
_REVEAL_MAX_PER_WINDOW = 5
_REVEAL_WINDOW_SECONDS = 30

# ---------------------------------------------------------------------------
# Config schema — auto-generated from DEFAULT_CONFIG
# ---------------------------------------------------------------------------

# Manual overrides for fields that need select options or custom types
_SCHEMA_OVERRIDES: Dict[str, Dict[str, Any]] = {
    "model": {
        "type": "string",
        "description": "Default model (e.g. anthropic/claude-sonnet-4.6)",
        "category": "general",
    },
    "model_context_length": {
        "type": "number",
        "description": "Context window override (0 = auto-detect from model metadata)",
        "category": "general",
    },
    "terminal.backend": {
        "type": "select",
        "description": "Terminal execution backend",
        "options": ["local", "docker", "ssh", "modal", "daytona", "singularity"],
    },
    "terminal.modal_mode": {
        "type": "select",
        "description": "Modal sandbox mode",
        "options": ["sandbox", "function"],
    },
    "tts.provider": {
        "type": "select",
        "description": "Text-to-speech provider",
        "options": ["edge", "elevenlabs", "openai", "neutts"],
    },
    "stt.provider": {
        "type": "select",
        "description": "Speech-to-text provider",
        # "mistral" temporarily removed — mistralai PyPI package quarantined
        # (malicious 2.4.6 release on 2026-05-12). Restore once available.
        "options": ["local", "groq", "openai", "xai", "elevenlabs"],
    },
    "stt.elevenlabs.model_id": {
        "type": "select",
        "description": "ElevenLabs Scribe model",
        "options": ["scribe_v2", "scribe_v1"],
    },
    "display.skin": {
        "type": "select",
        "description": "CLI visual theme",
        "options": ["default", "ares", "mono", "slate"],
    },
    "dashboard.theme": {
        "type": "select",
        "description": "Web dashboard visual theme",
        "options": ["default", "midnight", "ember", "mono", "cyberpunk", "rose", "lightgray"],
    },
    "display.resume_display": {
        "type": "select",
        "description": "How resumed sessions display history",
        "options": ["minimal", "full", "off"],
    },
    "display.busy_input_mode": {
        "type": "select",
        "description": "Input behavior while agent is running",
        "options": ["interrupt", "queue", "steer"],
    },
    "memory.provider": {
        "type": "select",
        "description": "Memory provider plugin",
        # options filled dynamically in get_schema() via discover_memory_providers()
        "options": ["builtin"],
    },
    "approvals.mode": {
        "type": "select",
        "description": "Dangerous command approval mode",
        "options": ["ask", "yolo", "deny"],
    },
    "context.engine": {
        "type": "select",
        "description": "Context management engine",
        "options": ["default", "custom"],
    },
    "human_delay.mode": {
        "type": "select",
        "description": "Simulated typing delay mode",
        "options": ["off", "typing", "fixed"],
    },
    "logging.level": {
        "type": "select",
        "description": "Log level for agent.log",
        "options": ["DEBUG", "INFO", "WARNING", "ERROR"],
    },
    "agent.service_tier": {
        "type": "select",
        "description": "API service tier (OpenAI/Anthropic)",
        "options": ["", "auto", "default", "flex"],
    },
    "delegation.reasoning_effort": {
        "type": "select",
        "description": "Reasoning effort for delegated subagents",
        "options": ["", "low", "medium", "high"],
    },
    "updates.non_interactive_local_changes": {
        "type": "select",
        "description": (
            "When the chat app / gateway updates Hermes (no terminal prompt), "
            "what to do with uncommitted local source edits. 'stash' keeps them "
            "and re-applies them after the update; 'discard' throws them away. "
            "Terminal updates always ask, regardless of this setting."
        ),
        "options": ["stash", "discard"],
    },
}

# Categories with fewer fields get merged into "general" to avoid tab sprawl.
_CATEGORY_MERGE: Dict[str, str] = {
    "privacy": "security",
    "context": "agent",
    "skills": "agent",
    "cron": "agent",
    "network": "agent",
    "checkpoints": "agent",
    "approvals": "security",
    "human_delay": "display",
    "dashboard": "display",
    "code_execution": "agent",
    "prompt_caching": "agent",
    "goals": "agent",
    "updates": "general",
    # `onboarding.profile_build` is the only schema-surfaced onboarding field
    # (`onboarding.seen` is an internal latch dict, not a user setting), so fold
    # it into the agent tab rather than spawning a one-field orphan category.
    "onboarding": "agent",
    # Only `telegram.reactions` currently lives under telegram — fold it in
    # with the other messaging-platform config (discord) so it isn't an
    # orphan tab of one field.
    "telegram": "discord",
}

# Display order for tabs — unlisted categories sort alphabetically after these.
_CATEGORY_ORDER = [
    "general", "agent", "terminal", "display", "delegation",
    "memory", "compression", "security", "browser", "voice",
    "tts", "stt", "logging", "discord", "auxiliary",
]


def _infer_type(value: Any) -> str:
    """Infer a UI field type from a Python value."""
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "number"
    if isinstance(value, float):
        return "number"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return "string"


def _build_schema_from_config(
    config: Dict[str, Any],
    prefix: str = "",
) -> Dict[str, Dict[str, Any]]:
    """Walk DEFAULT_CONFIG and produce a flat dot-path → field schema dict."""
    schema: Dict[str, Dict[str, Any]] = {}
    for key, value in config.items():
        full_key = f"{prefix}.{key}" if prefix else key

        # Skip internal / version keys
        if full_key in {"_config_version",}:
            continue

        # Category is the first path component for nested keys, or "general"
        # for top-level scalar fields (model, toolsets, timezone, etc.).
        if prefix:
            category = prefix.split(".")[0]
        elif isinstance(value, dict):
            category = key
        else:
            category = "general"

        if isinstance(value, dict):
            # Recurse into nested dicts
            schema.update(_build_schema_from_config(value, full_key))
        else:
            entry: Dict[str, Any] = {
                "type": _infer_type(value),
                "description": full_key.replace(".", " → ").replace("_", " ").title(),
                "category": category,
            }
            # Apply manual overrides
            if full_key in _SCHEMA_OVERRIDES:
                entry.update(_SCHEMA_OVERRIDES[full_key])
            # Merge small categories
            entry["category"] = _CATEGORY_MERGE.get(entry["category"], entry["category"])
            schema[full_key] = entry
    return schema


CONFIG_SCHEMA = _build_schema_from_config(DEFAULT_CONFIG)

_MEMORY_PROVIDER_FIELD = "memory.provider"


def _memory_provider_schema_options() -> List[str]:
    """Select options for ``memory.provider`` — builtin + discovered plugins."""
    options: List[str] = ["builtin"]
    seen = {"builtin"}
    try:
        from plugins.memory import discover_memory_providers

        for name, _description, _available in discover_memory_providers():
            if name and name not in seen:
                options.append(name)
                seen.add(name)
    except Exception:
        _log.warning(
            "discover_memory_providers failed; memory.provider schema "
            "will only list builtin",
            exc_info=True,
        )
    return options


def _schema_with_dynamic_fields() -> Dict[str, Dict[str, Any]]:
    """Return CONFIG_SCHEMA with runtime-discovered select options patched in."""
    fields = copy.deepcopy(CONFIG_SCHEMA)
    mem_field = fields.get(_MEMORY_PROVIDER_FIELD)
    if mem_field is not None:
        mem_field["options"] = _memory_provider_schema_options()
    return fields

# Inject virtual fields that don't live in DEFAULT_CONFIG but are surfaced
# by the normalize/denormalize cycle.  Insert model_context_length right after
# the "model" key so it renders adjacent in the frontend.
_mcl_entry = _SCHEMA_OVERRIDES["model_context_length"]
_ordered_schema: Dict[str, Dict[str, Any]] = {}
for _k, _v in CONFIG_SCHEMA.items():
    _ordered_schema[_k] = _v
    if _k == "model":
        _ordered_schema["model_context_length"] = _mcl_entry
CONFIG_SCHEMA = _ordered_schema


class ConfigUpdate(BaseModel):
    config: dict
    profile: Optional[str] = None


class EnvVarUpdate(BaseModel):
    key: str
    value: str
    profile: Optional[str] = None
    # Optional bearer key for the connectivity probe of a custom/local endpoint
    # (``key == "OPENAI_BASE_URL"``). Self-hosted endpoints that gate
    # ``/v1/models`` behind auth otherwise look "reachable but empty"; sending
    # the key lets the probe enumerate the served models. Ignored for the
    # regular PUT /api/env path (which only reads key/value).
    api_key: str = ""


class EnvVarDelete(BaseModel):
    key: str
    profile: Optional[str] = None


class EnvVarReveal(BaseModel):
    key: str
    profile: Optional[str] = None


class ModelAssignment(BaseModel):
    """Payload for POST /api/model/set — assign a provider/model to a slot.

    scope="main"        → writes model.provider + model.default
    scope="auxiliary"   → writes auxiliary.<task>.provider + auxiliary.<task>.model
    scope="auxiliary" with task=""  → applied to every auxiliary.* slot
    scope="auxiliary" with task="__reset__"  → resets every slot to provider="auto"
    """
    scope: str
    provider: str
    model: str
    task: str = ""
    # Optional OpenAI-compatible endpoint URL. Only honored for custom/local
    # providers on the main slot — lets the GUI configure a self-hosted endpoint
    # (vLLM, llama.cpp, Ollama, …) that needs no API key. The runtime resolver
    # reads model.base_url from config (it ignores OPENAI_BASE_URL), so this is
    # the path that actually wires a local endpoint into resolution.
    base_url: str = ""
    # Optional API key for a custom/local endpoint. Persisted to
    # ``model.api_key`` (where the runtime resolver reads it) so a self-hosted
    # endpoint that requires auth works from the GUI — mirrors the key the
    # ``hermes model`` custom flow collects. Honored only on the main slot for
    # custom/local providers.
    api_key: str = ""
    confirm_expensive_model: bool = False
    profile: Optional[str] = None


def normalize_main_model_assignment(provider: str, model: str) -> tuple[str, str]:
    """Normalize a main-slot (provider, model) pair before persisting.

    The Models page has two assignment paths and only one of them was safe:

    - The "Change" picker sends a real Hermes provider slug — fine.
    - The per-card "Use as → Main model" menu sends ``entry.provider``
      from the analytics rows, falling back to the model's VENDOR prefix
      (``modelVendor("anthropic/claude-opus-4.6") == "anthropic"``) when
      the session row has no ``billing_provider`` (older sessions, NULL
      rows).  That wrote ``provider: anthropic`` +
      ``default: anthropic/claude-opus-4.6`` to config — a vendor-prefixed
      OpenRouter slug on the NATIVE Anthropic provider.  New sessions then
      400 against api.anthropic.com ("model: anthropic/claude-opus-4.6 not
      found") and the user reads it as "changing models does nothing".

    Two repairs, both at this single chokepoint so every caller inherits:

    1. Vendor-name → Hermes-provider mapping: when the provider string is
       not a known Hermes provider/alias (e.g. ``moonshotai``, ``x-ai`` is
       known but ``poolside`` isn't) but the model is a vendor-prefixed
       aggregator slug, keep the user's CURRENT aggregator if they're on
       one, else fall back to openrouter.
    2. Model-format normalization for the resolved provider via
       ``normalize_model_for_provider`` (e.g. ``anthropic/claude-opus-4.6``
       on native anthropic → ``claude-opus-4-6``).
    """
    from hermes_cli.models import _KNOWN_PROVIDER_NAMES, normalize_provider
    from hermes_cli.model_normalize import normalize_model_for_provider

    prov_in = (provider or "").strip()
    model_in = (model or "").strip()
    canonical = normalize_provider(prov_in)

    if canonical not in _KNOWN_PROVIDER_NAMES and "/" in model_in:
        # Vendor prefix posing as a provider (analytics fallback). Resolve
        # against the user's current provider when it's an aggregator that
        # serves vendor-prefixed slugs; otherwise default to openrouter.
        try:
            cur_cfg = load_config().get("model", {})
            cur_provider = (
                str(cur_cfg.get("provider", "") or "").strip().lower()
                if isinstance(cur_cfg, dict) else ""
            )
        except Exception:
            cur_provider = ""
        from hermes_cli.models import _AGGREGATOR_PROVIDERS
        if cur_provider and normalize_provider(cur_provider) in _AGGREGATOR_PROVIDERS:
            canonical = normalize_provider(cur_provider)
            prov_in = cur_provider
        else:
            canonical = "openrouter"
            prov_in = "openrouter"

    # Custom/user-config providers keep the model verbatim — the registry
    # normalizer doesn't know their namespaces.
    if canonical in _KNOWN_PROVIDER_NAMES and not canonical.startswith("custom"):
        try:
            normalized_model = normalize_model_for_provider(model_in, canonical)
            if normalized_model:
                model_in = normalized_model
        except Exception:
            _log.debug("model normalization failed for %s/%s", prov_in, model_in, exc_info=True)

    return prov_in, model_in


def apply_main_model_assignment(
    model_cfg: "Any", provider: str, model: str, base_url: str = "", api_key: str = ""
) -> dict:
    """Apply a main-slot model assignment to a ``model`` config dict in place.

    Sets ``provider``/``default``, then reconciles ``base_url``:

    - An explicitly supplied ``base_url`` is always persisted (covers
      ``custom``/local endpoints and any provider whose key is bound to a
      non-default host).
    - Otherwise, a stale ``base_url`` is cleared ONLY when switching to a
      *different* provider — that URL belonged to the old provider. When the
      provider is unchanged and no new URL is supplied, the existing
      ``base_url`` is preserved. This keeps a user's custom endpoint (e.g. a
      Xiaomi MiMo Token Plan host, ``https://token-plan-*.xiaomimimo.com/v1``)
      alive when they merely re-pick a model under the same provider — picking
      a model previously wiped it, forcing the registry default and breaking
      Token Plan keys.

    The runtime resolver reads ``model.base_url`` from config (it ignores
    ``OPENAI_BASE_URL``) and only honors it when the configured provider matches
    and the pool entry is on the registry default, so preserving it here is what
    lets the override actually route. The hardcoded ``context_length`` override
    is always dropped since the new model may have a different context window.

    Returns the same dict (coerced to a fresh dict if the input wasn't one) so
    callers can assign it straight back onto the model config.
    """
    if not isinstance(model_cfg, dict):
        model_cfg = {}
    prev_provider = str(model_cfg.get("provider") or "").strip().lower()
    new_provider = provider.strip().lower()
    model_cfg["provider"] = provider
    model_cfg["default"] = model
    if base_url.strip():
        model_cfg["base_url"] = base_url.strip()
    elif model_cfg.get("base_url") and new_provider != prev_provider:
        # Switching providers: the old URL belonged to the old provider, drop
        # it so the new provider's default endpoint is used. Same-provider
        # re-assignment keeps the user's configured base_url intact.
        model_cfg["base_url"] = ""
    # The endpoint key follows the same lifecycle as base_url: an explicit key
    # is always persisted; an existing key is dropped only when switching to a
    # different provider (it belonged to the old endpoint), and preserved on a
    # same-provider re-pick so re-selecting a model doesn't wipe the key.
    if api_key.strip():
        model_cfg["api_key"] = api_key.strip()
    elif model_cfg.get("api_key") and new_provider != prev_provider:
        model_cfg["api_key"] = ""
    model_cfg.pop("context_length", None)
    return model_cfg


def _normalize_config_for_web(config: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize config for the web UI.

    Hermes supports ``model`` as either a bare string (``"anthropic/claude-sonnet-4"``)
    or a dict (``{default: ..., provider: ..., base_url: ...}``).  The schema is built
    from DEFAULT_CONFIG where ``model`` is a string, but user configs often have the
    dict form.  Normalize to the string form so the frontend schema matches.

    Also surfaces ``model_context_length`` as a top-level field so the web UI can
    display and edit it.  A value of 0 means "auto-detect".
    """
    config = dict(config)  # shallow copy
    model_val = config.get("model")
    if isinstance(model_val, dict):
        # Extract context_length before flattening the dict
        ctx_len = model_val.get("context_length", 0)
        config["model"] = model_val.get("default", model_val.get("name", ""))
        config["model_context_length"] = ctx_len if isinstance(ctx_len, int) else 0
    else:
        config["model_context_length"] = 0
    return config


@router.get("/api/config")
async def get_config(profile: Optional[str] = None):
    with profile_scope(profile):
        config = _normalize_config_for_web(load_config())
    # Strip internal keys that the frontend shouldn't see or send back
    return {k: v for k, v in config.items() if not k.startswith("_")}


@router.get("/api/config/defaults")
async def get_defaults():
    return DEFAULT_CONFIG


@router.get("/api/config/schema")
async def get_schema():
    return {"fields": _schema_with_dynamic_fields(), "category_order": _CATEGORY_ORDER}


_EMPTY_MODEL_INFO: dict = {
    "model": "",
    "provider": "",
    "auto_context_length": 0,
    "config_context_length": 0,
    "effective_context_length": 0,
    "capabilities": {},
}


@router.get("/api/model/info")
def get_model_info(profile: Optional[str] = None):
    """Return resolved model metadata for the currently configured model.

    Calls the same context-length resolution chain the agent uses, so the
    frontend can display "Auto-detected: 200K" alongside the override field.
    Also returns model capabilities (vision, reasoning, tools) when available.
    """
    try:
        with profile_scope(profile):
            from hermes_constants import get_config_path

            cfg = load_config()
            config_path = get_config_path()
        model_cfg = cfg.get("model", "")

        # Extract model name and provider from the config
        if isinstance(model_cfg, dict):
            model_name = model_cfg.get("default", model_cfg.get("name", ""))
            provider = model_cfg.get("provider", "")
            base_url = model_cfg.get("base_url", "")
            config_ctx = model_cfg.get("context_length")
        else:
            model_name = str(model_cfg) if model_cfg else ""
            provider = ""
            base_url = ""
            config_ctx = None

        if not model_name:
            return dict(_EMPTY_MODEL_INFO, provider=provider)

        # Resolve auto-detected context length (pass config_ctx=None to get
        # purely auto-detected value, then separately report the override)
        try:
            from agent.model_metadata import get_model_context_length
            auto_ctx = get_model_context_length(
                model=model_name,
                base_url=base_url,
                provider=provider,
                config_context_length=None,  # ignore override — we want auto value
            )
        except Exception:
            auto_ctx = 0

        config_ctx_int = 0
        if isinstance(config_ctx, int) and config_ctx > 0:
            config_ctx_int = config_ctx

        # Effective is what the agent actually uses
        effective_ctx = config_ctx_int if config_ctx_int > 0 else auto_ctx

        # Try to get model capabilities from models.dev
        caps = {}
        try:
            from agent.models_dev import get_model_capabilities
            mc = get_model_capabilities(provider=provider, model=model_name)
            if mc is not None:
                caps = {
                    "supports_tools": mc.supports_tools,
                    "supports_vision": mc.supports_vision,
                    "supports_reasoning": mc.supports_reasoning,
                    "context_window": mc.context_window,
                    "max_output_tokens": mc.max_output_tokens,
                    "model_family": mc.model_family,
                }
        except Exception:
            pass

        _model_trace(
            "api.model.info",
            profile=profile or "",
            config_path=str(config_path),
            model=model_name,
            provider=provider,
        )
        return {
            "model": model_name,
            "provider": provider,
            "auto_context_length": auto_ctx,
            "config_context_length": config_ctx_int,
            "effective_context_length": effective_ctx,
            "capabilities": caps,
        }
    except HTTPException:
        # Unknown/invalid profile must surface as 404, not degrade into a
        # 200 with empty model info (which would render as "no model set").
        raise
    except Exception:
        _log.exception("GET /api/model/info failed")
        return dict(_EMPTY_MODEL_INFO)


# ---------------------------------------------------------------------------
# Model assignment — pick provider+model for main slot or auxiliary slots.
# Mirrors the model.options JSON-RPC from tui_gateway but uses REST so the
# Models page (which has no chat PTY open) can drive it.
# ---------------------------------------------------------------------------

# Canonical auxiliary task slots. Keep in sync with DEFAULT_CONFIG["auxiliary"]
# in hermes_cli/config.py — listed here for deterministic ordering in the UI.
_AUX_TASK_SLOTS: Tuple[str, ...] = (
    "vision",
    "web_extract",
    "compression",
    "skills_hub",
    "approval",
    "mcp",
    "title_generation",
    "triage_specifier",
    "kanban_decomposer",
    "profile_describer",
    "curator",
)


@router.get("/api/model/options")
def get_model_options(profile: Optional[str] = None):
    """Return authenticated providers + their curated model lists.

    REST equivalent of the ``model.options`` JSON-RPC on tui_gateway, so the
    dashboard Models page can render the picker without a live chat session.
    The response shape matches ``model.options`` 1:1 so ``ModelPickerDialog``
    can share the same types.

    ``profile`` scopes the picker context (current model/provider, custom
    providers from config, per-profile .env auth state) so the Models page
    reads the SAME profile /api/model/set writes.
    """
    try:
        from hermes_cli.inventory import build_models_payload, load_picker_context

        # include_unconfigured + picker_hints + canonical_order mirror the
        # tui_gateway `model.options` JSON-RPC handler exactly, so every GUI
        # surface fed by this endpoint (Settings → Model, the first-run
        # onboarding picker) sees the SAME full provider universe `hermes model`
        # exposes — not just the authenticated subset. Unconfigured providers
        # come back as skeleton rows carrying `authenticated=False` +
        # `auth_type`/`key_env`/`warning` so the GUI can render a setup
        # affordance instead of hiding the provider entirely.
        with profile_scope(profile):
            return build_models_payload(
                load_picker_context(),
                max_models=50,
                include_unconfigured=True,
                picker_hints=True,
                canonical_order=True,
                pricing=True,
                capabilities=True,
            )
    except HTTPException:
        raise
    except Exception:
        _log.exception("GET /api/model/options failed")
        raise HTTPException(status_code=500, detail="Failed to list model options")


@router.get("/api/model/recommended-default")
def get_recommended_default_model(provider: str = ""):
    """Return the recommended default model for a freshly-authenticated provider.

    Mirrors the model-curation `hermes model` does so GUI onboarding lands on a
    sensible default instead of blindly taking the first curated entry. For
    Nous this honors the user's free/paid tier: free users get a free model,
    paid users get the full curated default. For any other provider it falls
    back to the first curated model (same as before).

    Response: {"provider": str, "model": str, "free_tier": bool | None}
    where free_tier is True/False for Nous and None otherwise. `model` may be
    empty if nothing could be resolved (caller degrades gracefully).
    """
    slug = (provider or "").strip().lower()

    if slug == "official":
        try:
            from hermes_cli.official_gateway_models import get_official_default_model

            model = get_official_default_model()
            return {"provider": "official", "model": model, "free_tier": None}
        except Exception:
            _log.exception("GET /api/model/recommended-default (official) failed")
            return {"provider": "official", "model": "", "free_tier": None}

    if slug == "nous":
        try:
            from hermes_cli.models import (
                get_curated_nous_model_ids,
                get_pricing_for_provider,
                check_nous_free_tier,
                partition_nous_models_by_tier,
                union_with_portal_free_recommendations,
                union_with_portal_paid_recommendations,
            )
            from hermes_cli.auth import get_provider_auth_state

            model_ids = get_curated_nous_model_ids()
            pricing = get_pricing_for_provider("nous") or {}
            free_tier = check_nous_free_tier(force_fresh=True)

            portal_url = ""
            try:
                state = get_provider_auth_state("nous") or {}
                portal_url = state.get("portal_base_url", "") or ""
            except Exception:
                portal_url = ""

            if free_tier:
                model_ids, pricing = union_with_portal_free_recommendations(
                    model_ids, pricing, portal_url
                )
                model_ids, _unavailable = partition_nous_models_by_tier(
                    model_ids, pricing, free_tier=True
                )
            else:
                model_ids, pricing = union_with_portal_paid_recommendations(
                    model_ids, pricing, portal_url
                )

            model = model_ids[0] if model_ids else ""
            return {"provider": "nous", "model": model, "free_tier": bool(free_tier)}
        except Exception:
            _log.exception("GET /api/model/recommended-default (nous) failed")
            return {"provider": "nous", "model": "", "free_tier": None}

    # Non-Nous: first curated model for the provider, matching prior behaviour.
    try:
        from hermes_cli.inventory import build_models_payload, load_picker_context

        payload = build_models_payload(load_picker_context(), max_models=50)
        for row in payload.get("providers", []):
            if str(row.get("slug", "")).lower() == slug:
                models = row.get("models") or []
                return {"provider": slug, "model": models[0] if models else "", "free_tier": None}
        return {"provider": slug, "model": "", "free_tier": None}
    except Exception:
        _log.exception("GET /api/model/recommended-default failed")
        return {"provider": slug, "model": "", "free_tier": None}


@router.get("/api/model/auxiliary")
def get_auxiliary_models(profile: Optional[str] = None):
    """Return current auxiliary task assignments.

    Shape:
      {
        "tasks": [
          {"task": "vision", "provider": "auto", "model": "", "base_url": ""},
          ...
        ],
        "main": {"provider": "openrouter", "model": "anthropic/claude-opus-4.7"},
      }

    ``profile`` scopes the read — without it, the Models page would show
    the dashboard profile's auxiliary pins while /api/model/set wrote the
    selected profile's (read/write asymmetry).
    """
    try:
        with profile_scope(profile):
            cfg = load_config()
        aux_cfg = cfg.get("auxiliary", {})
        if not isinstance(aux_cfg, dict):
            aux_cfg = {}

        tasks = []
        for slot in _AUX_TASK_SLOTS:
            slot_cfg = aux_cfg.get(slot, {}) if isinstance(aux_cfg.get(slot), dict) else {}
            tasks.append({
                "task": slot,
                "provider": str(slot_cfg.get("provider", "auto") or "auto"),
                "model": str(slot_cfg.get("model", "") or ""),
                "base_url": str(slot_cfg.get("base_url", "") or ""),
            })

        model_cfg = cfg.get("model", {})
        if isinstance(model_cfg, dict):
            main = {
                "provider": str(model_cfg.get("provider", "") or ""),
                "model": str(model_cfg.get("default", model_cfg.get("name", "")) or ""),
            }
        else:
            main = {"provider": "", "model": str(model_cfg) if model_cfg else ""}

        return {"tasks": tasks, "main": main}
    except HTTPException:
        raise
    except Exception:
        _log.exception("GET /api/model/auxiliary failed")
        raise HTTPException(status_code=500, detail="Failed to read auxiliary config")


@router.post("/api/model/set")
async def set_model_assignment(body: ModelAssignment, profile: Optional[str] = None):
    """Assign a model to the main slot or an auxiliary task slot.

    Writes to ``~/.marketing_hub/config.yaml`` — applies to **new** sessions only.
    The currently running chat PTY (if any) is not affected; use the
    ``/model`` slash command inside a chat to hot-swap that specific session.
    """
    scope = (body.scope or "").strip().lower()
    provider = (body.provider or "").strip()
    model = (body.model or "").strip()
    task = (body.task or "").strip().lower()
    base_url = (body.base_url or "").strip()
    api_key = (body.api_key or "").strip()

    if scope not in {"main", "auxiliary"}:
        raise HTTPException(status_code=400, detail="scope must be 'main' or 'auxiliary'")

    try:
        # Expensive-model warning runs BEFORE the profile scope is entered:
        # profile_scope must never be held across an await (the RLock is
        # reentrant per-thread, so a second coroutine interleaving on the
        # event-loop thread could cross-restore the module globals).
        if model and not body.confirm_expensive_model:
            try:
                from hermes_cli.model_cost_guard import expensive_model_warning

                # Pricing lookup can hit models.dev / a /models endpoint on a
                # cache miss — keep it off the event loop.
                warning = await asyncio.to_thread(
                    expensive_model_warning,
                    model,
                    provider=provider,
                    base_url=base_url,
                )
            except Exception:
                warning = None
            if warning is not None:
                return {
                    "ok": False,
                    "scope": scope,
                    "provider": provider,
                    "model": model,
                    "confirm_required": True,
                    "confirm_message": warning.message,
                }

        def _apply_assignment():
            with profile_scope(body.profile or profile):
                return _apply_model_assignment_sync(
                    scope, provider, model, task, base_url, api_key
                )

        result = await asyncio.to_thread(_apply_assignment)
        if isinstance(result, dict) and result.get("ok") and result.get("scope") == "main":
            result.update(apply_llm_runtime_reload())
        return result
    except HTTPException:
        raise
    except Exception:
        _log.exception("POST /api/model/set failed")
        raise HTTPException(status_code=500, detail="Failed to save model assignment")


def _apply_model_assignment_sync(
    scope: str, provider: str, model: str, task: str, base_url: str, api_key: str = ""
):
    """Synchronous body of POST /api/model/set.

    Runs inside ``profile_scope`` (in a worker thread) so every
    load_config/save_config lands in the requested profile.  Raises
    HTTPException for validation errors — the async wrapper re-raises them.
    """
    cfg = load_config()
    from hermes_cli.config import (
        is_integrated_named_profile_config,
        patch_config_yaml,
        read_raw_config,
    )
    profile_patch = is_integrated_named_profile_config()

    if scope == "main":
        if not provider or not model:
            raise HTTPException(status_code=400, detail="provider and model required for main")
        provider, model = normalize_main_model_assignment(provider, model)
        raw_model = cfg.get("model", {})
        if profile_patch:
            on_disk = read_raw_config().get("model", {})
            raw_model = on_disk if isinstance(on_disk, dict) else {}
        model_cfg = apply_main_model_assignment(
            raw_model if isinstance(raw_model, dict) else {},
            provider,
            model,
            base_url,
            api_key,
        )
        cfg["model"] = model_cfg

        # When switching the main provider to Nous, mirror the CLI's
        # post-model-selection behaviour (hermes_cli/main.py
        # prompt_enable_tool_gateway / tools_config apply_nous_managed_defaults):
        # auto-route any *unconfigured* tools through the Nous Tool Gateway.
        # This is purely additive — apply_nous_managed_defaults skips every
        # tool where the user already has a direct key (FIRECRAWL_API_KEY,
        # FAL_KEY, etc.) or an explicit backend/provider in config, so it
        # never overwrites a user's own setup. GUI users thus land on the
        # gateway the same way CLI users do, without a separate prompt.
        gateway_tools: list[str] = []
        if provider.strip().lower() == "nous":
            try:
                from hermes_cli.nous_subscription import apply_nous_managed_defaults
                from hermes_cli.tools_config import _get_platform_tools

                enabled = _get_platform_tools(
                    cfg, "cli", include_default_mcp_servers=False
                )
                changed = apply_nous_managed_defaults(
                    cfg,
                    enabled_toolsets=enabled,
                    force_fresh=True,
                )
                gateway_tools = sorted(changed)
            except Exception:
                # Portal lookup hiccups / non-subscriber / non-nous gating
                # must never block saving the model assignment.
                _log.debug("apply_nous_managed_defaults skipped", exc_info=True)

        if profile_patch:
            patch_config_yaml({"model": model_cfg})
            channel_shells_cleared: list[str] = []
        else:
            save_config(cfg)
            # 全局主模型变更：清掉渠道壳假绑定，Gateway 才能真正跟随系统默认
            channel_shells_cleared = []
            try:
                from plugins.mxai.cfg.agent_model_config import clear_legacy_channel_shell_models

                channel_shells_cleared = clear_legacy_channel_shell_models()
            except Exception:
                _log.debug("clear_legacy_channel_shell_models skipped", exc_info=True)

        from hermes_constants import get_config_path

        _model_trace(
            "api.model.set",
            scope=scope,
            profile=os.environ.get("HERMES_PROFILE", ""),
            config_path=str(get_config_path()),
            provider=provider,
            model=model,
            profile_patch=profile_patch,
            channel_shells_cleared=channel_shells_cleared,
        )

        # Register a named ``custom_providers`` entry for a custom/local
        # endpoint, mirroring the ``hermes model`` custom flow
        # (_save_custom_provider). Without this the endpoint only lives in
        # ``model.*`` and the picker has no proper ready row for it — the
        # GUI then surfaces a "needs setup" dead-end on the bare ``custom``
        # provider. Dedups by base_url, so re-saving is idempotent.
        if provider.strip().lower() in {"custom", "local"} and base_url:
            try:
                from hermes_cli.main import _auto_provider_name, _save_custom_provider

                _save_custom_provider(
                    base_url,
                    api_key,
                    model,
                    name=_auto_provider_name(base_url),
                )
            except Exception:
                # Never block the assignment on the bookkeeping write —
                # model.* is already persisted and routable.
                _log.debug("custom_providers registration skipped", exc_info=True)

        # Surface auxiliary slots still pinned to a *different* provider than
        # the new main one. Switching the main model does NOT touch aux pins
        # (they're independent, sticky per-task overrides — see
        # auxiliary_client._resolve_auto). A user who switches main away from
        # a now-unpaid provider (e.g. nous with $0 balance) keeps paying 402s
        # on every background aux call until they reset those pins. We never
        # auto-clear them — pinning aux to a cheaper/different model is a
        # legitimate config — but we tell the caller so the UI can offer a
        # "reset to main" nudge instead of silently burning credits.
        new_provider = provider.strip().lower()
        stale_aux: list[dict] = []
        aux_cfg = cfg.get("auxiliary", {})
        if isinstance(aux_cfg, dict):
            for slot in _AUX_TASK_SLOTS:
                slot_cfg = aux_cfg.get(slot)
                if not isinstance(slot_cfg, dict):
                    continue
                slot_provider = str(slot_cfg.get("provider", "") or "").strip()
                if (
                    slot_provider
                    and slot_provider.lower() not in {"auto", ""}
                    and slot_provider.lower() != new_provider
                ):
                    stale_aux.append({
                        "task": slot,
                        "provider": slot_provider,
                        "model": str(slot_cfg.get("model", "") or ""),
                    })

        return {
            "ok": True,
            "scope": "main",
            "provider": provider,
            "model": model,
            "base_url": model_cfg.get("base_url", ""),
            "gateway_tools": gateway_tools,
            "stale_aux": stale_aux,
            "channel_shells_cleared": channel_shells_cleared,
        }

    # scope == "auxiliary"
    aux = cfg.get("auxiliary")
    if not isinstance(aux, dict):
        aux = {}
    if profile_patch:
        on_disk_aux = read_raw_config().get("auxiliary", {})
        aux = copy.deepcopy(on_disk_aux) if isinstance(on_disk_aux, dict) else {}

    if task == "__reset__":
        # Reset every slot to provider="auto", model="" — keeps other fields intact.
        for slot in _AUX_TASK_SLOTS:
            slot_cfg = aux.get(slot)
            if not isinstance(slot_cfg, dict):
                slot_cfg = {}
            slot_cfg["provider"] = "auto"
            slot_cfg["model"] = ""
            aux[slot] = slot_cfg
        cfg["auxiliary"] = aux
        if profile_patch:
            patch_config_yaml({"auxiliary": aux})
        else:
            save_config(cfg)
        return {"ok": True, "scope": "auxiliary", "reset": True}

    if not provider:
        raise HTTPException(status_code=400, detail="provider required for auxiliary")

    targets = [task] if task else list(_AUX_TASK_SLOTS)
    for slot in targets:
        if slot not in _AUX_TASK_SLOTS:
            raise HTTPException(status_code=400, detail=f"unknown auxiliary task: {slot}")
        slot_cfg = aux.get(slot)
        if not isinstance(slot_cfg, dict):
            slot_cfg = {}
        slot_cfg["provider"] = provider
        slot_cfg["model"] = model
        aux[slot] = slot_cfg

    cfg["auxiliary"] = aux
    if profile_patch:
        patch_config_yaml({"auxiliary": aux})
    else:
        save_config(cfg)
    return {
        "ok": True,
        "scope": "auxiliary",
        "tasks": targets,
        "provider": provider,
        "model": model,
    }




def _denormalize_config_from_web(config: Dict[str, Any]) -> Dict[str, Any]:
    """Reverse _normalize_config_for_web before saving.

    Reconstructs ``model`` as a dict by reading the current on-disk config
    to recover model subkeys (provider, base_url, api_mode, etc.) that were
    stripped from the GET response.  The frontend only sees model as a flat
    string; the rest is preserved transparently.

    Also handles ``model_context_length`` — writes it back into the model dict
    as ``context_length``.  A value of 0 or absent means "auto-detect" (omitted
    from the dict so get_model_context_length() uses its normal resolution).
    """
    config = dict(config)
    # Remove any _model_meta that might have leaked in (shouldn't happen
    # with the stripped GET response, but be defensive)
    config.pop("_model_meta", None)

    # Extract and remove model_context_length before processing model
    ctx_override = config.pop("model_context_length", 0)
    if not isinstance(ctx_override, int):
        try:
            ctx_override = int(ctx_override)
        except (TypeError, ValueError):
            ctx_override = 0

    model_val = config.get("model")
    if isinstance(model_val, str) and model_val:
        # Read the current disk config to recover model subkeys
        try:
            disk_config = load_config()
            disk_model = disk_config.get("model")
            if isinstance(disk_model, dict):
                # Preserve all subkeys, update default with the new value
                disk_model["default"] = model_val
                # Write context_length into the model dict (0 = remove/auto)
                if ctx_override > 0:
                    disk_model["context_length"] = ctx_override
                else:
                    disk_model.pop("context_length", None)
                config["model"] = disk_model
            # Model was previously a bare string — upgrade to dict if
            # user is setting a context_length override
            elif ctx_override > 0:
                config["model"] = {
                    "default": model_val,
                    "context_length": ctx_override,
                }
        except Exception:
            pass  # can't read disk config — just use the string form
    return config


@router.put("/api/config")
async def update_config(body: ConfigUpdate, profile: Optional[str] = None):
    try:
        def _apply_config_update():
            from hermes_cli.config import _config_updates_touch_llm

            with profile_scope(body.profile or profile):
                cfg = _denormalize_config_from_web(body.config)
                touch_llm = _config_updates_touch_llm(cfg)
                save_config(cfg)
                return touch_llm

        touch_llm = await asyncio.to_thread(_apply_config_update)
        response: dict[str, Any] = {"ok": True}
        if touch_llm:
            response.update(apply_llm_runtime_reload())
        return response
    except HTTPException:
        raise
    except Exception:
        _log.exception("PUT /api/config failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/api/env")
async def get_env_vars(profile: Optional[str] = None):
    with profile_scope(profile):
        env_on_disk = load_env()
    channel_keys = _channel_managed_env_keys()
    result = {}
    for var_name, info in OPTIONAL_ENV_VARS.items():
        value = env_on_disk.get(var_name)
        result[var_name] = {
            "is_set": bool(value),
            "redacted_value": redact_key(value) if value else None,
            "description": info.get("description", ""),
            "url": info.get("url"),
            "category": info.get("category", ""),
            "is_password": info.get("password", False),
            "tools": info.get("tools", []),
            "advanced": info.get("advanced", False),
            # True when this var is a messaging-platform credential owned by a
            # Channels page card. The Keys/Env page uses this to hide it and
            # avoid duplicating the (richer) Channels configuration UI.
            "channel_managed": var_name in channel_keys,
        }
    return result


@router.put("/api/env")
async def set_env_var(body: EnvVarUpdate, profile: Optional[str] = None):
    try:
        with profile_scope(body.profile or profile):
            save_env_value(body.key, body.value)
        from hermes_cli.config import env_key_touches_llm_runtime

        response: dict[str, Any] = {"ok": True, "key": body.key}
        if env_key_touches_llm_runtime(body.key):
            response.update(apply_llm_runtime_reload())
        return response
    except ValueError as exc:
        # save_env_value raises ValueError for invalid names and for keys
        # on the denylist (LD_PRELOAD, PATH, PYTHONPATH, …). Surface the
        # message to the SPA so the user understands why the write was
        # refused instead of seeing an opaque 500.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        _log.exception("PUT /api/env failed")
        raise HTTPException(status_code=500, detail="Internal server error")


# Live credential probes keyed by env var. Each entry is (method, url, auth)
# where auth is "bearer" (Authorization header) or "query" (?key=). A cheap
# read-only models/key call that 401s on a bad token — enough to catch a
# mistyped key before it's persisted. Providers absent from this map (or local
# endpoints) are not network-validated; the client treats those as "unknown".
_CREDENTIAL_PROBES: dict[str, tuple[str, str]] = {
    "OPENROUTER_API_KEY": ("https://openrouter.ai/api/v1/key", "bearer"),
    "OPENAI_API_KEY": ("https://api.openai.com/v1/models", "bearer"),
    "XAI_API_KEY": ("https://api.x.ai/v1/models", "bearer"),
    "GEMINI_API_KEY": ("https://generativelanguage.googleapis.com/v1beta/models", "query"),
    "MOARK_API_KEY": ("https://api.moark.com/v1/models", "bearer"),
    "DEEPSEEK_API_KEY": ("https://api.deepseek.com/v1/models", "bearer"),
    "DASHSCOPE_API_KEY": ("https://dashscope-intl.aliyuncs.com/compatible-mode/v1/models", "bearer"),
}


def _resolve_env_credential_probe(env_key: str) -> tuple[str, str] | None:
    """Map an env var (e.g. MOARK_API_KEY) to a live probe URL + auth mode."""
    static = _CREDENTIAL_PROBES.get(env_key)
    if static:
        return static
    try:
        import os

        from hermes_cli.auth import PROVIDER_REGISTRY
        from hermes_cli.config import get_env_value
    except ImportError:
        return None

    for pcfg in PROVIDER_REGISTRY.values():
        if env_key not in (pcfg.api_key_env_vars or ()):
            continue
        base = (pcfg.inference_base_url or "").strip()
        if pcfg.base_url_env_var:
            override = (get_env_value(pcfg.base_url_env_var) or os.environ.get(pcfg.base_url_env_var, "")).strip()
            if override:
                base = override
        if base:
            return (base.rstrip("/") + "/models", "bearer")
    return None


def _parse_model_ids(resp: "Any") -> List[str]:
    """Extract model ids from an OpenAI-compatible ``/v1/models`` response.

    Tolerant of the common shapes: ``{"data": [{"id": ...}]}`` (OpenAI / vLLM /
    llama.cpp) and a bare ``{"data": ["id", ...]}``. Returns ``[]`` on any
    parse/HTTP error so a slightly non-standard endpoint never hard-blocks.
    """
    try:
        if not resp.is_success:
            return []
        payload = resp.json()
    except Exception:
        return []
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return []
    ids: List[str] = []
    for item in data:
        if isinstance(item, dict):
            mid = str(item.get("id") or "").strip()
        else:
            mid = str(item or "").strip()
        if mid:
            ids.append(mid)
    return ids


@router.post("/api/providers/validate")
async def validate_provider_credential(
    body: EnvVarUpdate, request: Request, profile: Optional[str] = None
):
    """Live-probe a provider credential before it's saved.

    Returns {ok, reachable, message}. ok=True means the provider accepted the
    key; ok=False + reachable=True means the key is bad (caller should block);
    reachable=False means the network probe couldn't run (caller may save with
    a warning rather than hard-blocking offline users).

    When ``value`` is empty, reads the persisted credential from ~/.marketing_hub/.env
    so the Env page can test after save without re-revealing the secret.
    """
    require_token(request)
    import httpx

    key = (body.key or "").strip()
    value = (body.value or "").strip()

    with profile_scope(body.profile or profile):
        if not value:
            try:
                import os

                from hermes_cli.config import get_env_value

                value = (get_env_value(key) or os.environ.get(key, "") or "").strip()
            except Exception:
                value = ""

    if not value:
        return {"ok": False, "reachable": True, "message": "Enter a value first."}

    # Local / custom endpoint: validate connectivity, not auth — any HTTP
    # response (even 401) proves the endpoint is up. Also surface the model
    # ids the endpoint advertises (OpenAI ``/v1/models`` shape) so the GUI can
    # auto-pick a default without asking the user to type a model name.
    if key == "OPENAI_BASE_URL":
        url = value.rstrip("/") + "/models"
        # Send the optional API key so endpoints that require auth on
        # ``/v1/models`` (many hosted OpenAI-compatible servers) still enumerate
        # their models instead of returning an empty list behind a 401.
        api_key = (body.api_key or "").strip()
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
        try:
            with httpx.Client(timeout=httpx.Timeout(8.0)) as client:
                resp = client.get(url, headers=headers)
            models = _parse_model_ids(resp)
            return {
                "ok": True,
                "reachable": True,
                "message": "",
                "models": models,
                "model_count": len(models),
            }
        except Exception:
            return {"ok": False, "reachable": False, "message": f"Could not reach {url}."}

    probe = _resolve_env_credential_probe(key)
    if not probe:
        # No probe for this provider — can't validate, don't block.
        return {"ok": True, "reachable": False, "message": ""}

    url, auth = probe
    headers = {"Accept": "application/json"}
    params = {}
    if auth == "bearer":
        headers["Authorization"] = f"Bearer {value}"
    else:
        params["key"] = value

    try:
        with httpx.Client(timeout=httpx.Timeout(10.0)) as client:
            resp = client.get(url, headers=headers, params=params)
    except Exception:
        return {"ok": False, "reachable": False, "message": "Could not reach the provider to verify the key."}

    if resp.status_code in (401, 403):
        return {"ok": False, "reachable": True, "message": "That API key was rejected. Double-check it and try again."}
    if resp.status_code == 429 or resp.is_success:
        # 429 = key is valid but rate-limited; success = valid.
        models = _parse_model_ids(resp) if auth == "bearer" and "/models" in url else []
        return {
            "ok": True,
            "reachable": True,
            "message": "",
            "models": models,
            "model_count": len(models),
        }
    return {"ok": False, "reachable": True, "message": f"Provider returned HTTP {resp.status_code} for this key."}


@router.delete("/api/env")
async def remove_env_var(body: EnvVarDelete, profile: Optional[str] = None):
    try:
        with profile_scope(body.profile or profile):
            removed = remove_env_value(body.key)
        if not removed:
            raise HTTPException(status_code=404, detail=f"{body.key} not found in .env")
        from hermes_cli.config import env_key_touches_llm_runtime

        response: dict[str, Any] = {"ok": True, "key": body.key}
        if env_key_touches_llm_runtime(body.key):
            response.update(apply_llm_runtime_reload())
        return response
    except HTTPException:
        raise
    except ValueError as exc:
        # remove_env_value raises ValueError for invalid key names. Surface
        # the message to the SPA so the user understands why the delete was
        # refused instead of seeing an opaque 500. Mirrors PUT /api/env.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception:
        _log.exception("DELETE /api/env failed")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/api/env/reveal")
async def reveal_env_var(
    body: EnvVarReveal, request: Request, profile: Optional[str] = None
):
    """Return the real (unredacted) value of a single env var.

    Protected by:
    - Ephemeral session token (generated per server start, injected into SPA)
    - Rate limiting (max 5 reveals per 30s window)
    - Audit logging
    """
    # --- Token check ---
    require_token(request)

    # --- Rate limit ---
    now = time.time()
    cutoff = now - _REVEAL_WINDOW_SECONDS
    _reveal_timestamps[:] = [t for t in _reveal_timestamps if t > cutoff]
    if len(_reveal_timestamps) >= _REVEAL_MAX_PER_WINDOW:
        raise HTTPException(status_code=429, detail="Too many reveal requests. Try again shortly.")
    _reveal_timestamps.append(now)

    # --- Reveal ---
    with profile_scope(body.profile or profile):
        env_on_disk = load_env()
    value = env_on_disk.get(body.key)
    if value is None:
        raise HTTPException(status_code=404, detail=f"{body.key} not found in .env")

    _log.info("env/reveal: %s", body.key)
    return {"key": body.key, "value": value}


class RawConfigUpdate(BaseModel):
    yaml_text: str
    profile: Optional[str] = None


@router.get("/api/config/raw")
async def get_config_raw(profile: Optional[str] = None):
    """Raw config.yaml text plus its resolved path.

    ``path`` is resolved inside ``profile_scope`` so the Config page header
    shows the file the switched profile actually reads/writes — /api/status's
    ``config_path`` is machine-global and always reports the dashboard
    process's own profile, which is wrong under the global profile switcher.
    """
    with profile_scope(profile):
        path = get_config_path()
    if not path.exists():
        return {"yaml": "", "path": str(path)}
    return {"yaml": path.read_text(encoding="utf-8"), "path": str(path)}


@router.put("/api/config/raw")
async def update_config_raw(body: RawConfigUpdate, profile: Optional[str] = None):
    try:
        parsed = yaml.safe_load(body.yaml_text)
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="YAML must be a mapping")
        with profile_scope(body.profile or profile):
            save_config(parsed)
        return {"ok": True}
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {e}")


# ---------------------------------------------------------------------------
# Token / cost analytics endpoint
# ---------------------------------------------------------------------------

