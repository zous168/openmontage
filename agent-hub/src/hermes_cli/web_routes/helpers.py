"""Shared helpers for dashboard background actions (gateway, ops, skills, …)."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from hermes_cli.config import get_hermes_home

_log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Short action name (from URL) → log file basename under the action log dir.
ACTION_LOG_FILES: Dict[str, str] = {
    "gateway-restart": "gateway-restart.log",
    "gateway-start": "gateway-start.log",
    "gateway-stop": "gateway-stop.log",
    "hermes-update": "hermes-update.log",
    "doctor": "action-doctor.log",
    "security-audit": "action-security-audit.log",
    "backup": "action-backup.log",
    "import": "action-import.log",
    "checkpoints-prune": "action-checkpoints-prune.log",
    "skills-install": "action-skills-install.log",
    "skills-uninstall": "action-skills-uninstall.log",
    "skills-update": "action-skills-update.log",
    "curator-run": "action-curator-run.log",
    "prompt-size": "action-prompt-size.log",
    "dump": "action-dump.log",
    "config-migrate": "action-config-migrate.log",
    "tools-post-setup": "action-tools-post-setup.log",
    "mcp-install": "action-mcp-install.log",
}

# name → most recently spawned Popen handle.
ACTION_PROCS: Dict[str, subprocess.Popen] = {}

# name → completed synthetic action result (no subprocess spawned).
ACTION_RESULTS: Dict[str, Dict[str, Any]] = {}


def action_log_dir() -> Path:
    """Gateway action logs under ``{data_root}/logs``."""
    from hermes_constants import get_hub_logs_dir

    return get_hub_logs_dir()


def record_completed_action(name: str, message: str, exit_code: int = 1) -> None:
    """Record a non-spawned action result and write it to the action log."""
    from hermes_cli.gateway_action_trace import log_gateway_trace

    log_file_name = ACTION_LOG_FILES[name]
    log_dir = action_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file_name
    with open(log_path, "ab", buffering=0) as log_file:
        log_file.write(
            f"\n=== {name} completed {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode()
        )
        log_file.write(message.encode("utf-8", errors="replace"))
        if not message.endswith("\n"):
            log_file.write(b"\n")
    ACTION_PROCS.pop(name, None)
    ACTION_RESULTS[name] = {"exit_code": exit_code, "pid": None}
    if name == "gateway-restart":
        log_gateway_trace("action.completed", name=name, exit_code=exit_code)


def spawn_hermes_action(subcommand: List[str], name: str) -> subprocess.Popen:
    """Spawn ``hermes <subcommand>`` detached and record the Popen handle."""
    from hermes_cli.gateway_action_trace import log_gateway_trace
    from hermes_constants import get_default_hermes_root

    log_file_name = ACTION_LOG_FILES[name]
    log_dir = action_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file_name
    log_file = open(log_path, "ab", buffering=0)
    log_file.write(
        f"\n=== {name} started {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n".encode()
    )

    cmd = [sys.executable, "-u", "-m", "hermes_cli.main", *subcommand]

    child_env = {**os.environ, "HERMES_NONINTERACTIVE": "1", "PYTHONUNBUFFERED": "1"}
    child_env.setdefault("HUB_DATA_DIR", str(get_hermes_home()))
    child_env.pop("HERMES_PROFILE", None)
    if name in ("gateway-restart", "gateway-start"):
        from hermes_cli.gateway_lifecycle import gateway_spawn_env

        child_env.update(gateway_spawn_env())
    src_root = str(PROJECT_ROOT)
    existing_pp = child_env.get("PYTHONPATH", "").strip()
    child_env["PYTHONPATH"] = os.pathsep.join(
        [p for p in [src_root, existing_pp] if p]
    )

    popen_kwargs: Dict[str, Any] = {
        "cwd": src_root,
        "stdin": subprocess.DEVNULL,
        "stdout": log_file,
        "stderr": subprocess.STDOUT,
        "env": child_env,
    }
    if sys.platform == "win32":
        from hermes_cli._subprocess_compat import windows_hide_flags

        popen_kwargs["creationflags"] = windows_hide_flags()
    else:
        popen_kwargs["start_new_session"] = True

    proc = subprocess.Popen(cmd, **popen_kwargs)
    log_gateway_trace(
        "action.spawn",
        name=name,
        pid=proc.pid,
        cmd=" ".join(cmd),
        cwd=src_root,
        log_path=str(log_path),
        pythonpath=child_env.get("PYTHONPATH", ""),
        hub_data_dir=child_env.get("HUB_DATA_DIR", ""),
        hermes_noninteractive=child_env.get("HERMES_NONINTERACTIVE", ""),
    )
    log_file.close()
    ACTION_RESULTS.pop(name, None)
    ACTION_PROCS[name] = proc
    return proc


def tail_lines(path: Path, n: int) -> List[str]:
    """Return the last ``n`` lines of ``path``."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    return lines[-n:] if n > 0 else lines


