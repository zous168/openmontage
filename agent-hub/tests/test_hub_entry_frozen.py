"""hub_entry 冻结态 -m/-u 分发（gateway 自拉起 / dashboard spawn）."""

from __future__ import annotations

import sys
from unittest import mock

import pytest


@pytest.fixture
def hub_entry():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "packaging" / "hub_entry.py"
    spec = importlib.util.spec_from_file_location("hub_entry_testmod", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_strip_python_interpreter_flags(hub_entry) -> None:
    assert hub_entry._strip_python_interpreter_flags(["-u", "-m", "gateway.run"]) == [
        "-m",
        "gateway.run",
    ]


def test_emulate_hermes_cli_main_gateway_run(hub_entry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    seen: dict[str, object] = {}

    import runpy

    def fake_run_module(module: str, run_name: str) -> None:
        seen["module"] = module
        seen["run_name"] = run_name
        seen["argv"] = list(sys.argv)

    monkeypatch.setattr(runpy, "run_module", fake_run_module)

    ok = hub_entry._emulate_python_flags(
        ["-u", "-m", "hermes_cli.main", "gateway", "run"],
    )
    assert ok is True
    assert seen["module"] == "gateway.run"
    assert seen["argv"] == ["gateway.run"]


def test_emulate_gateway_run_module(hub_entry, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    seen: dict[str, object] = {}

    import runpy

    def fake_run_module(module: str, run_name: str) -> None:
        seen["module"] = module
        seen["argv"] = list(sys.argv)

    monkeypatch.setattr(runpy, "run_module", fake_run_module)

    ok = hub_entry._emulate_python_flags(["-m", "gateway.run"])
    assert ok is True
    assert seen["module"] == "gateway.run"
    assert seen["argv"] == ["gateway.run"]
