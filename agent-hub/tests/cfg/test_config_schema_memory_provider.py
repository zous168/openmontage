"""Config schema exposes all discovered memory provider plugins."""

from __future__ import annotations

from plugins.memory import discover_memory_providers
from hermes_cli.web_routes.config import (
    _memory_provider_schema_options,
    _schema_with_dynamic_fields,
)


def test_memory_provider_schema_lists_discovered_plugins() -> None:
    discovered = {name for name, _d, _a in discover_memory_providers()}
    assert discovered, "expected bundled memory plugins under plugins/memory/"

    options = _memory_provider_schema_options()
    assert options[0] == "builtin"
    assert discovered.issubset(set(options)), (
        f"missing from schema options: {sorted(discovered - set(options))}"
    )


def test_schema_with_dynamic_fields_patches_memory_provider() -> None:
    fields = _schema_with_dynamic_fields()
    mem = fields["memory.provider"]
    assert mem["type"] == "select"
    options = mem["options"]
    assert "builtin" in options
    assert "honcho" in options
    assert len(options) > 2
