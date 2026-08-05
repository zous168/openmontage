"""Resolve the OpenMontage project Python interpreter.

Agents and Backlot must not use an arbitrary host ``python`` (e.g. Cursor or
narrator-ai-cli venv) when calling registry tools — local video fallbacks
depend on torch/diffusers installed in this repo's ``.venv``.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

from plugins.openmontage.lib.paths import DATA_ROOT, IMPORT_ROOT, REPO_ROOT

_REEXEC_FLAG = "OPENMONTAGE_PYTHON_REEXEC"


def venv_python_path() -> Path:
    """Path to the repo virtualenv interpreter, if the venv layout exists."""
    name = "Scripts/python.exe" if os.name == "nt" else "bin/python"
    return REPO_ROOT / ".venv" / name


def resolve_openmontage_python() -> Path:
    """Best interpreter for registry tools and Backlot subprocesses."""
    override = (os.environ.get("OPENMONTAGE_PYTHON") or "").strip()
    if override:
        path = Path(override).expanduser()
        if path.is_file():
            return path.resolve()
    venv_py = venv_python_path()
    if venv_py.is_file():
        return venv_py.resolve()
    return Path(sys.executable).resolve()


def _imports_local_video_stack(exe: Path) -> bool:
    try:
        proc = subprocess.run(
            [str(exe), "-c", "import torch, diffusers"],
            capture_output=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def ensure_repo_interpreter() -> None:
    """Re-exec the current process with repo ``.venv`` when it has the GPU stack."""
    if os.environ.get(_REEXEC_FLAG) == "1":
        return
    venv_py = venv_python_path()
    if not venv_py.is_file():
        return
    if Path(sys.executable).resolve() == venv_py.resolve():
        return
    if _imports_local_video_stack(Path(sys.executable)):
        return
    if not _imports_local_video_stack(venv_py):
        return
    os.environ[_REEXEC_FLAG] = "1"
    os.execv(str(venv_py), [str(venv_py), *sys.argv])


def openmontage_python_env(base: Optional[dict] = None) -> dict[str, str]:
    """Child-process env: repo python, venv on PATH, plugin namespace importable.

    Children run with ``cwd`` at the repo root, where ``plugins/`` does not
    live, so ``PYTHONPATH`` is the only way ``plugins.openmontage.*`` resolves.

    ``DATA_ROOT`` is pinned rather than left to be re-derived: the child may not
    inherit the host's ``HUB_DATA_DIR`` (a Backlot server started straight from
    a shell doesn't), and a child that resolves a different data root writes
    checkpoints and artifacts where the parent will never look for them.
    """
    env = dict(os.environ if base is None else base)
    py = resolve_openmontage_python()
    env["OPENMONTAGE_PYTHON"] = str(py)
    env["OPENMONTAGE_DATA_ROOT"] = str(DATA_ROOT)
    import_root = str(IMPORT_ROOT)
    existing = env.get("PYTHONPATH", "")
    parts = [p for p in existing.split(os.pathsep) if p]
    if not any(p == import_root for p in parts):
        env["PYTHONPATH"] = os.pathsep.join([import_root, *parts])
    if py.parent.name in ("Scripts", "bin"):
        venv_root = py.parent.parent
        path_key = "Path" if os.name == "nt" else "PATH"
        prefix = str(py.parent)
        current = env.get(path_key, "")
        parts = current.split(os.pathsep) if current else []
        if not parts or Path(parts[0]).resolve() != py.parent.resolve():
            env[path_key] = os.pathsep.join([prefix, *parts])
        env["VIRTUAL_ENV"] = str(venv_root)
    return env


def python_invocation_hint() -> str:
    """One-line hint for agent prompts (absolute path, cross-platform)."""
    return str(resolve_openmontage_python())
