"""Plugin manifest toolsets when register() skipped (unsupported platform)."""

from __future__ import annotations

from unittest.mock import MagicMock

from hermes_cli.plugins import get_manifest_toolset_tools, get_plugin_toolsets


def test_manifest_toolset_tools_for_unregistered_plugin_tool() -> None:
    manager = MagicMock()
    loaded = MagicMock()
    loaded.enabled = True
    loaded.manifest.provides_tools = ["meet_join", "meet_leave"]
    manager._plugins = {"google_meet": loaded}

    import hermes_cli.plugins as plugins_mod

    original = plugins_mod.get_plugin_manager
    plugins_mod.get_plugin_manager = lambda: manager
    try:
        assert get_manifest_toolset_tools("meet_join") == ["meet_join"]
        keys = {row[0] for row in get_plugin_toolsets()}
        assert "meet_join" in keys
        assert "meet_leave" in keys
    finally:
        plugins_mod.get_plugin_manager = original
