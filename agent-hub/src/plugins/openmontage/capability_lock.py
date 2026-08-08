"""编排 agent 能力收口：从工具列表拿掉读文件/探测通道。

软提示拦不住「有工具就会用」。本模块在 OM 生产会话里：

1. ``llm_request`` middleware —— 发往模型前从 ``tools`` 数组删除禁用工具
2. ``pre_tool_call`` 兜底 —— 即使幻觉调用也拒绝执行

锁定后**统一**拿掉读文件类 + ``terminal`` / ``execute_code``（不再依赖
跨进程 busy 判定——CLI 与 hub 内存态不一致时会漏拦）。

无头 stage（``OPENMONTAGE_HEADLESS_STAGE=1``）不走本模块收口：其 Hermes
工具面已在 ``backlot.agent_executor`` 收成 openmontage_stage + skills_view
（om_registry / om_checkpoint / om_artifact_*；不含 file/terminal/execute_code）；
若仍幻觉调用通用工具，由 governance 硬拦。
"""

from __future__ import annotations

import logging
import os
from copy import deepcopy
from typing import Any, Optional

logger = logging.getLogger(__name__)

# OM 生产会话：统一禁止「翻盘重建契约 / 假等待 / 手搓进度」
_LOCKDOWN_TOOLS = frozenset({
    "read_file",
    "search_files",
    "find_files",
    "list_files",
    "terminal",
    "execute_code",
})

_OM_TOOLS = frozenset({
    "om_preflight",
    "om_catalog",
    "om_pipeline",
    "om_project",
    "om_director",
    "om_run",
    "om_job",
    "om_state",
})

# session_id → 已进入 OM 生产模式
_locked_sessions: set[str] = set()


def reset_lockdown_state_for_tests() -> None:
    """测试用：清空会话锁定表。"""
    _locked_sessions.clear()


def is_headless_stage() -> bool:
    return bool(os.environ.get("OPENMONTAGE_HEADLESS_STAGE"))


def mark_session_lockdown(session_id: str | None, *, reason: str = "") -> None:
    """将会话标为 OM 生产锁定（幂等）。"""
    sid = str(session_id or "").strip()
    if not sid or is_headless_stage():
        return
    if sid not in _locked_sessions:
        logger.info("capability_lock.on session=%s reason=%s", sid, reason or "om")
    _locked_sessions.add(sid)


def is_session_locked(session_id: str | None) -> bool:
    if is_headless_stage():
        return False
    sid = str(session_id or "").strip()
    return bool(sid and sid in _locked_sessions)


def tools_to_strip(session_id: str | None) -> frozenset[str]:
    """本轮应从工具列表移除的工具名（锁定即全套，统一处理）。"""
    if is_headless_stage() or not is_session_locked(session_id):
        return frozenset()
    return _LOCKDOWN_TOOLS


def _entry_tool_name(entry: Any) -> Optional[str]:
    if not isinstance(entry, dict):
        return None
    fn = entry.get("function")
    if isinstance(fn, dict) and fn.get("name"):
        return str(fn["name"])
    if entry.get("name"):
        return str(entry["name"])
    # Anthropic / 部分适配器
    if entry.get("type") == "function" and isinstance(entry.get("function"), dict):
        return str(entry["function"].get("name") or "") or None
    return None


def strip_tools_list(tools: list, banned: frozenset[str]) -> list:
    """过滤 tools 数组，保留非禁用项。"""
    if not banned or not tools:
        return tools
    kept: list = []
    dropped: list[str] = []
    for entry in tools:
        name = _entry_tool_name(entry)
        if name and name in banned:
            dropped.append(name)
            continue
        kept.append(entry)
    if dropped:
        logger.info(
            "capability_lock.strip dropped=%s remaining=%d",
            sorted(set(dropped)),
            len(kept),
        )
    return kept


def llm_request_middleware(
    *,
    request: dict | None = None,
    session_id: str = "",
    **_kw: Any,
) -> dict | None:
    """``llm_request`` middleware：从发往模型的 tools 里拿掉禁用工具。"""
    if not isinstance(request, dict):
        return None
    banned = tools_to_strip(session_id)
    if not banned:
        return None

    new_request = deepcopy(request)
    changed = False

    tools = new_request.get("tools")
    if isinstance(tools, list) and tools:
        filtered = strip_tools_list(tools, banned)
        if len(filtered) != len(tools):
            new_request["tools"] = filtered
            changed = True

    # 部分 provider 把工具挂在 nested body
    body = new_request.get("body")
    if isinstance(body, dict):
        body_tools = body.get("tools")
        if isinstance(body_tools, list) and body_tools:
            filtered = strip_tools_list(body_tools, banned)
            if len(filtered) != len(body_tools):
                body = dict(body)
                body["tools"] = filtered
                new_request["body"] = body
                changed = True

    if not changed:
        return None
    return {"request": new_request}


def pre_tool_capability_block(
    tool_name: str,
    *,
    session_id: str = "",
) -> dict | None:
    """执行侧兜底：锁定会话调用已剥离工具 → block。"""
    if is_headless_stage():
        return None
    banned = tools_to_strip(session_id)
    if tool_name not in banned:
        return None
    return {
        "action": "block",
        "message": (
            "OpenMontage 能力收口：生产会话已从工具列表移除 "
            f"{tool_name}（与 read_file/search_files/terminal/execute_code 同等处理）。"
            "进度 → om_project；轮询 → om_job；契约 → skill_view / om_director；"
            "不要翻目录、读 checkpoint、或假等待。"
        ),
    }


def note_om_tool_use(tool_name: str, *, session_id: str = "") -> None:
    """om_* 一用就锁定该会话（即使本轮没注入 brief）。"""
    if tool_name in _OM_TOOLS or tool_name.startswith("om_"):
        mark_session_lockdown(session_id, reason=f"tool:{tool_name}")
