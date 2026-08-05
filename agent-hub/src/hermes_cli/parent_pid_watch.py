"""Shim → 仓库 ``shared/parent_pid_watch.py``（统一 ``PARENT_PID``）."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_shared_on_path() -> None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.append(Path(meipass))
    here = Path(__file__).resolve()
    candidates.append(here.parents[3] / "shared")  # marketing-hub/shared
    for base in candidates:
        mod = base / "parent_pid_watch.py"
        if mod.is_file():
            root = str(base)
            if root not in sys.path:
                sys.path.insert(0, root)
            return


_ensure_shared_on_path()

from parent_pid_watch import (  # noqa: E402
    ENV_PARENT_PID,
    child_spawn_env,
    is_pid_alive,
    parse_parent_pid_from_env,
    start_parent_pid_watch,
)

__all__ = [
    "ENV_PARENT_PID",
    "child_spawn_env",
    "is_pid_alive",
    "parse_parent_pid_from_env",
    "start_parent_pid_watch",
]
