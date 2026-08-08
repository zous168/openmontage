"""Prefer Git Bash over WSL bash.exe on Windows."""

from __future__ import annotations

import os

from tools.environments import local as local_env


def test_is_wsl_bash_detects_system32(monkeypatch, tmp_path):
    windir = tmp_path / "Windows"
    sys32 = windir / "System32"
    sys32.mkdir(parents=True)
    bash = sys32 / "bash.exe"
    bash.write_text("", encoding="utf-8")
    monkeypatch.setenv("WINDIR", str(windir))
    assert local_env._is_wsl_bash(str(bash)) is True


def test_is_wsl_bash_rejects_git_bash(monkeypatch, tmp_path):
    git_bash = tmp_path / "Git" / "bin" / "bash.exe"
    git_bash.parent.mkdir(parents=True)
    git_bash.write_text("", encoding="utf-8")
    monkeypatch.setenv("WINDIR", str(tmp_path / "Windows"))
    assert local_env._is_wsl_bash(str(git_bash)) is False


def test_find_bash_prefers_git_over_wsl_which(monkeypatch, tmp_path):
    if os.name != "nt":
        # Exercise Windows branch explicitly.
        monkeypatch.setattr(local_env, "_IS_WINDOWS", True)

    windir = tmp_path / "Windows"
    sys32 = windir / "System32"
    sys32.mkdir(parents=True)
    wsl = sys32 / "bash.exe"
    wsl.write_text("", encoding="utf-8")

    git_bash = tmp_path / "Git" / "bin" / "bash.exe"
    git_bash.parent.mkdir(parents=True)
    git_bash.write_text("", encoding="utf-8")

    monkeypatch.setenv("WINDIR", str(windir))
    monkeypatch.delenv("HERMES_GIT_BASH_PATH", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setenv("ProgramFiles", str(tmp_path))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "x86"))
    monkeypatch.setattr(local_env.shutil, "which", lambda _name: str(wsl))

    assert local_env._find_bash() == str(git_bash)