def spawn_gateway_restart() -> Tuple[subprocess.Popen, bool]:
    """先停 Hub 登记的 Gateway，再 ``gateway run``（不靠 ``--replace``）."""
    existing = ACTION_PROCS.get("gateway-restart")
    if existing is not None and existing.poll() is None:
        from hermes_cli.gateway_action_trace import log_gateway_trace

        log_gateway_trace("spawn.reuse", pid=existing.pid)
        return existing, True
    from hermes_cli.gateway_action_trace import log_gateway_trace
    from hermes_cli.gateway_lifecycle import stop_gateway_for_fresh_run

    log_gateway_trace("spawn.request")
    stop_gateway_for_fresh_run()
    return spawn_hermes_action(["gateway", "run"], "gateway-restart"), False


def apply_llm_runtime_reload() -> dict[str, Any]:
    """Best-effort: reload ``.env`` into Hub process and restart Hermes Gateway."""
    out: dict[str, Any] = {}
    try:
        from hermes_cli.config import reload_env

        out["env_reloaded"] = reload_env()
    except Exception:
        _log.exception("Failed to reload .env after LLM runtime change")
        out["env_reloaded"] = 0
        out["env_reload_error"] = "reload failed"
    try:
        proc, reused = spawn_gateway_restart()
        out["gateway_restart_started"] = True
        out["gateway_restart_action"] = "gateway-restart"
        out["gateway_restart_pid"] = proc.pid
        out["gateway_restart_reused"] = reused
    except Exception:
        _log.exception("Failed to restart gateway after LLM runtime change")
        out["gateway_restart_started"] = False
        out["gateway_restart_error"] = "spawn failed"
    return out


def restart_gateway_after_webhook_enable() -> dict[str, Any]:
    """Best-effort gateway restart after enabling the webhook platform."""
    try:
        proc, reused = spawn_gateway_restart()
    except Exception:
        _log.exception("Failed to auto-restart gateway after enabling webhooks")
        return {
            "restart_started": False,
            "restart_error": "spawn failed",
        }
    if reused:
        _log.info(
            "Webhook enable: reusing in-flight gateway restart (pid %s)",
            proc.pid,
        )
    return {
        "restart_started": True,
        "restart_action": "gateway-restart",
        "restart_pid": proc.pid,
    }


def restart_gateway_after_telegram_onboarding() -> dict[str, Any]:
    """Best-effort gateway restart after Telegram onboarding apply."""
    try:
        proc, reused = spawn_gateway_restart()
    except Exception:
        _log.exception("Failed to auto-restart gateway after Telegram onboarding")
        return {
            "restart_started": False,
            "restart_error": "spawn failed",
        }
    if reused:
        _log.info(
            "Telegram onboarding: reusing in-flight gateway restart (pid %s)",
            proc.pid,
        )
    return {
        "restart_started": True,
        "restart_action": "gateway-restart",
        "restart_pid": proc.pid,
    }
