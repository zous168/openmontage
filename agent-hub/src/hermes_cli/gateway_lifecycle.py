"""Gateway 随宿主进程启停（组合根 ``wire_gateway_lifecycle`` 挂载）."""

from __future__ import annotations

import asyncio
import logging
import os
import socket
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from typing import Any

from fastapi import FastAPI

logger = logging.getLogger(__name__)
_gw_logger = logging.getLogger("hermes.gateway.out")

# Strong reference to hub-attached gateway subprocess (prevents GC closing pipes).
_hub_gateway_proc: subprocess.Popen | None = None


def _truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"1", "true", "yes", "on"}


def _falsy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in {"0", "false", "no", "off"}


def is_gateway_autostart_enabled() -> bool:
    """``HERMES_GATEWAY_AUTOSTART=0`` 可关闭."""
    override = os.environ.get("HERMES_GATEWAY_AUTOSTART")
    if _falsy(override):
        return False
    if _truthy(override):
        return True
    return True


def hub_supervisor_pid() -> int:
    """Hub 自身 ``start_parent_pid_watch`` 的监督者（MxAI sidecar 注入 / dev reload 用 ``getppid``）."""
    from hermes_cli.parent_pid_watch import parse_parent_pid_from_env

    pid = parse_parent_pid_from_env()
    if pid is not None:
        return pid
    if os.environ.get("RUN_MAIN") == "true":
        ppid = os.getppid()
        if ppid > 0:
            return ppid
    return os.getpid()


def hub_parent_process_pid() -> int:
    """兼容别名 → :func:`hub_supervisor_pid`."""
    return hub_supervisor_pid()


def gateway_supervisor_pid() -> int:
    """Hub 拉起 Gateway 时注入的 ``PARENT_PID``：谁 spawn 谁监督 → 当前 Hub 进程."""
    return os.getpid()


def should_stop_spawned_gateways_on_shutdown() -> bool:
    """``uvicorn --reload`` worker 回收时不关停 Gateway（监督者仍在）."""
    return os.environ.get("RUN_MAIN") != "true"


def hub_listen_endpoint() -> tuple[str, int]:
    """Hub API 监听地址（与 ``_start_hub_backend.ps1`` / ``main.py`` 对齐）."""
    host = (os.environ.get("HUB_API_HOST") or "127.0.0.1").strip()
    if host in {"0.0.0.0", "::", ""}:
        host = "127.0.0.1"
    port = int((os.environ.get("HUB_API_PORT") or "8642").strip())
    return host, port


