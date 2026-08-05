"""Hermes plugins package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_PKG_ROOT = Path(__file__).resolve().parent


def _ensure_hub_knowledge_package() -> None:
    """将 plugins.hub_knowledge 映射到目录 plugins/hub-knowledge/（含连字符）。"""
    module_name = "plugins.hub_knowledge"
    if module_name in sys.modules:
        return
    plugin_dir = _PKG_ROOT / "hub-knowledge"
    init_file = plugin_dir / "__init__.py"
    if not init_file.exists():
        return
    spec = importlib.util.spec_from_file_location(
        module_name,
        init_file,
        submodule_search_locations=[str(plugin_dir)],
    )
    if spec is None or spec.loader is None:
        return
    module = importlib.util.module_from_spec(spec)
    module.__package__ = module_name
    module.__path__ = [str(plugin_dir)]  # type: ignore[attr-defined]
    sys.modules[module_name] = module
    spec.loader.exec_module(module)


_ensure_hub_knowledge_package()

hub_knowledge = sys.modules.get("plugins.hub_knowledge")
