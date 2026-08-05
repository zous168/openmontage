"""Gateway spawn argv / env（Hub 路径不靠 ``--replace``）."""

from __future__ import annotations

import os

import pytest


def test_hub_managed_run_command(monkeypatch: pytest.MonkeyPatch) -> None:
    from hermes_cli import gateway as gw

    monkeypatch.setenv("PARENT_PID", "4242")
    monkeypatch.setattr(gw, "get_python_path", lambda: "/usr/bin/python3")

    cmd = gw._gateway_run_command()

    assert cmd == ["/usr/bin/python3", "-m", "gateway.run"]


def test_gateway_spawn_env_uses_hub_pid(monkeypatch: pytest.MonkeyPatch) -> None:
    from hermes_cli import gateway_lifecycle as gl

    monkeypatch.setenv("PARENT_PID", "9999")
    monkeypatch.setattr(gl.os, "getpid", lambda: 5555)

    assert gl.gateway_spawn_env() == {"PARENT_PID": "5555"}


@pytest.mark.skipif(os.name != "nt", reason="Windows argv builder")
def test_build_gateway_argv_hub_managed_when_parent_pid_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """开发态 Hub 自身无 PARENT_PID 时，显式 parent 仍须走 gateway.run。"""
    from pathlib import Path

    from hermes_cli import gateway_windows as gww

    monkeypatch.delenv("PARENT_PID", raising=False)
    monkeypatch.setenv("HUB_DATA_DIR", r"D:\tmp\hub-data")
    monkeypatch.setattr(
        gww,
        "_resolve_detached_python",
        lambda _p: (r"C:\Python\python.exe", r"C:\venv", []),
    )
    monkeypatch.setattr(gww, "_stable_gateway_working_dir", lambda _root: r"D:\tmp\work")
    monkeypatch.setattr(
        "hermes_cli.config.get_hermes_home",
        lambda: Path(r"D:\tmp\hub-data\profiles\qiyeweixin"),
    )
    monkeypatch.setattr(
        "hermes_cli.gateway.PROJECT_ROOT",
        Path(r"D:\code\agent-hub\src"),
    )
    monkeypatch.setattr("hermes_cli.gateway.get_python_path", lambda: r"C:\Python\python.exe")
    monkeypatch.setattr("hermes_cli.gateway._profile_arg", lambda _home=None: "--profile qiyeweixin")
    monkeypatch.setattr(
        "hermes_cli.gateway._hub_managed_spawn",
        lambda: False,
    )

    cmd, _cwd, overlay = gww._build_gateway_argv(gateway_parent_pid=4242)
    assert cmd[-2:] == ["-m", "gateway.run"]
    assert overlay.get("PARENT_PID") == "4242"


@pytest.mark.skipif(os.name != "nt", reason="Windows argv builder")
def test_build_gateway_argv_cli_path_without_parent_pid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """非 Hub 拉起（无 parent pid、无 env PARENT_PID）仍走 hermes_cli.main。"""
    from pathlib import Path

    from hermes_cli import gateway_windows as gww

    monkeypatch.delenv("PARENT_PID", raising=False)
    monkeypatch.setenv("HUB_DATA_DIR", r"D:\tmp\hub-data")
    monkeypatch.setattr(
        gww,
        "_resolve_detached_python",
        lambda _p: (r"C:\Python\pythonw.exe", r"C:\venv", []),
    )
    monkeypatch.setattr(gww, "_stable_gateway_working_dir", lambda _root: r"D:\tmp\work")
    monkeypatch.setattr(
        "hermes_cli.config.get_hermes_home",
        lambda: Path(r"D:\tmp\hub-data\profiles\qiyeweixin"),
    )
    monkeypatch.setattr(
        "hermes_cli.gateway.PROJECT_ROOT",
        Path(r"D:\code\agent-hub\src"),
    )
    monkeypatch.setattr("hermes_cli.gateway.get_python_path", lambda: r"C:\Python\pythonw.exe")
    monkeypatch.setattr("hermes_cli.gateway._profile_arg", lambda _home=None: "--profile qiyeweixin")
    monkeypatch.setattr("hermes_cli.gateway._hub_managed_spawn", lambda: False)

    cmd, _cwd, overlay = gww._build_gateway_argv()
    assert "hermes_cli.main" in cmd
    assert "gateway" in cmd and "run" in cmd
    assert "PARENT_PID" not in overlay
