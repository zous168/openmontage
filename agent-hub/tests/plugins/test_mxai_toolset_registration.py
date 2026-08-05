"""MxAI toolset 须按 Hermes bundled-backend 模式注册（与 spotify 对齐）."""

from __future__ import annotations

from hermes_cli.tools_config import CONFIGURABLE_TOOLSETS, MXAI_COMPOSITE_TOOLSET
from plugins.mxai.mcp_tools import MXAI_PER_TOOL_TOOLSETS
from toolsets import TOOLSETS, resolve_toolset


def test_mxai_composite_in_configurable_toolsets() -> None:
    keys = {row[0] for row in CONFIGURABLE_TOOLSETS}
    assert MXAI_COMPOSITE_TOOLSET in keys
    for name in MXAI_PER_TOOL_TOOLSETS:
        assert name not in keys


def test_mxai_composite_and_per_tool_in_toolsets_dict() -> None:
    assert "mxai" in TOOLSETS
    composite = set(TOOLSETS["mxai"]["tools"])
    assert composite == set(MXAI_PER_TOOL_TOOLSETS)
    for name in MXAI_PER_TOOL_TOOLSETS:
        assert name in TOOLSETS
        assert TOOLSETS[name]["tools"] == [name]


def test_mxai_resolve_per_tool_toolsets() -> None:
    for name in MXAI_PER_TOOL_TOOLSETS:
        assert resolve_toolset(name) == [name]
    assert set(resolve_toolset("mxai")) == set(MXAI_PER_TOOL_TOOLSETS)
