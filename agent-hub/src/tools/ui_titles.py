"""工具 UI 展示名（Dashboard / FloatingChat 等）。

优先读 registry schema.``title``（各工具注册时写入）；再回退本模块内置名。
插件工具应在注册时把 ``title`` 写进 schema，无需在此登记。
"""

from __future__ import annotations

# Hermes 内置 / 通用工具展示名（与 tools/* 注册名对齐）
HERMES_TOOL_UI_TITLES: dict[str, str] = {
    "execute_code": "运行代码",
    "terminal": "终端命令",
    "search_files": "搜索文件",
    "image_generate": "生成图片",
    "vision_analyze": "图片理解",
}


def normalize_tool_name(name: str) -> str:
    raw = str(name or "").strip().lower()
    if not raw:
        return ""
    tail = raw.split("__")[-1] or raw
    if tail.startswith("mcp__"):
        tail = tail[5:]
    return tail


def resolve_tool_ui_title(name: str) -> str:
    """解析工具对用户可见的中文名。"""
    key = normalize_tool_name(name)
    if not key:
        return "工具"
    try:
        from tools.registry import registry

        schema = registry.get_schema(key) or {}
        title = str(schema.get("title") or "").strip()
        if title:
            return title
    except Exception:
        pass
    if key in HERMES_TOOL_UI_TITLES:
        return HERMES_TOOL_UI_TITLES[key]
    return key.replace("_", " ")
