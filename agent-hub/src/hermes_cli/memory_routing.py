"""基座：内置 memory 工具分流（USER.md vs MEMORY.md）.

Hermes 默认语义倾向「凡用户相关 → user」；Hub 产品语义为：
- USER.md：语言、称呼、沟通风格
- MEMORY.md：业务、规则、项目等跨会话稳定约定（非工具调试笔记）

在 Hub 数据根下的任意 Profile 上，``memory(action=add)`` 由 platform
middleware 按规则改写 ``target``；非常驻的终端/路径踩坑类内容拒写入 MEMORY。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable

_USER_ONLY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"^user speaks .+ and prefers .+ responses?\s*$",
        r"^(语言|称呼|沟通风格|语气)(偏好)?[:：]",
        r"^叫我[\s，,:：]",
        r"^prefer(s)? (chinese|english|simplified|mandarin)\b",
        r"^speaks? (chinese|english|mandarin)\b",
        r"^(回复|沟通)?(偏好|习惯)[:：].*(中文|英文|简洁)",
        r"^用户(偏好|习惯)(用)?(中文|英文)",
    )
)

# Tool-debug / shell-workaround notes must not pollute every session's MEMORY.md.
_TRANSIENT_MEMORY_SIGNALS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bWSL\b",
        r"/mnt/[a-z]/",
        r"git-bash",
        r"terminal snapshot",
        r"read_file tool",
        r"file not found",
        r"no such file or directory",
        r"\bcd:\s",
        r"exit (code )?126",
        r"ProgramData[/\\]MarketingHub",
        r"\bH:\\",
        r"\bC:\\",
        r"use (the )?`?cat`? command",
        r"working directory.*terminal",
        r"harmless error lines",
        r"snapshot mechanism is broken",
    )
)

_TRANSIENT_MEMORY_STRONG: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"terminal tool runs inside WSL",
        r"read_file tool cannot resolve",
        r"commands still execute successfully \(exit 0\)",
    )
)

TRANSIENT_MEMORY_REJECTION = (
    "Refusing MEMORY.md write: content looks like transient tool/shell debugging "
    "(WSL paths, terminal errors, read_file workarounds). MEMORY.md is for stable "
    "business rules and project conventions injected into every session. "
    "Use fact_store(action=add) for retrievable technical notes, or a skill for "
    "repeatable procedures."
)

MEMORY_TOOL_APPENDIX = (
    "\n\n[System rules — Hub profiles]\n"
    "- ``add`` routing: USER.md = language/name/tone only; business, roles, projects "
    "→ MEMORY.md.\n"
    "- Do NOT save terminal/shell debugging, WSL path workarounds, or tool error "
    "notes to MEMORY.md (they would inject into every session). Use fact_store or "
    "skills instead.\n"
    "- MEMORY.md entries must be stable facts still useful across unrelated topics."
)

_schema_patch_applied = False


def memory_routing_enabled() -> bool:
    raw = os.environ.get("HUB_MEMORY_ROUTING", "1")
    return raw.strip().lower() not in {"0", "false", "no", "off"}


def is_hub_scoped_hermes_home(home: Path, *, data_root: Path) -> bool:
    """True when *home* is the hub default root or ``profiles/<id>/``."""
    try:
        resolved = home.resolve()
        root = data_root.resolve()
        if resolved == root:
            return True
        return resolved.parent == (root / "profiles").resolve()
    except OSError:
        return False


def current_hub_profile_scope() -> bool:
    if not memory_routing_enabled():
        return False
    from hermes_constants import get_default_hermes_root, get_hermes_home

    return is_hub_scoped_hermes_home(
        Path(get_hermes_home()),
        data_root=Path(get_default_hermes_root()),
    )


def is_transient_memory_content(content: str | None) -> bool:
    """True when content is tool/shell debugging — must not live in MEMORY.md."""
    text = (content or "").strip()
    if not text:
        return False
    if any(p.search(text) for p in _TRANSIENT_MEMORY_STRONG):
        return True
    hits = sum(1 for p in _TRANSIENT_MEMORY_SIGNALS if p.search(text))
    if hits >= 2:
        return True
    return hits >= 1 and len(text) > 180


def hub_memory_write_guard(
    *,
    action: str,
    target: str,
    content: str | None,
) -> str | None:
    """Return error message when a Hub profile memory write must be refused."""
    if not current_hub_profile_scope():
        return None
    if action not in {"add", "replace"}:
        return None
    if target != "memory":
        return None
    if is_transient_memory_content(content):
        return TRANSIENT_MEMORY_REJECTION
    return None


def is_user_only_memory_content(content: str | None) -> bool:
    """True when an add-entry belongs in USER.md (language/name/tone only)."""
    text = (content or "").strip()
    if not text:
        return False
    if any(p.search(text) for p in _USER_ONLY_PATTERNS):
        return True
    if len(text) <= 48 and re.search(r"(中文|英文|简体|繁体|简洁|语气|称呼)", text):
        if not re.search(r"(负责|业务|渠道|规则|项目|Profile|Agent|运营|开发)", text, re.I):
            return True
    return False


def resolve_memory_target(*, action: str, target: str, content: str | None) -> str:
    """Hub ``memory`` target for mutating actions."""
    if action != "add":
        return target
    return "user" if is_user_only_memory_content(content) else "memory"


def memory_tool_request_middleware(
    tool_name: str,
    args: dict[str, Any],
    **_: Any,
) -> dict[str, Any] | None:
    if tool_name != "memory":
        return None
    if not current_hub_profile_scope():
        return None

    action = str(args.get("action") or "").strip()
    if action != "add":
        return None

    requested = str(args.get("target") or "memory").strip() or "memory"
    resolved = resolve_memory_target(
        action=action,
        target=requested,
        content=args.get("content"),
    )
    if resolved == requested:
        return None

    new_args = dict(args)
    new_args["target"] = resolved
    return {
        "args": new_args,
        "middleware": "hub.memory_routing",
        "target_from": requested,
        "target_to": resolved,
    }


def _compose_memory_tool_description(
    base_desc: str,
    prior: Callable[[], dict[str, Any]] | None,
) -> str:
    """Merge base schema, optional prior override, and Hub appendix."""
    desc = base_desc or ""
    if prior is not None:
        try:
            raw = prior()
            if isinstance(raw, dict) and raw.get("description"):
                desc = str(raw["description"])
        except Exception:
            pass
    if MEMORY_TOOL_APPENDIX.strip() not in desc:
        desc = desc + MEMORY_TOOL_APPENDIX
    return desc


def _patch_memory_tool_schema() -> None:
    global _schema_patch_applied
    from tools.registry import registry

    entry = registry.get_entry("memory")
    if entry is None:
        return

    if _schema_patch_applied and entry.dynamic_schema_overrides is not None:
        return

    prior = entry.dynamic_schema_overrides
    base_desc = entry.schema.get("description") or ""

    def _overrides() -> dict[str, str]:
        return {
            "description": _compose_memory_tool_description(base_desc, prior),
        }

    entry.dynamic_schema_overrides = _overrides
    _schema_patch_applied = True


def wire_memory_routing() -> None:
    """Register hub platform memory routing (idempotent)."""
    from hermes_cli.middleware import TOOL_REQUEST_MIDDLEWARE
    from hermes_cli.plugins import register_bundled_middleware

    register_bundled_middleware(TOOL_REQUEST_MIDDLEWARE, memory_tool_request_middleware)
    _patch_memory_tool_schema()
