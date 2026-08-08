"""Per-invocation ``label`` is injected into tool schemas and stripped on dispatch."""

from __future__ import annotations

from unittest.mock import MagicMock

from tools.registry import ToolRegistry, _with_invocation_label_schema


def test_with_invocation_label_schema_adds_label_property() -> None:
    schema = {
        "name": "demo",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    }
    out = _with_invocation_label_schema(schema)
    assert "label" in out["parameters"]["properties"]
    assert "code" in out["parameters"]["properties"]
    assert "label" not in out["parameters"]["required"]


def test_execute_code_schema_requires_label() -> None:
    schema = {
        "name": "execute_code",
        "parameters": {
            "type": "object",
            "properties": {"code": {"type": "string"}},
            "required": ["code"],
        },
    }
    out = _with_invocation_label_schema(schema)
    assert "label" in out["parameters"]["properties"]
    assert "label" in out["parameters"]["required"]
    assert "code" in out["parameters"]["required"]


def test_dispatch_strips_label_before_handler() -> None:
    reg = ToolRegistry()
    handler = MagicMock(return_value='{"ok": true}')
    reg.register(
        name="demo_tool",
        toolset="other",
        schema={
            "name": "demo_tool",
            "parameters": {
                "type": "object",
                "properties": {"code": {"type": "string"}},
                "required": ["code"],
            },
        },
        handler=handler,
    )
    reg.dispatch("demo_tool", {"label": "检查状态", "code": "print(1)"})
    handler.assert_called_once()
    assert handler.call_args.args[0] == {"code": "print(1)"}
