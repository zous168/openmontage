"""Memory provider + Profile memory read/test routes."""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from hermes_cli.config import get_hermes_home, load_config, save_config
from hermes_cli.web_routes.deps import profile_scope

_log = logging.getLogger(__name__)

router = APIRouter(tags=["memory"])


class MemoryProviderSelect(BaseModel):
    provider: str


class MemoryReset(BaseModel):
    target: str = "all"


class MemoryRetrieveTestRequest(BaseModel):
    query: str
    entity: Optional[str] = None
    entities: Optional[list[str]] = None
    limit: Optional[int] = None
    session_id: Optional[str] = None


@router.get("/api/memory")
async def get_memory_status():
    from plugins.memory import discover_memory_providers

    cfg = load_config()
    active = ""
    mem = cfg.get("memory")
    if isinstance(mem, dict):
        active = str(mem.get("provider") or "")

    providers = []
    try:
        for name, description, configured in discover_memory_providers():
            providers.append({
                "name": name,
                "description": description,
                "configured": bool(configured),
            })
    except Exception:
        _log.exception("discover_memory_providers failed")

    mem_dir = get_hermes_home() / "memories"
    files = {}
    for fname, key in (("MEMORY.md", "memory"), ("USER.md", "user")):
        path = mem_dir / fname
        files[key] = path.stat().st_size if path.exists() else 0

    return {
        "active": active,
        "providers": providers,
        "builtin_files": files,
    }


@router.get("/api/memory/profile")
async def get_memory_profile_overview(profile: Optional[str] = None):
    from hermes_cli.memory_profile import get_profile_memory_overview

    label = (profile or "").strip() or "default"
    with profile_scope(profile):
        return get_profile_memory_overview(profile_label=label)


@router.get("/api/memory/profile/facts")
async def get_memory_profile_facts(
    profile: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
):
    from hermes_cli.memory_profile import list_profile_holographic_facts

    label = (profile or "").strip() or "default"
    with profile_scope(profile):
        payload = list_profile_holographic_facts(
            category=category,
            limit=limit,
            offset=offset,
        )
    return {"profile_id": label, **payload}


@router.get("/api/memory/profile/entities")
async def get_memory_profile_entities(
    profile: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
):
    from hermes_cli.memory_profile import list_profile_holographic_entities

    label = (profile or "").strip() or "default"
    with profile_scope(profile):
        payload = list_profile_holographic_entities(limit=limit, offset=offset)
    return {"profile_id": label, **payload}


@router.post("/api/memory/profile/entities/purge-noise")
async def post_memory_profile_purge_noise_entities(profile: Optional[str] = None):
    from hermes_cli.memory_profile import purge_profile_noise_entities

    label = (profile or "").strip() or "default"
    with profile_scope(profile):
        result = purge_profile_noise_entities()
    return {"profile_id": label, **result}


@router.post("/api/memory/profile/markdown/purge-transient")
async def post_memory_profile_purge_transient_markdown(
    profile: Optional[str] = None,
    target: str = "memory",
):
    from hermes_cli.memory_profile import purge_profile_transient_memory

    label = (profile or "").strip() or "default"
    tgt = (target or "memory").strip().lower()
    if tgt not in {"memory", "user"}:
        raise HTTPException(status_code=400, detail="target must be memory or user")
    with profile_scope(profile):
        result = purge_profile_transient_memory(target=tgt)
    return {"profile_id": label, **result}


@router.get("/api/memory/profile/sessions")
async def get_memory_profile_sessions(
    profile: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    order: str = "recent",
):
    from hermes_cli.memory_profile import list_profile_agent_sessions

    label = (profile or "").strip() or "default"
    with profile_scope(profile):
        payload = list_profile_agent_sessions(limit=limit, offset=offset, order=order)
    return {"profile_id": label, **payload}


@router.get("/api/memory/profile/sessions/{session_id}/messages")
async def get_memory_profile_session_messages(
    session_id: str,
    profile: Optional[str] = None,
):
    from hermes_cli.memory_profile import get_profile_agent_session_messages

    label = (profile or "").strip() or "default"
    try:
        with profile_scope(profile):
            payload = get_profile_agent_session_messages(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"profile_id": label, **payload}


@router.get("/api/memory/profile/sessions/{session_id}/compression-chain")
async def get_memory_profile_session_compression_chain(
    session_id: str,
    profile: Optional[str] = None,
):
    from hermes_cli.memory_profile import get_profile_session_compression_chain

    label = (profile or "").strip() or "default"
    try:
        with profile_scope(profile):
            payload = get_profile_session_compression_chain(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"profile_id": label, **payload}


@router.post("/api/memory/profile/retrieve-test")
async def post_memory_profile_retrieve_test(
    body: MemoryRetrieveTestRequest,
    profile: Optional[str] = None,
):
    from hermes_cli.memory_profile import simulate_profile_memory_retrieval

    label = (profile or "").strip() or "default"
    query = (body.query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    try:
        with profile_scope(profile):
            return simulate_profile_memory_retrieval(
                query=query,
                profile_label=label,
                entity=body.entity,
                entities=body.entities,
                limit=body.limit,
                session_id=body.session_id,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/memory/provider")
async def set_memory_provider(body: MemoryProviderSelect):
    provider = (body.provider or "").strip()
    if provider.lower() in {"built-in", "builtin", "none"}:
        provider = ""

    if provider:
        from plugins.memory import discover_memory_providers

        valid = {name for name, _d, _c in discover_memory_providers()}
        if provider not in valid:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unknown memory provider '{provider}'. "
                    "Run `hermes memory setup` to configure a new one."
                ),
            )

    cfg = load_config()
    if not isinstance(cfg.get("memory"), dict):
        cfg["memory"] = {}
    cfg["memory"]["provider"] = provider
    save_config(cfg)
    return {"ok": True, "active": provider}


@router.post("/api/memory/reset")
async def reset_memory(body: MemoryReset):
    target = (body.target or "all").strip().lower()
    if target not in {"all", "memory", "user"}:
        raise HTTPException(status_code=400, detail="target must be all, memory, or user")

    mem_dir = get_hermes_home() / "memories"
    deleted = []
    targets = []
    if target in {"all", "memory"}:
        targets.append("MEMORY.md")
    if target in {"all", "user"}:
        targets.append("USER.md")
    for fname in targets:
        path = mem_dir / fname
        if path.exists():
            try:
                path.unlink()
                deleted.append(fname)
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"Could not delete {fname}: {exc}") from exc
    return {"ok": True, "deleted": deleted}
