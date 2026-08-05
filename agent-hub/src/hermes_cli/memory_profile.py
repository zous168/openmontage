"""Profile 级记忆只读聚合（Hermes Dashboard · 随 ?profile= 切换）."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

import yaml

from hermes_constants import get_hermes_home

_ENTRY_DELIMITER = "\n§\n"

_CATEGORY_LABELS = {
    "user_pref": "用户偏好",
    "project": "项目/业务",
    "tool": "工具/环境",
    "general": "通用",
}

_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)


def _memory_defaults() -> dict[str, Any]:
    from hermes_cli.config import DEFAULT_CONFIG

    mem = DEFAULT_CONFIG.get("memory")
    return mem if isinstance(mem, dict) else {}


def merged_memory_settings(mem_cfg: dict[str, Any] | None) -> dict[str, Any]:
    """Effective memory.* settings for the active profile (mirrors agent init)."""
    defaults = _memory_defaults()
    mem = mem_cfg if isinstance(mem_cfg, dict) else {}
    provider = str(mem.get("provider") or defaults.get("provider") or "").strip()
    return {
        "memory_enabled": bool(mem.get("memory_enabled", defaults.get("memory_enabled", True))),
        "user_profile_enabled": bool(
            mem.get("user_profile_enabled", defaults.get("user_profile_enabled", True))
        ),
        "memory_char_limit": int(mem.get("memory_char_limit", defaults.get("memory_char_limit", 2200))),
        "user_char_limit": int(mem.get("user_char_limit", defaults.get("user_char_limit", 1375))),
        "prefetch_limit": int(mem.get("prefetch_limit", defaults.get("prefetch_limit", 5))),
        "provider": provider or "builtin",
    }


def _tokenize(text: str) -> set[str]:
    return {t.lower() for t in _TOKEN_RE.findall(text or "") if len(t) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0


def _serialize_fact(fact: dict[str, Any]) -> dict[str, Any]:
    row = {k: v for k, v in fact.items() if k != "hrr_vector"}
    if "score" in row and row["score"] is not None:
        row["score"] = round(float(row["score"]), 4)
    if "trust_score" in row and row["trust_score"] is not None:
        row["trust_score"] = round(float(row["trust_score"]), 4)
    return row


def _entry_relevance_score(query: str, text: str) -> float:
    query = query or ""
    text = text or ""
    if not query or not text:
        return 0.0
    if query in text or text in query:
        return 1.0

    query_tokens = _tokenize(query)
    text_tokens = _tokenize(text)
    score = _jaccard(query_tokens, text_tokens)
    if score > 0:
        return score

    for token in sorted(query_tokens, key=len, reverse=True):
        if len(token) >= 2 and token in text:
            return 0.75
    for token in sorted(text_tokens, key=len, reverse=True):
        if len(token) >= 2 and token in query:
            return 0.75
    return 0.0


def _markdown_relevance_hints(
    memory_entries: list[dict[str, Any]],
    user_entries: list[dict[str, Any]],
    query: str,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Keyword overlap against static Markdown entries (diagnostic only)."""
    if not (query or "").strip():
        return []

    hints: list[dict[str, Any]] = []
    for target, entries in (("memory", memory_entries), ("user", user_entries)):
        for entry in entries:
            text = str(entry.get("text") or "")
            score = _entry_relevance_score(query, text)
            if score <= 0:
                continue
            hints.append(
                {
                    "target": target,
                    "index": entry.get("index"),
                    "text": entry.get("text"),
                    "score": round(score, 4),
                }
            )
    hints.sort(key=lambda h: h["score"], reverse=True)
    return hints[:limit]


def _build_prefetch_block(facts: list[dict[str, Any]]) -> str:
    if not facts:
        return ""
    lines = []
    for fact in facts:
        trust = fact.get("trust_score", fact.get("trust", 0)) or 0
        content = fact.get("content", "")
        lines.append(f"- [{float(trust):.1f}] {content}")
    return "## Holographic Memory\n" + "\n".join(lines)


