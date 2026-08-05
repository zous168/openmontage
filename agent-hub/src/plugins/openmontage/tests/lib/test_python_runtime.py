"""Tests for lib.python_runtime."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from plugins.openmontage.lib.python_runtime import resolve_openmontage_python, venv_python_path


def test_resolve_prefers_openmontage_python_env(tmp_path, monkeypatch):
    fake = tmp_path / "custom-python.exe"
    fake.write_text("", encoding="utf-8")
    monkeypatch.setenv("OPENMONTAGE_PYTHON", str(fake))
    assert resolve_openmontage_python() == fake.resolve()


def test_venv_python_path_layout():
    path = venv_python_path()
    assert path.name in ("python.exe", "python")
    assert path.parent.name in ("Scripts", "bin")


def test_resolve_falls_back_to_venv_when_present():
    venv_py = venv_python_path()
    if not venv_py.is_file():
        return
    with patch.dict("os.environ", {}, clear=False):
        import os

        os.environ.pop("OPENMONTAGE_PYTHON", None)
        assert resolve_openmontage_python() == venv_py.resolve()
