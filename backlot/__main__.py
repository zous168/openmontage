"""Backlot CLI.

    python -m backlot open [project-id]   # start server if needed, open browser
    python -m backlot serve [--port N]    # run the server in the foreground

``open`` is idempotent and non-fatal by design: agents call it at pipeline
initialization and must continue the production even if it fails.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser

from backlot import API_VERSION, DEFAULT_PORT
from lib.python_runtime import ensure_repo_interpreter, openmontage_python_env, resolve_openmontage_python


def _port() -> int:
    try:
        return int(os.environ.get("BACKLOT_PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


def _probe_health(port: int) -> dict | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as resp:
            if resp.status != 200:
                return None
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def _server_alive(port: int) -> bool:
    return _probe_health(port) is not None


def _server_ready(port: int) -> bool:
    data = _probe_health(port)
    if not data or not data.get("ok"):
        return False
    try:
        return int(data.get("api_version", 1)) >= API_VERSION
    except (TypeError, ValueError):
        return False


def _stop_listener(port: int) -> None:
    """Best-effort kill of whatever is listening on *port* (stale Backlot)."""
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["netstat", "-ano"],
                capture_output=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except Exception:
            return
        raw = out.stdout or b""
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("mbcs", errors="replace")
        pids: set[int] = set()
        token = f":{port}"
        for line in text.splitlines():
            if "LISTENING" not in line or token not in line:
                continue
            parts = line.split()
            if not parts:
                continue
            try:
                pids.add(int(parts[-1]))
            except ValueError:
                continue
        for pid in pids:
            if pid <= 0:
                continue
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
    else:
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )


def _spawn_server(port: int) -> None:
    """Start the server as a detached background process."""
    py = str(resolve_openmontage_python())
    cmd = [py, "-m", "backlot", "serve", "--port", str(port)]
    kwargs: dict = {
        "env": openmontage_python_env(),
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def cmd_open(project_id: str | None) -> int:
    port = _port()
    if _server_alive(port) and not _server_ready(port):
        print("backlot: restarting server (API update)")
        _stop_listener(port)
        time.sleep(0.6)
    if not _server_alive(port):
        try:
            _spawn_server(port)
        except Exception as exc:
            print(f"backlot: could not start server ({exc}) — continuing without the board")
            return 1
        deadline = time.time() + 15
        while time.time() < deadline:
            if _server_ready(port):
                break
            time.sleep(0.4)
        else:
            print("backlot: server did not come up in time — continuing without the board")
            return 1
    url = f"http://127.0.0.1:{port}/"
    if project_id:
        url = f"http://127.0.0.1:{port}/p/{project_id}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"backlot: {url}")
    return 0


def cmd_serve(port: int) -> int:
    import uvicorn

    uvicorn.run("backlot.server:app", host="127.0.0.1", port=port, log_level="warning")
    return 0


def main(argv: list[str] | None = None) -> int:
    ensure_repo_interpreter()
    parser = argparse.ArgumentParser(prog="backlot", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_open = sub.add_parser("open", help="open the board in the browser (starts server if needed)")
    p_open.add_argument("project_id", nargs="?", default=None)

    p_serve = sub.add_parser("serve", help="run the Backlot server in the foreground")
    p_serve.add_argument("--port", type=int, default=_port())

    args = parser.parse_args(argv)
    if args.command == "open":
        return cmd_open(args.project_id)
    if args.command == "serve":
        return cmd_serve(args.port)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