def _load_holographic_retriever(home: Path):
    """Return (retriever, min_trust) when holographic is active for this profile."""
    cfg = _read_yaml_at(home)
    mem_cfg = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}
    provider = str(mem_cfg.get("provider") or "").strip()
    if provider != "holographic":
        return None, 0.3

    from hermes_cli.config import cfg_get
    from plugins.memory.holographic.retrieval import FactRetriever
    from plugins.memory.holographic.store import MemoryStore as HolographicStore

    plugin_cfg = cfg_get(cfg, "plugins", "hermes-memory-store", default={}) or {}
    home_str = str(home)
    db_path = plugin_cfg.get("db_path", f"{home_str}/memory_store.db")
    if isinstance(db_path, str):
        db_path = db_path.replace("$HERMES_HOME", home_str).replace("${HERMES_HOME}", home_str)
    if not Path(db_path).is_file():
        return None, float(plugin_cfg.get("min_trust_threshold", 0.3))

    store = HolographicStore(
        db_path=db_path,
        default_trust=float(plugin_cfg.get("default_trust", 0.5)),
        hrr_dim=int(plugin_cfg.get("hrr_dim", 1024)),
    )
    retriever = FactRetriever(
        store=store,
        temporal_decay_half_life=int(plugin_cfg.get("temporal_decay_half_life", 0)),
        hrr_weight=float(plugin_cfg.get("hrr_weight", 0.3)),
        hrr_dim=int(plugin_cfg.get("hrr_dim", 1024)),
    )
    min_trust = float(plugin_cfg.get("min_trust_threshold", 0.3))
    return retriever, min_trust


def _load_holographic_system_prompt_block(home: Path, mem_cfg: dict[str, Any]) -> str | None:
    """Mirror HolographicMemoryProvider.system_prompt_block() in the cached system prompt."""
    if str(mem_cfg.get("provider") or "").strip() != "holographic":
        return None
    try:
        from plugins.memory.holographic import HolographicMemoryProvider

        provider = HolographicMemoryProvider()
        provider.initialize(session_id="retrieve-test")
        block = provider.system_prompt_block()
        return block.strip() or None
    except Exception:
        return None


def _load_session_conversation_history(
    session_id: str | None,
    *,
    home: Path,
) -> list[dict[str, Any]]:
    sid = (session_id or "").strip()
    if not sid:
        return []
    try:
        payload = get_profile_agent_session_messages(sid, home=home)
    except ValueError:
        return []
    return list(payload.get("messages") or [])


def _build_api_user_message_content(query: str, prefetch_block: str) -> tuple[str, str | None]:
    """Return (api_content, wrapped_prefetch) matching conversation_loop injection."""
    from agent.memory_manager import build_memory_context_block

    wrapped = build_memory_context_block(prefetch_block) if prefetch_block else ""
    if wrapped:
        return f"{query}\n\n{wrapped}", wrapped
    return query, wrapped or None


def _load_builtin_prompt_blocks(home: Path, mem_cfg: dict[str, Any]) -> dict[str, Any]:
    """Mirror session-start MEMORY/USER injection (frozen snapshot at load time)."""
    from tools.memory_tool import MemoryStore

    settings = merged_memory_settings(mem_cfg)
    store = MemoryStore(
        memory_char_limit=settings["memory_char_limit"],
        user_char_limit=settings["user_char_limit"],
    )
    store.load_from_disk()
    return {
        "memory_enabled": settings["memory_enabled"],
        "user_profile_enabled": settings["user_profile_enabled"],
        "memory_block": store.format_for_system_prompt("memory") if settings["memory_enabled"] else None,
        "user_block": store.format_for_system_prompt("user") if settings["user_profile_enabled"] else None,
    }


