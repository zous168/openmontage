"""父进程看门狗 —— 被 spawn 的子进程在父进程消失后自行退出。

`agent-hub` 以 sidecar 形式运行：宿主进程 spawn 它并注入 ``PARENT_PID``。
宿主被强杀（任务管理器、崩溃）时不会走正常关停流程，子进程就会变成孤儿继续占用端口。
本模块让子进程主动轮询父进程存活状态，父进程一消失就自退。

由 ``agent-hub/src/hermes_cli/parent_pid_watch.py`` 通过 sys.path 注入后以顶层模块导入，
并由 ``agent-hub/agent-hub.spec`` 作为 datas 打包进冻结产物。
"""

from __future__ import annotations

import os
import sys
import threading
import time

ENV_PARENT_PID = "PARENT_PID"

DEFAULT_POLL_INTERVAL = 2.0

__all__ = [
    "ENV_PARENT_PID",
    "child_spawn_env",
    "is_pid_alive",
    "parse_parent_pid_from_env",
    "start_parent_pid_watch",
]


def child_spawn_env(pid: int) -> dict[str, str]:
    """spawn 子进程时要叠加的环境变量：告诉它该监督谁。"""
    return {ENV_PARENT_PID: str(int(pid))}


def parse_parent_pid_from_env(env: dict[str, str] | None = None) -> int | None:
    """读取 ``PARENT_PID``；缺失、非数字或非正数一律返回 ``None``。"""
    source = os.environ if env is None else env
    raw = (source.get(ENV_PARENT_PID) or "").strip()
    if not raw:
        return None
    try:
        pid = int(raw)
    except ValueError:
        return None
    return pid if pid > 0 else None


def is_pid_alive(pid: int) -> bool:
    """跨平台判断进程是否存活。"""
    if pid <= 0:
        return False
    if os.name == "nt":
        return _is_pid_alive_windows(pid)
    try:
        # 信号 0 只做权限与存在性检查，不实际投递。
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # 进程存在但不属于当前用户。
        return True
    except OSError:
        return False
    return True


def _is_pid_alive_windows(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == _STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _resolve_parent_pid() -> int | None:
    """优先用显式注入的 ``PARENT_PID``；冻结态回退 ``getppid()``。

    源码运行时不回退 —— 开发者从终端直接起进程时，父进程是 shell，
    盯着它反而会在 shell 退出时误杀服务。
    """
    pid = parse_parent_pid_from_env()
    if pid is not None:
        return pid
    if getattr(sys, "frozen", False):
        ppid = os.getppid()
        if ppid > 0:
            return ppid
    return None


def start_parent_pid_watch(
    *,
    label: str = "child",
    poll_interval: float = DEFAULT_POLL_INTERVAL,
    exit_code: int = 0,
) -> bool:
    """启动看门狗线程，父进程消失即退出本进程。

    返回是否真的启动了监督。``False`` 表示无法确定父进程 —— 调用方自行决定
    是容忍（开发态）还是拒绝启动（sidecar 必须有宿主）。
    """
    parent_pid = _resolve_parent_pid()
    if parent_pid is None:
        return False
    if not is_pid_alive(parent_pid):
        # 父进程在我们起来之前就没了，没必要再进循环。
        _exit_now(label, parent_pid, exit_code)
        return True

    interval = max(0.1, float(poll_interval))

    def _watch() -> None:
        while True:
            time.sleep(interval)
            if not is_pid_alive(parent_pid):
                _exit_now(label, parent_pid, exit_code)
                return

    thread = threading.Thread(
        target=_watch, name=f"parent-pid-watch[{label}]", daemon=True
    )
    thread.start()
    return True


def _exit_now(label: str, parent_pid: int, exit_code: int) -> None:
    """立即终止本进程。

    用 ``os._exit`` 而非 ``sys.exit``：看门狗跑在守护线程里，``SystemExit``
    只会结束该线程；而且此时宿主已死，也没有值得等待的优雅关停。
    """
    sys.stderr.write(
        f"{label}: parent process {parent_pid} exited — shutting down\n"
    )
    sys.stderr.flush()
    os._exit(exit_code)
