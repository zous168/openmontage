"""工具 UI 展示名解析."""

from __future__ import annotations

from tools.ui_titles import resolve_tool_ui_title


def test_hermes_builtin_titles() -> None:
    assert resolve_tool_ui_title("execute_code") == "运行代码"
    assert resolve_tool_ui_title("terminal") == "终端命令"


def test_plugin_title_prefix_is_stripped() -> None:
    """MCP 前缀应被剥离后再回退到人类可读名。"""
    assert resolve_tool_ui_title("mcp__some_custom_tool") == "some custom tool"


def test_unknown_tool_humanized() -> None:
    assert resolve_tool_ui_title("some_custom_tool") == "some custom tool"