def simulate_profile_memory_retrieval(
    *,
    query: str,
    home: Path | None = None,
    profile_label: str = "default",
    entity: str | None = None,
    entities: list[str] | None = None,
    limit: int | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Simulate memory injected before an LLM request (session-start + turn prefetch only).

    Matches ``conversation_loop`` / ``HolographicMemoryProvider.prefetch`` — not
    fact_store tool calls (search/probe/reason happen only when the agent invokes tools).
    ``entity`` / ``entities`` are ignored (legacy API fields).
    """
    root = home or get_hermes_home()
    query = (query or "").strip()
    if not query:
        raise ValueError("query is required")

    cfg = _read_yaml_at(root)
    mem_cfg = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}
    settings = merged_memory_settings(mem_cfg)
    provider = settings["provider"]

    configured_prefetch = max(1, min(int(settings["prefetch_limit"]), 50))
    if limit is not None:
        configured_prefetch = min(configured_prefetch, max(1, min(int(limit), 50)))
    prefetch_limit = configured_prefetch

    session_start = _load_builtin_prompt_blocks(root, mem_cfg)
    holographic_system_block = _load_holographic_system_prompt_block(root, mem_cfg)
    history_messages = _load_session_conversation_history(session_id, home=root)

    retriever, min_trust = _load_holographic_retriever(root)
    prefetch_facts: list[dict[str, Any]] = []
    prefetch_block = ""

    if retriever is not None:
        try:
            raw_prefetch = retriever.search(query, min_trust=min_trust, limit=prefetch_limit)
            prefetch_facts = [_serialize_fact(f) for f in raw_prefetch]
            prefetch_block = _build_prefetch_block(raw_prefetch)
        except Exception:
            prefetch_facts = []
            prefetch_block = ""

    api_user_content, prefetch_injected = _build_api_user_message_content(query, prefetch_block)

    return {
        "profile_id": profile_label,
        "query": query,
        "provider": provider,
        "settings": settings,
        "session_id": (session_id or "").strip() or None,
        "scenario": {
            "session_start": {
                "label": "session_start",
                "description": (
                    "会话建立时写入 system prompt：MEMORY.md / USER.md 整段，"
                    "以及全息引擎的说明块（不含具体 fact）"
                ),
                "holographic_system_block": holographic_system_block,
                **session_start,
            },
            "conversation_history": {
                "label": "conversation_history",
                "description": (
                    "来自 state.db 的 messages[]，随每条 LLM 请求一并发送；"
                    "不是记忆检索，仅为对话上下文"
                ),
                "messages": history_messages,
                "message_count": len(history_messages),
                "simulated_turn": {
                    "user_content": query,
                    "api_user_content": api_user_content,
                    "prefetch_injection": prefetch_injected,
                },
            },
            "turn_prefetch": {
                "label": "turn_prefetch",
                "description": (
                    "本轮用户消息发出前自动 prefetch（Profile 级 memory_store.db），"
                    "经 memory-context 包装后追加到 api_user_content 末尾"
                ),
                "limit": prefetch_limit,
                "block": prefetch_block or None,
                "injected_block": prefetch_injected,
                "facts": prefetch_facts[:prefetch_limit],
            },
        },
        "category_labels": dict(_CATEGORY_LABELS),
    }


def _read_yaml_at(home: Path) -> dict[str, Any]:
    path = home / "config.yaml"
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig")) or {}
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_markdown_entries(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    parts = [p.strip() for p in raw.split(_ENTRY_DELIMITER) if p.strip()]
    from hermes_cli.memory_routing import is_transient_memory_content

    return [
        {
            "index": i,
            "text": text,
            "chars": len(text),
            "transient": is_transient_memory_content(text),
        }
        for i, text in enumerate(parts)
    ]


def _write_markdown_entries(path: Path, entries: list[str]) -> None:
    import os
    import tempfile

    from utils import atomic_replace

    path.parent.mkdir(parents=True, exist_ok=True)
    content = _ENTRY_DELIMITER.join(entries) if entries else ""
    fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp", prefix=".mem_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        atomic_replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def purge_profile_transient_memory(
    *,
    home: Path | None = None,
    target: str = "memory",
) -> dict[str, Any]:
    """Remove transient MEMORY.md (or USER.md) entries from disk."""
    root = home or get_hermes_home()
    mem_dir = root / "memories"
    fname = "MEMORY.md" if target == "memory" else "USER.md"
    path = mem_dir / fname
    if not path.is_file():
        return {"target": target, "removed": [], "count": 0, "remaining": 0}

    from hermes_cli.memory_routing import is_transient_memory_content

    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return {"target": target, "removed": [], "count": 0, "remaining": 0}

    parts = [p.strip() for p in raw.split(_ENTRY_DELIMITER) if p.strip()]
    kept: list[str] = []
    removed: list[str] = []
    for part in parts:
        if is_transient_memory_content(part):
            removed.append(part[:240])
        else:
            kept.append(part)

    if removed:
        _write_markdown_entries(path, kept)

    return {
        "target": target,
        "removed": removed,
        "count": len(removed),
        "remaining": len(kept),
    }


def _query_holographic_stats(db_path: Path) -> dict[str, Any]:
    if not db_path.is_file():
        return {
            "memory_store_exists": False,
            "facts": 0,
            "entities": 0,
            "entities_usable": 0,
            "entities_noise": 0,
            "categories": [],
        }
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        facts = int(conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0])
        entities_total = 0
        entities_usable = 0
        entities_noise = 0
        try:
            from plugins.memory.holographic.store import is_plausible_entity

            names = [
                str(row[0])
                for row in conn.execute("SELECT name FROM entities").fetchall()
            ]
            entities_total = len(names)
            entities_usable = sum(1 for name in names if is_plausible_entity(name))
            entities_noise = entities_total - entities_usable
        except sqlite3.Error:
            pass
        categories: list[dict[str, Any]] = []
        try:
            rows = conn.execute(
                """
                SELECT category, COUNT(*) AS cnt
                FROM facts
                GROUP BY category
                ORDER BY cnt DESC, category ASC
                """
            ).fetchall()
            categories = [{"name": str(r["category"] or "general"), "count": int(r["cnt"])} for r in rows]
        except sqlite3.Error:
            pass
        return {
            "memory_store_exists": True,
            "facts": facts,
            "entities": entities_total,
            "entities_usable": entities_usable,
            "entities_noise": entities_noise,
            "categories": categories,
        }
    finally:
        conn.close()


def list_profile_holographic_facts(
    *,
    home: Path | None = None,
    category: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    root = home or get_hermes_home()
    db_path = root / "memory_store.db"
    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    if not db_path.is_file():
        return {"facts": [], "total": 0, "limit": limit, "offset": offset}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        params: list[Any] = []
        where = ""
        if category:
            where = "WHERE category = ?"
            params.append(category)
        total = int(conn.execute(f"SELECT COUNT(*) FROM facts {where}", params).fetchone()[0])
        params.extend([limit, offset])
        rows = conn.execute(
            f"""
            SELECT fact_id, content, category, tags, trust_score,
                   retrieval_count, helpful_count, created_at, updated_at
            FROM facts
            {where}
            ORDER BY trust_score DESC, updated_at DESC, fact_id DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()
        return {
            "facts": [dict(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn.close()


def list_profile_holographic_entities(
    *,
    home: Path | None = None,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    """List entities extracted from facts (for probe/reason test inputs)."""
    root = home or get_hermes_home()
    db_path = root / "memory_store.db"
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    if not db_path.is_file():
        return {"entities": [], "total": 0, "limit": limit, "offset": offset}

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        try:
            rows = conn.execute(
                """
                SELECT e.entity_id, e.name, e.entity_type,
                       COUNT(fe.fact_id) AS fact_count,
                       (
                           SELECT f.content
                           FROM facts f
                           JOIN fact_entities fe2 ON fe2.fact_id = f.fact_id
                           WHERE fe2.entity_id = e.entity_id
                           ORDER BY f.updated_at DESC
                           LIMIT 1
                       ) AS sample_fact
                FROM entities e
                LEFT JOIN fact_entities fe ON fe.entity_id = e.entity_id
                GROUP BY e.entity_id
                ORDER BY fact_count DESC, e.name ASC
                """
            ).fetchall()
        except sqlite3.Error:
            return {"entities": [], "total": 0, "limit": limit, "offset": offset}

        from plugins.memory.holographic.store import is_plausible_entity

        all_entities = [
            {
                "id": int(r["entity_id"]),
                "name": str(r["name"]),
                "type": str(r["entity_type"] or "unknown"),
                "fact_count": int(r["fact_count"] or 0),
                "sample_fact": str(r["sample_fact"] or "")[:200] or None,
                "plausible": is_plausible_entity(str(r["name"])),
            }
            for r in rows
        ]
        total = len(all_entities)
        page = all_entities[offset : offset + limit]
        usable = sum(1 for e in all_entities if e["plausible"])
        return {
            "entities": page,
            "total": total,
            "usable": usable,
            "noise": total - usable,
            "limit": limit,
            "offset": offset,
        }
    finally:
        conn.close()


def purge_profile_noise_entities(*, home: Path | None = None) -> dict[str, Any]:
    """Delete noise entities from memory_store.db (not UI-only hiding)."""
    root = home or get_hermes_home()
    db_path = root / "memory_store.db"
    if not db_path.is_file():
        return {"removed": [], "count": 0}

    from plugins.memory.holographic.store import is_plausible_entity

    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    removed: list[str] = []
    try:
        rows = conn.execute("SELECT entity_id, name FROM entities").fetchall()
        for row in rows:
            name = str(row["name"])
            if is_plausible_entity(name):
                continue
            entity_id = int(row["entity_id"])
            conn.execute("DELETE FROM fact_entities WHERE entity_id = ?", (entity_id,))
            conn.execute("DELETE FROM entities WHERE entity_id = ?", (entity_id,))
            removed.append(name)
        conn.commit()
    finally:
        conn.close()
    return {"removed": removed, "count": len(removed)}


_AGENT_SESSION_EXCLUDE_SOURCES = ("cron", "tool")


def _open_profile_session_db(*, home: Path | None = None):
    from hermes_state import SessionDB

    root = home or get_hermes_home()
    db_path = root / "state.db"
    if not db_path.is_file():
        return None
    return SessionDB(db_path=db_path)


def list_profile_agent_sessions(
    *,
    home: Path | None = None,
    limit: int = 30,
    offset: int = 0,
    order: str = "recent",
) -> dict[str, Any]:
    """List agent chat sessions for the active profile (read-only)."""
    import re as _re
    import time as _time

    limit = max(1, min(int(limit), 100))
    offset = max(0, int(offset))
    order_by_recent = (order or "recent").strip().lower() != "created"
    empty = {"sessions": [], "total": 0, "limit": limit, "offset": offset}

    db = _open_profile_session_db(home=home)
    if db is None:
        return empty
    try:
        exclude = list(_AGENT_SESSION_EXCLUDE_SOURCES)
        sessions = db.list_sessions_rich(
            exclude_sources=exclude,
            limit=limit,
            offset=offset,
            min_message_count=1,
            order_by_last_active=order_by_recent,
        )
        total = db.session_count(
            exclude_sources=exclude,
            min_message_count=1,
            exclude_children=True,
        )
        now = _time.time()
        slim: list[dict[str, Any]] = []
        for row in sessions:
            # When a compression root is projected forward to its live tip
            # (list_sessions_rich), the surfaced row carries ``_lineage_root_id``
            # = the original root. Use it to flag the entry as a compression
            # continuation and read the generation off the projected "… #N"
            # title so the UI can badge it without an extra round-trip.
            _root = row.get("_lineage_root_id")
            _gen_m = _re.search(r"#(\d+)\s*$", str(row.get("title") or ""))
            slim.append(
                {
                    "id": str(row.get("id") or ""),
                    "source": row.get("source"),
                    "model": row.get("model"),
                    "title": row.get("title"),
                    "started_at": row.get("started_at"),
                    "ended_at": row.get("ended_at"),
                    "last_active": row.get("last_active"),
                    "message_count": int(row.get("message_count") or 0),
                    "preview": row.get("preview"),
                    "is_active": (
                        row.get("ended_at") is None
                        and (now - float(row.get("last_active") or row.get("started_at") or 0))
                        < 300
                    ),
                    "compressed": bool(_root),
                    "lineage_root_id": str(_root) if _root else None,
                    "generation": int(_gen_m.group(1)) if _gen_m else 1,
                }
            )
        return {"sessions": slim, "total": total, "limit": limit, "offset": offset}
    finally:
        db.close()


def get_profile_agent_session_messages(
    session_id: str,
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    """Return transcript messages for one profile session."""
    db = _open_profile_session_db(home=home)
    if db is None:
        raise ValueError("No state.db for this profile")
    try:
        sid = db.resolve_session_id((session_id or "").strip())
        if not sid:
            raise ValueError("Session not found")
        sid = db.resolve_resume_session_id(sid)
        raw = db.get_messages(sid)
        messages: list[dict[str, Any]] = []
        for msg in raw:
            role = str(msg.get("role") or "")
            content = msg.get("content")
            if content is None and role not in {"tool", "assistant"}:
                continue
            text = content if isinstance(content, str) else str(content or "")
            entry: dict[str, Any] = {
                "role": role,
                "content": text,
                "timestamp": msg.get("timestamp"),
            }
            if msg.get("tool_name"):
                entry["tool_name"] = msg.get("tool_name")
            if msg.get("tool_calls"):
                entry["tool_calls"] = msg.get("tool_calls")
            messages.append(entry)
        return {"session_id": sid, "messages": messages}
    finally:
        db.close()


def get_profile_session_compression_chain(
    session_id: str,
    *,
    home: Path | None = None,
) -> dict[str, Any]:
    """Return the compression family (root + continuations) for one session.

    Each node carries a compaction-summary preview so the dashboard can render
    the source conversation and every compressed snapshot as one lineage —
    resolving the otherwise-invisible time-stamp-id continuations that context
    compaction forks off. ``compressed`` is True when the family has >1 node.
    """
    db = _open_profile_session_db(home=home)
    if db is None:
        raise ValueError("No state.db for this profile")
    try:
        sid = db.resolve_session_id((session_id or "").strip())
        if not sid:
            raise ValueError("Session not found")
        nodes = db.get_compression_chain_nodes(sid)
        root_id = next((n["session_id"] for n in nodes if n.get("is_root")), sid)
        tip_id = next((n["session_id"] for n in nodes if n.get("is_tip")), sid)
        return {
            "session_id": sid,
            "root_id": root_id,
            "tip_id": tip_id,
            "compressed": len(nodes) > 1,
            "nodes": nodes,
        }
    finally:
        db.close()


def get_profile_memory_overview(
    *,
    home: Path | None = None,
    profile_label: str = "default",
) -> dict[str, Any]:
    root = home or get_hermes_home()
    mem_dir = root / "memories"
    memory_entries = _parse_markdown_entries(mem_dir / "MEMORY.md")
    user_entries = _parse_markdown_entries(mem_dir / "USER.md")

    cfg = _read_yaml_at(root)
    mem_cfg = cfg.get("memory") if isinstance(cfg.get("memory"), dict) else {}
    settings = merged_memory_settings(mem_cfg)
    holo = _query_holographic_stats(root / "memory_store.db")

    return {
        "profile_id": profile_label,
        "scope": "profile",
        "provider": settings["provider"],
        "memory_enabled": settings["memory_enabled"],
        "user_profile_enabled": settings["user_profile_enabled"],
        "settings": settings,
        "stats": {
            "holographic_facts": holo["facts"],
            "holographic_entities": holo["entities"],
            "holographic_entities_usable": holo.get("entities_usable", 0),
            "holographic_entities_noise": holo.get("entities_noise", 0),
            "memory_store_exists": holo["memory_store_exists"],
            "memory_md_entries": len(memory_entries),
            "memory_md_transient": sum(1 for e in memory_entries if e.get("transient")),
            "memory_md_chars": sum(e["chars"] for e in memory_entries),
            "user_md_entries": len(user_entries),
            "user_md_chars": sum(e["chars"] for e in user_entries),
        },
        "categories": holo["categories"],
        "markdown": {
            "memory": memory_entries,
            "user": user_entries,
        },
        "category_labels": dict(_CATEGORY_LABELS),
    }
