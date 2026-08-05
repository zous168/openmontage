"""Hub platform memory routing (USER.md vs MEMORY.md)."""

from __future__ import annotations

from pathlib import Path

import pytest

from hermes_cli.memory_routing import (
    is_hub_scoped_hermes_home,
    is_transient_memory_content,
    is_user_only_memory_content,
    hub_memory_write_guard,
    memory_tool_request_middleware,
    resolve_memory_target,
)


@pytest.mark.parametrize(
    "content,expected",
    [
        ("User speaks Chinese (simplified) and prefers Chinese responses", True),
        ("语言偏好：中文", True),
        ("用户负责抖音业务（抖音渠道运营）。", False),
        ("工作规则：回复用中文，且 50 字以内。", False),
        ("用户近期在做 AI 相关项目，方向：Agent 应用开发。", False),
    ],
)
def test_is_user_only_memory_content(content: str, expected: bool) -> None:
    assert is_user_only_memory_content(content) is expected


@pytest.mark.parametrize(
    "content,expected_target",
    [
        ("User speaks Chinese (simplified) and prefers Chinese responses", "user"),
        ("用户负责抖音业务", "memory"),
        ("工作规则：回复用中文，且 50 字以内。", "memory"),
    ],
)
def test_resolve_memory_target_add(content: str, expected_target: str) -> None:
    assert resolve_memory_target(action="add", target="user", content=content) == expected_target


def test_resolve_memory_target_replace_unchanged() -> None:
    assert (
        resolve_memory_target(action="replace", target="user", content="x") == "user"
    )


def test_is_hub_scoped_hermes_home(tmp_path: Path) -> None:
    root = tmp_path / "hub"
    root.mkdir()
    assistant = root / "profiles" / "assistant"
    assistant.mkdir(parents=True)
    other = tmp_path / "else"
    other.mkdir()
    assert is_hub_scoped_hermes_home(root, data_root=root) is True
    assert is_hub_scoped_hermes_home(assistant, data_root=root) is True
    assert is_hub_scoped_hermes_home(other, data_root=root) is False


def test_middleware_rewrites_add_on_hub_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "hub"
    assistant = data_dir / "profiles" / "assistant"
    assistant.mkdir(parents=True)
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("HUB_MEMORY_ROUTING", "1")

    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(str(assistant))
    try:
        result = memory_tool_request_middleware(
            "memory",
            {
                "action": "add",
                "target": "user",
                "content": "用户负责抖音业务（抖音渠道运营）。",
            },
        )
    finally:
        reset_hermes_home_override(token)

    assert result is not None
    assert result["args"]["target"] == "memory"
    assert result["middleware"] == "hub.memory_routing"


def test_middleware_skips_outside_hub_data_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "hub"
    data_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))

    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(str(outside))
    try:
        result = memory_tool_request_middleware(
            "memory",
            {"action": "add", "target": "user", "content": "用户负责抖音业务"},
        )
    finally:
        reset_hermes_home_override(token)

    assert result is None


def test_wire_memory_routing_idempotent() -> None:
    from hermes_cli.memory_routing import memory_tool_request_middleware, wire_memory_routing
    from hermes_cli.middleware import TOOL_REQUEST_MIDDLEWARE
    from hermes_cli.plugins import get_plugin_manager

    wire_memory_routing()
    first_count = len(get_plugin_manager()._middleware.get(TOOL_REQUEST_MIDDLEWARE, []))
    wire_memory_routing()
    second_count = len(get_plugin_manager()._middleware.get(TOOL_REQUEST_MIDDLEWARE, []))
    assert second_count == first_count
    assert memory_tool_request_middleware in get_plugin_manager()._middleware.get(
        TOOL_REQUEST_MIDDLEWARE, []
    )


WSL_NOTE = (
    "The terminal tool runs inside WSL with HOME=/root. "
    "Use /mnt/h/work/project/mx-ai not H:\\ paths. "
    "read_file tool cannot resolve /mnt/h/ — use cat via terminal instead."
)


def test_is_transient_memory_content_wsl_block() -> None:
    assert is_transient_memory_content(WSL_NOTE) is True
    assert is_transient_memory_content("用户负责抖音业务（抖音渠道运营）。") is False
    assert is_transient_memory_content("工作规则：回复用中文，且 50 字以内。") is False


def test_hub_memory_write_guard_blocks_transient(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    data_dir = tmp_path / "hub"
    assistant = data_dir / "profiles" / "assistant"
    assistant.mkdir(parents=True)
    monkeypatch.setenv("HUB_DATA_DIR", str(data_dir))
    monkeypatch.setenv("HUB_MEMORY_ROUTING", "1")

    from hermes_constants import reset_hermes_home_override, set_hermes_home_override

    token = set_hermes_home_override(str(assistant))
    try:
        msg = hub_memory_write_guard(action="add", target="memory", content=WSL_NOTE)
        assert msg is not None
        ok = hub_memory_write_guard(
            action="add",
            target="memory",
            content="用户负责抖音业务（抖音渠道运营）。",
        )
        assert ok is None
    finally:
        reset_hermes_home_override(token)


def test_compose_memory_tool_description_preserves_appendix() -> None:
    from hermes_cli.memory_routing import (
        MEMORY_TOOL_APPENDIX,
        _compose_memory_tool_description,
    )

    base = "Base memory tool description."
    prior_desc = "Plugin override description."

    def prior() -> dict[str, str]:
        return {"description": prior_desc}

    merged = _compose_memory_tool_description(base, prior)
    assert prior_desc in merged
    assert MEMORY_TOOL_APPENDIX.strip() in merged