def hub_listen_ready() -> bool:
    """Return True when something is accepting TCP on the hub API port."""
    host, port = hub_listen_endpoint()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.3)
    try:
        sock.connect((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


async def wait_for_hub_serving(
    cancel: asyncio.Event,
    *,
    timeout: float = 60.0,
    poll_interval: float = 0.2,
) -> bool:
    """Wait until hub binds its API port, or ``cancel`` / timeout."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if cancel.is_set():
            return False
        if await asyncio.to_thread(hub_listen_ready):
            return True
        await asyncio.sleep(poll_interval)
    return False


def gateway_spawn_env(*, parent_pid: int | None = None) -> dict[str, str]:
    from hermes_cli.parent_pid_watch import child_spawn_env

    pid = parent_pid if parent_pid is not None else gateway_supervisor_pid()
    return child_spawn_env(pid)


@contextmanager
def gateway_spawn_context(*, parent_pid: int | None = None):
    overlay = gateway_spawn_env(parent_pid=parent_pid)
    saved = {key: os.environ.get(key) for key in overlay}
    try:
        os.environ.update(overlay)
        yield overlay
    finally:
        for key, previous in saved.items():
            if previous is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = previous


def _stop_gateway_pid(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        from gateway.status import (
            _pid_exists,
            get_running_pid,
            remove_pid_file,
            terminate_pid,
            write_planned_stop_marker,
        )
    except ImportError:
        return False

    if not _pid_exists(pid):
        return False

    try:
        write_planned_stop_marker(pid)
    except Exception:
        pass

    try:
        terminate_pid(pid, force=False)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        return False

    deadline = time.monotonic() + 10.0
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            if get_running_pid() == pid:
                remove_pid_file()
            return True
        time.sleep(0.25)

    try:
        terminate_pid(pid, force=True)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        return False
    return not _pid_exists(pid)


def stop_spawned_gateways() -> list[int]:
    """Stop the gateway recorded in ``gateway.pid`` (if any)."""
    stopped: list[int] = []
    try:
        from hermes_constants import get_default_hermes_root
        from gateway.status import get_running_pid

        pid = get_running_pid(
            get_default_hermes_root() / "gateway.pid",
            cleanup_stale=False,
        )
        if pid is not None and _stop_gateway_pid(pid):
            stopped.append(pid)
    except Exception:
        pass

    if stopped:
        live_tui = None
        try:
            from tui_gateway import server as tui_server

            live_tui = len(getattr(tui_server, "_sessions", {}))
        except Exception:
            pass
        logger.info(
            "hermes.gateway.stop stopped_pids=%s live_tui_sessions=%s",
            stopped,
            live_tui,
        )
    return stopped


def _ensure_gw_handler() -> None:
    """确保 gateway 转发 logger 有可见 handler.

    Hub 用 structlog + uvicorn；``hermes.gateway.out`` 这个 stdlib logger 默认
    无 handler、root 也无 handler，INFO 会被直接丢弃（同理之前的 ``[diag]`` 也从没
    出现过）。这里复用 uvicorn 的 handler，让转发行与 ``INFO:`` 访问日志落到同一
    输出流、同一格式；uvicorn 不存在时退回自建 StreamHandler(stderr)。
    """
    if _gw_logger.handlers:
        return
    handlers = (
        logging.getLogger("uvicorn.error").handlers
        or logging.getLogger("uvicorn").handlers
    )
    if handlers:
        for h in handlers:
            _gw_logger.addHandler(h)
    else:
        h = logging.StreamHandler(sys.stderr)
        h.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
        _gw_logger.addHandler(h)
    _gw_logger.setLevel(logging.INFO)
    _gw_logger.propagate = False


def _forward_gateway_output(proc: subprocess.Popen) -> None:
    """读取 gateway 子进程的 stdout+stderr 并转发到 hub logger（daemon 线程）.

    每行前缀 ``[gateway pid=<PID>]`` 以便与 hub 自身日志区分、并标明来源进程。
    """
    _ensure_gw_handler()
    pid = proc.pid

    def _reader() -> None:
        assert proc.stdout is not None
        try:
            for raw in proc.stdout:
                line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
                if line:
                    _gw_logger.info("[gateway pid=%d] %s", pid, line)
        except Exception:
            pass
        finally:
            rc = proc.poll()
            _gw_logger.info("[gateway pid=%d] <stdout closed, exit_code=%s>", pid, rc)

    t = threading.Thread(target=_reader, daemon=True, name="hub-gateway-stdout")
    t.start()


def _spawn_hub_attached_gateway() -> int | None:
    """Hub 场景下以 attached 方式启动 gateway，将其 stdout/stderr 转发到 hub logger.

    与 _spawn_detached_gateway 的区别：
    - Windows 用 python.exe（非 pythonw），无 DETACHED_PROCESS 等隔离 flag
    - stdout/stderr 通过 PIPE 捕获，由 reader 线程实时写入 hermes.gateway.out logger
    - 进程句柄存入 _hub_gateway_proc 防止 GC
    """
    global _hub_gateway_proc

    supervisor_pid = gateway_supervisor_pid()

    cmd: list[str]
    popen_kwargs: dict

    if sys.platform == "win32":
        try:
            from hermes_cli.gateway_windows import _build_gateway_argv
        except ImportError:
            return None

        cmd, working_dir, env_overlay = _build_gateway_argv(
            gateway_parent_pid=supervisor_pid,
        )

        env = {
            **os.environ,
            **env_overlay,
            **gateway_spawn_env(parent_pid=supervisor_pid),
        }

        # python.exe（有控制台）代替 pythonw.exe，这样 stdout/stderr 可以被 PIPE 捕获
        exe = cmd[0]
        if exe.lower().endswith("w.exe"):
            candidate = exe[:-5] + ".exe"
            if os.path.isfile(candidate):
                cmd[0] = candidate

        popen_kwargs = {
            "cwd": working_dir,
            "env": env,
            "creationflags": 0x00000200,  # CREATE_NEW_PROCESS_GROUP
        }
    else:
        try:
            from hermes_cli.gateway import _gateway_run_command
        except ImportError:
            return None

        cmd = _gateway_run_command()
        env = os.environ.copy()
        env["HERMES_GATEWAY_DETACHED"] = "1"
        env.update(gateway_spawn_env(parent_pid=supervisor_pid))
        popen_kwargs = {"env": env}

    try:
        proc = subprocess.Popen(
            cmd,
            **popen_kwargs,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
    except OSError as exc:
        logger.warning(
            "[gateway.lifecycle] hub_spawn_failed supervisor=%d cmd=%r cwd=%s error=%s",
            supervisor_pid,
            cmd,
            popen_kwargs.get("cwd"),
            exc,
        )
        return None

    hub_data = env.get("HUB_DATA_DIR", os.environ.get("HUB_DATA_DIR", ""))
    parent_pid = env.get("PARENT_PID", "")
    logger.info(
        "[gateway.lifecycle] hub_spawn cmd=%r cwd=%s HUB_DATA_DIR=%s PARENT_PID=%s supervisor=%d",
        cmd,
        popen_kwargs.get("cwd"),
        hub_data,
        parent_pid,
        supervisor_pid,
    )

    _hub_gateway_proc = proc
    _forward_gateway_output(proc)
    logger.info(
        "[gateway.lifecycle] hub_attached child_pid=%d exe=%s supervisor=%d",
        proc.pid,
        cmd[0],
        supervisor_pid,
    )
    return proc.pid


def stop_gateway_for_fresh_run() -> list[int]:
    """停掉 ``gateway.pid`` 中的 Gateway，便于无 ``--replace`` 的 ``gateway run`` 占住唯一槽位."""
    return stop_spawned_gateways()


def _gateway_autostart_wait_seconds() -> float:
    """Onefile sidecar 冷启动 gateway 需二次解压，给足 pid 文件就绪时间."""
    if getattr(sys, "frozen", False):
        return 60.0
    return 15.0


def _autostart_context() -> dict[str, str]:
    """Snapshot paths/env for autostart diagnostic logs."""
    from gateway.status import _get_gateway_lock_path, _get_pid_path
    from hermes_constants import get_default_hermes_root, get_hermes_home

    return {
        "hub_pid": str(os.getpid()),
        "supervisor_pid": str(gateway_supervisor_pid()),
        "HUB_DATA_DIR": os.environ.get("HUB_DATA_DIR", ""),
        "DATA_DIR": os.environ.get("DATA_DIR", ""),
        "PARENT_PID": os.environ.get("PARENT_PID", ""),
        "hermes_home": str(get_hermes_home()),
        "default_root": str(get_default_hermes_root()),
        "pid_path": str(_get_pid_path()),
        "lock_path": str(_get_gateway_lock_path()),
        "frozen": str(getattr(sys, "frozen", False)),
    }


def _wait_for_gateway_ready(
    *,
    attached_pid: int | None,
    wait_seconds: float,
    spawn_mode: str,
) -> dict[str, object]:
    """Poll ``get_running_pid`` with periodic ``probe_running_pid`` logs."""
    from gateway.status import _pid_exists, get_running_pid, probe_running_pid

    deadline = time.monotonic() + wait_seconds
    poll = 0
    last_probe_log = 0.0

    while time.monotonic() < deadline:
        poll += 1
        pid = get_running_pid()
        if pid is not None:
            logger.info(
                "[gateway.lifecycle] autostart ready mode=%s poll=%d pid=%d ctx=%s",
                spawn_mode,
                poll,
                pid,
                _autostart_context(),
            )
            return {"status": "started", "pid": pid, "polls": poll, "mode": spawn_mode}

        now = time.monotonic()
        if poll == 1 or now - last_probe_log >= 10.0:
            probe = probe_running_pid()
            attached_alive = (
                attached_pid is not None
                and attached_pid > 0
                and _pid_exists(attached_pid)
            )
            logger.info(
                "[gateway.lifecycle] autostart waiting mode=%s poll=%d "
                "attached_pid=%s attached_alive=%s elapsed=%.1fs probe=%s",
                spawn_mode,
                poll,
                attached_pid,
                attached_alive,
                wait_seconds - (deadline - now),
                probe,
            )
            last_probe_log = now
        time.sleep(0.5)

    probe = probe_running_pid()
    attached_alive = (
        attached_pid is not None and attached_pid > 0 and _pid_exists(attached_pid)
    )

    if attached_alive and probe.get("status") == "running":
        pid = int(probe["candidate_pid"])
        logger.info(
            "[gateway.lifecycle] autostart ready_after_wait mode=%s poll=%d pid=%d probe=%s",
            spawn_mode,
            poll,
            pid,
            probe,
        )
        return {
            "status": "started",
            "pid": pid,
            "polls": poll,
            "mode": spawn_mode,
            "via": "final_probe",
        }

    if attached_alive and probe.get("lock_active"):
        lock_pid = probe.get("candidate_pid") or attached_pid
        logger.warning(
            "[gateway.lifecycle] autostart lock_fallback mode=%s attached_pid=%d "
            "lock_active=%s probe=%s ctx=%s",
            spawn_mode,
            attached_pid,
            probe.get("lock_active"),
            probe,
            _autostart_context(),
        )
        return {
            "status": "started",
            "pid": int(lock_pid),
            "polls": poll,
            "mode": spawn_mode,
            "via": "lock_fallback",
            "probe": probe,
        }

    if attached_alive:
        logger.warning(
            "[gateway.lifecycle] autostart spawn_timeout attached_alive mode=%s "
            "attached_pid=%d poll=%d probe=%s ctx=%s",
            spawn_mode,
            attached_pid,
            poll,
            probe,
            _autostart_context(),
        )
        return {
            "status": "spawn_timeout",
            "pid": attached_pid,
            "polls": poll,
            "mode": spawn_mode,
            "probe": probe,
        }

    logger.error(
        "[gateway.lifecycle] autostart failed mode=%s attached_pid=%s poll=%d probe=%s ctx=%s",
        spawn_mode,
        attached_pid,
        poll,
        probe,
        _autostart_context(),
    )
    return {
        "status": "spawn_timeout",
        "polls": poll,
        "mode": spawn_mode,
        "probe": probe,
    }


def ensure_gateway_running(*, wait_seconds: float | None = None) -> dict[str, object]:
    from gateway.status import _pid_exists, get_running_pid, probe_running_pid, remove_pid_file

    if wait_seconds is None:
        wait_seconds = _gateway_autostart_wait_seconds()

    ctx = _autostart_context()
    initial_probe = probe_running_pid()
    logger.info(
        "[gateway.lifecycle] autostart begin wait_seconds=%.0f ctx=%s probe=%s",
        wait_seconds,
        ctx,
        initial_probe,
    )

    existing = get_running_pid()
    if existing is not None:
        if _pid_exists(existing):
            logger.info(
                "[gateway.lifecycle] autostart already_running pid=%d ctx=%s",
                existing,
                ctx,
            )
            return {"status": "already_running", "pid": existing}
        logger.warning(
            "[gateway.lifecycle] autostart stale_pid_file pid=%d ctx=%s probe=%s",
            existing,
            ctx,
            initial_probe,
        )
        try:
            remove_pid_file()
        except Exception as exc:
            logger.warning(
                "[gateway.lifecycle] autostart remove_stale_pid failed: %s",
                exc,
            )

    if not os.environ.get("DATA_DIR", "").strip():
        try:
            from hermes_constants import get_default_hermes_root

            os.environ.setdefault("DATA_DIR", str(get_default_hermes_root()))
        except Exception:
            pass

    parent = gateway_supervisor_pid()

    attached_pid = _spawn_hub_attached_gateway()
    if attached_pid is not None:
        return _wait_for_gateway_ready(
            attached_pid=attached_pid,
            wait_seconds=wait_seconds,
            spawn_mode="hub_attached",
        )

    logger.info(
        "[gateway.lifecycle] autostart fallback detached parent=%d ctx=%s",
        parent,
        _autostart_context(),
    )
    from hermes_cli.gateway import _spawn_detached_gateway

    with gateway_spawn_context(parent_pid=parent):
        if not _spawn_detached_gateway():
            logger.error(
                "[gateway.lifecycle] autostart spawn_failed mode=detached ctx=%s",
                _autostart_context(),
            )
            return {"status": "spawn_failed"}

    return _wait_for_gateway_ready(
        attached_pid=None,
        wait_seconds=wait_seconds,
        spawn_mode="detached",
    )


def _ensure_hub_loggers_visible() -> None:
    """把 hub 关键 stdlib 包 logger 挂到 uvicorn 的 handler 上，让它们真正可见。

    hub 用 structlog + uvicorn；uvicorn 默认只给 ``uvicorn*`` 配 handler、root 不配，
    于是 ``hermes_cli`` / ``tui_gateway`` 里所有 ``logging.getLogger(__name__).info(...)``
    （含 ``/api/ws`` 握手鉴权的 ``[diag]`` 行、tui_gateway 的连接/关闭原因）全被丢弃——
    这正是「TUI 报 gateway exited 而 hub/gateway 日志一片空白」的原因。这里让这些包
    logger 复用 uvicorn 的输出流，与 ``INFO:`` 访问日志同处可见。
    """
    handlers = (
        logging.getLogger("uvicorn.error").handlers
        or logging.getLogger("uvicorn").handlers
    )
    for name in ("hermes_cli", "tui_gateway", "gateway.status", "gateway.run"):
        lg = logging.getLogger(name)
        if handlers:
            existing_ids = {id(h) for h in lg.handlers}
            for h in handlers:
                if id(h) not in existing_ids:
                    lg.addHandler(h)
        elif not lg.handlers:
            h = logging.StreamHandler(sys.stderr)
            h.setFormatter(logging.Formatter("%(levelname)s:     %(message)s"))
            lg.addHandler(h)
        if lg.level == logging.NOTSET or lg.level > logging.INFO:
            lg.setLevel(logging.INFO)


def wire_gateway_lifecycle(app: FastAPI) -> None:
    """在组合根 FastAPI app 上注册 Gateway 启停.

    FastAPI 0.109+ 在已有 ``lifespan`` 时 ``on_event(startup)`` 不会执行，
    因此这里链入 ``app.router.lifespan_context``。
    """
    from contextlib import asynccontextmanager

    from hermes_cli.shutdown_diag import log_shutdown_snapshot, wire_shutdown_diag

    wire_shutdown_diag(app)

    existing = app.router.lifespan_context

    async def _autostart_gateway_background(cancel: asyncio.Event) -> None:
        """Gateway 自拉起：等 Hub 监听后再 spawn，并周期性保活（死后重拉）。"""
        if not is_gateway_autostart_enabled():
            logger.info("[gateway.lifecycle] autostart disabled via HERMES_GATEWAY_AUTOSTART")
            return
        host, port = hub_listen_endpoint()
        if not await wait_for_hub_serving(cancel):
            if cancel.is_set():
                logger.info(
                    "[gateway.lifecycle] autostart skipped: hub not serving on %s:%s "
                    "(shutdown before bind)",
                    host,
                    port,
                )
            else:
                logger.warning(
                    "[gateway.lifecycle] autostart skipped: hub listen timeout on %s:%s",
                    host,
                    port,
                )
            return

        # Hub 存活期间周期性 ensure：首次必拉；之后若 PID 丢失则重拉。
        keep_alive_sec = 30.0
        while not cancel.is_set():
            try:
                result = await asyncio.to_thread(ensure_gateway_running)
                logger.info("[gateway.lifecycle] autostart result=%s", result)
            except asyncio.CancelledError:
                logger.info("[gateway.lifecycle] autostart cancelled during gateway spawn")
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("hermes.gateway.autostart_failed: %s", exc)

            try:
                await asyncio.wait_for(cancel.wait(), timeout=keep_alive_sec)
                return
            except asyncio.TimeoutError:
                continue

    @asynccontextmanager
    async def _hub_gateway_lifespan(app_instance: FastAPI):
        # uvicorn 此时已配好日志；把 hub 的 stdlib 包 logger 挂上去，让 [diag] 等可见。
        try:
            _ensure_hub_loggers_visible()
        except Exception:  # noqa: BLE001
            pass

        autostart_cancel = asyncio.Event()
        autostart_task: asyncio.Task[None] | None = None
        device_auth_refresh_cancel = asyncio.Event()
        device_auth_refresh_task: asyncio.Task[None] | None = None

        from core.platform.device.device_auth_service import device_auth_refresh_background

        device_auth_refresh_task = asyncio.create_task(
            device_auth_refresh_background(device_auth_refresh_cancel),
            name="device-auth-refresh",
        )

        if existing is not None:
            async with existing(app_instance):
                autostart_task = asyncio.create_task(
                    _autostart_gateway_background(autostart_cancel)
                )
                yield
        else:
            autostart_task = asyncio.create_task(
                _autostart_gateway_background(autostart_cancel)
            )
            yield

        log_shutdown_snapshot("lifespan_shutdown_begin")

        autostart_cancel.set()
        device_auth_refresh_cancel.set()
        if device_auth_refresh_task is not None:
            device_auth_refresh_task.cancel()
            try:
                await device_auth_refresh_task
            except asyncio.CancelledError:
                pass
        if autostart_task is not None:
            autostart_task.cancel()
            try:
                await autostart_task
            except asyncio.CancelledError:
                pass

        if not should_stop_spawned_gateways_on_shutdown():
            logger.info("hermes.gateway.shutdown skipped (uvicorn reload worker)")
            return
        try:
            stopped = await asyncio.to_thread(stop_spawned_gateways)
            log_shutdown_snapshot("lifespan_gateway_stop_done")
            if stopped:
                logger.info("hermes.gateway.shutdown stopped_pids=%s", stopped)
                live_tui = None
                try:
                    from tui_gateway import server as tui_server

                    live_tui = len(getattr(tui_server, "_sessions", {}))
                except Exception:
                    pass
                if live_tui:
                    logger.warning(
                        "hermes.gateway.shutdown while live_tui_sessions=%s — "
                        "dashboard chat WS may disconnect (code 1012) and show "
                        "'gateway exited'",
                        live_tui,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("hermes.gateway.shutdown_failed: %s", exc)

    app.router.lifespan_context = _hub_gateway_lifespan
