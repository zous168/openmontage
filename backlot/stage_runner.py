"""Stage runner — headless-agent stage execution + page-driven approval for Backlot.

页面驱动通道：``POST /api/project/{id}/stage/run`` 触发无头 claude CLI
（``claude -p --permission-mode bypassPermissions``）执行**单一** pipeline 阶段。
无头 agent 读同一份 director skill、走同一 registry（工具事件自动落
events.jsonl）、写同一份 checkpoint 契约 —— 与交互式 agent 完全同轨。

职责边界（HARD）：
- 本模块绝不写 checkpoint 的 ``completed`` / ``awaiting_human`` —— 唯一例外是
  取消/超时/服务重启时对 agent 留下的 ``in_progress`` 补写 ``failed``。
- 绝不写 decision_log 的 ``user_approved=true`` —— 唯一例外是页面批准
  （``approve_stage``），且必须镜像追加同 (category, subject) 的决策，
  否则 ``production_audit.check_approval_gate_drift`` 报 critical。
- 本模块新增的文件（``runs/``、``.run.lock``）只作观察元数据，不进入
  checkpoint / artifacts / decision_log / events.jsonl 契约路径。
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from lib.paths import PROJECTS_DIR, REPO_ROOT

RUNS_DIRNAME = "runs"
LOCK_FILENAME = ".run.lock"
RUN_STATUSES = ("queued", "running", "succeeded", "failed", "aborted")
KEEP_RUNS = 20
HEARTBEAT_SECONDS = 25
MONITOR_POLL_SECONDS = 5
RECONCILE_STAGNANT_SECONDS = 120
# prepare 加锁 → run_task 写出 runs/*.json 之间的窗口；超出视为孤儿锁。
ORPHAN_LOCK_GRACE_SECONDS = 45
DEFAULT_WALL_TIME_MINUTES = 30
MIN_WALL_TIME_MINUTES = 10
DEFAULT_BUDGET_USD = 5
REVISION_LIMIT_DEFAULT = 3
# 尾巴按**原始 NDJSON 字节**切——一个事件动辄数百字节，取得太小渲染后
# 只剩一两行，板面预览就没信息量了。
LOG_TAIL_CHARS = 8000


class StageRunError(Exception):
    """Bad request (400) — stage order violation, missing checkpoint, etc."""

    status = 400


class StageBusyError(StageRunError):
    """A run is already active for this project (409)."""

    status = 409


class RevisionLimitError(StageRunError):
    """Manifest revision cap reached (409)."""

    status = 409


@dataclass
class RunTask:
    task_id: str
    project_dir: Path
    project_id: str
    stage: str
    pipeline_type: str
    status: str = "queued"
    started_at: str = ""
    finished_at: Optional[str] = None
    exit_code: Optional[int] = None
    error: Optional[str] = None
    pid: Optional[int] = None
    timeout_seconds: float = DEFAULT_WALL_TIME_MINUTES * 60
    budget_usd: float = DEFAULT_BUDGET_USD
    log_path: Path = field(init=False)
    prompt: str = ""
    started_ts: float = field(default_factory=time.time)
    # 取消/超时由外部设置（cancel_run / _monitor），run_task 的
    # communicate 返回后据此定终态。
    requested_status: Optional[str] = None
    proc: Optional[asyncio.subprocess.Process] = None
    monitor_task: Optional[asyncio.Task] = None
    heartbeat_task: Optional[asyncio.Task] = None

    def __post_init__(self) -> None:
        self.started_at = datetime.now(timezone.utc).isoformat()
        self.log_path = self.project_dir / RUNS_DIRNAME / f"{self.task_id}.log"


# 内存态运行句柄（先例：edit_preview._PREVIEW_SESSIONS）——服务重启后靠
# runs/*.json + reconcile 重建，_TASKS 不是唯一事实来源。
_TASKS: dict[str, RunTask] = {}


def _read_json(path: Path) -> Optional[dict]:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _runs_dir(project_dir: Path) -> Path:
    return project_dir / RUNS_DIRNAME


def _lock_path(project_dir: Path) -> Path:
    return project_dir / LOCK_FILENAME


def _run_state_path(project_dir: Path, task_id: str) -> Path:
    return _runs_dir(project_dir) / f"{task_id}.json"


# ---------------------------------------------------------------------------
# CLI 解析（Windows 关键路径）
# ---------------------------------------------------------------------------


def _resolve_claude_cmd() -> list[str]:
    """返回可被 CreateProcess 执行的 claude 命令 argv 头（不含参数）。

    已知事实（本机实测）：npm 全局目录 ``%APPDATA%/npm/claude`` 是
    extensionless POSIX sh 脚本（Git Bash 的 which 能找到但 CreateProcess
    无法执行）；真正的入口是 ``claude.cmd`` → 直接调用 npm 包内原生
    ``bin/claude.exe``。解析顺序：
    1. npm 包内原生 exe（Windows 优先，零中间层）
    2. shutil.which("claude.cmd") / "claude.exe"（PATHEXT 解析，排除 sh 脚本）
    3. 降级 "claude"（POSIX 或 PATH 里确实有可执行文件时）
    """
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            native = (
                Path(appdata)
                / "npm"
                / "node_modules"
                / "@anthropic-ai"
                / "claude-code"
                / "bin"
                / "claude.exe"
            )
            if native.is_file():
                return [str(native)]
    for name in ("claude.cmd", "claude.exe", "claude"):
        found = _which(name)
        if found:
            return [found]
    raise StageRunError("未找到 claude CLI——请确认 Claude Code 已安装并加入 PATH")


def _which(name: str) -> Optional[str]:
    import shutil

    try:
        resolved = shutil.which(name)
    except OSError:
        return None
    if not resolved:
        return None
    # Git Bash 下 which("claude") 可能命中 extensionless sh 脚本——CreateProcess
    # 无法执行（无 PATHEXT 后缀），必须排除。
    if os.name == "nt" and "." not in Path(resolved).name:
        return None
    return resolved


def _build_cli_args(budget_usd: float) -> list[str]:
    """argv 100% 静态（budget 来自 manifest 数值）——用户输入只经 stdin。

    用 ``stream-json`` 而非 ``text``：text 只在进程结束时一次性吐出，
    于是「查看日志」在最需要它的时候（阶段跑了几分钟还没结束）永远是空的。
    stream-json 实时逐行落盘，日志随 agent 推进增长。原始 NDJSON 留在
    ``runs/*.log``（保真、可 debug），展示前经 ``render_run_log`` 渲染。
    """
    return [
        "-p",
        "--output-format", "stream-json",
        "--verbose",  # stream-json 在 -p 下需要它才输出逐事件流
        "--permission-mode", "bypassPermissions",
        "--max-budget-usd", f"{budget_usd:.2f}",
    ]


# 会话级宿主变量——必须从无头子进程环境剥离。
#
# 背景（本机实测，21 次 spawn 最小化）：Backlot server 通常由交互式 agent
# 启动（`python -m backlot open <id>`），于是继承宿主会话注入的
# ``CLAUDE_CODE_ENTRYPOINT='claude-desktop'``。原样传给独立 spawn 的
# claude CLI 后，子进程认定自己跑在桌面 App 内、改用**宿主托管的 OAuth
# 凭据**而非 settings.json 的 ANTHROPIC_AUTH_TOKEN，凭据过期即
# ``401 OAuth access token has expired``——无头通道整体不可用。
#
# ENTRYPOINT 是唯一的必需项（其余单独保留均不致命），但会话身份/宿主
# 认证握手类变量同样不该泄漏进一个独立会话，一并剥离。用户自己在
# settings.json 配的 CLAUDE_CODE_*（SUBAGENT_MODEL / EFFORT_LEVEL / …）
# 不在此列，且 CLI 会自行重读 settings.json，配置不丢。
_CHILD_ENV_DROP = frozenset({
    "CLAUDE_CODE_ENTRYPOINT",           # ← 401 的直接成因
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_HOST_SESSION_ID",
    "CLAUDE_CODE_CHILD_SESSION",
    "CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH",
    "CLAUDE_CODE_SDK_HAS_OAUTH_REFRESH",
    "CLAUDE_CODE_OAUTH_SCOPES",
    "CLAUDE_CODE_EXECPATH",
    "CLAUDECODE",
    "CLAUDE_PID",
    "CLAUDE_AGENT_SDK_VERSION",
})


def _child_env(base: Optional[dict] = None) -> dict:
    """无头子进程环境：继承机器配置（ANTHROPIC_* 等），剥离宿主会话变量。"""
    from lib.python_runtime import openmontage_python_env

    env = openmontage_python_env(base)
    for key in _CHILD_ENV_DROP:
        env.pop(key, None)
    return env


# ---------------------------------------------------------------------------
# 锁（server 侧行为，不进 lib/checkpoint.py——交互式 agent 通道零改动）
# ---------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        return psutil.pid_exists(pid)
    except ImportError:
        pass
    if os.name == "nt":
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}"],
                capture_output=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            text = (out.stdout or b"").decode("utf-8", errors="replace")
            return f"PID {pid}" in text
        except OSError:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _lock_is_stale(lock: dict, project_dir: Optional[Path] = None) -> bool:
    expires = lock.get("expires_at")
    if isinstance(expires, (int, float)) and time.time() > expires:
        return True
    pid = lock.get("pid")
    if isinstance(pid, int) and pid > 0 and not _pid_alive(pid):
        return True
    if project_dir is None:
        return False
    task_id = str(lock.get("task_id") or "")
    if not task_id:
        return True
    run = _read_run(project_dir, task_id)
    if run is not None:
        return run.get("status") not in ("queued", "running")
    live = _TASKS.get(project_dir.name)
    if live and live.task_id == task_id and live.status in ("queued", "running"):
        return False
    started = _parse_ts(lock.get("started_at"))
    if started <= 0:
        return True
    return (time.time() - started) > ORPHAN_LOCK_GRACE_SECONDS


def _reconcile_lock(project_dir: Path) -> None:
    """清掉过期/孤儿 .run.lock（prepare 后崩溃会留下 pid=0 且无 runs/*.json）。"""
    path = _lock_path(project_dir)
    existing = _read_json(path)
    if not existing or not _lock_is_stale(existing, project_dir):
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _acquire_lock(project_dir: Path, task: RunTask) -> None:
    _reconcile_lock(project_dir)
    path = _lock_path(project_dir)
    existing = _read_json(path)
    if existing and not _lock_is_stale(existing, project_dir):
        raise StageBusyError(
            f"该项目已有任务 {existing.get('task_id')} 在运行，请等待完成"
        )
    lock = {
        "task_id": task.task_id,
        "stage": task.stage,
        "pid": task.pid,
        "started_at": task.started_at,
        "expires_at": task.started_ts + task.timeout_seconds * 2,
        "runner": "web",
    }
    tmp = path.with_suffix(".lock.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2)
    os.replace(tmp, path)


def _release_lock(project_dir: Path, task_id: str) -> None:
    path = _lock_path(project_dir)
    existing = _read_json(path)
    if existing and existing.get("task_id") == task_id:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def _update_lock_pid(project_dir: Path, task: RunTask) -> None:
    """spawn 后把真实 pid 补进锁（供 stale 判定与并发检查）。"""
    path = _lock_path(project_dir)
    existing = _read_json(path)
    if existing and existing.get("task_id") == task.task_id:
        existing["pid"] = task.pid
        existing["expires_at"] = task.started_ts + task.timeout_seconds * 2
        tmp = path.with_suffix(".lock.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)
        os.replace(tmp, path)


# ---------------------------------------------------------------------------
# runs/ 状态文件（SSE 触发源——每次写都经 watchfiles → hub.publish）
# ---------------------------------------------------------------------------


def _write_run_state(task: RunTask, *, log_tail_chars: int = LOG_TAIL_CHARS) -> None:
    state = {
        "task_id": task.task_id,
        "project_id": task.project_id,
        "stage": task.stage,
        "status": task.status,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "exit_code": task.exit_code,
        "error": task.error,
        "pid": task.pid,
        "log_tail": _log_tail(task.log_path, log_tail_chars),
    }
    runs = _runs_dir(task.project_dir)
    runs.mkdir(parents=True, exist_ok=True)
    tmp = _run_state_path(task.project_dir, task.task_id).with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _run_state_path(task.project_dir, task.task_id))


# ---------------------------------------------------------------------------
# stream-json 渲染（NDJSON 事件流 → 人类可读日志行）
# ---------------------------------------------------------------------------


def _brief(value: Any, limit: int = 120) -> str:
    """把工具入参/结果压成单行摘要。"""
    if isinstance(value, list):  # tool_result 的 content 可能是 block 数组
        value = " ".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in value
        )
    if isinstance(value, dict):
        value = ", ".join(f"{k}={v}" for k, v in value.items())
    text = " ".join(str(value or "").split())
    return text[:limit] + ("…" if len(text) > limit else "")


_READ_LINE_PREFIX = re.compile(r"^\d+\t")


def _strip_read_line_numbers(text: str) -> str:
    """Read 工具返回 ``1\\tline\\n2\\tline`` — 展示前去掉行号前缀。"""
    lines = text.splitlines()
    if not lines:
        return text
    numbered = sum(1 for ln in lines if _READ_LINE_PREFIX.match(ln))
    if numbered < max(3, len(lines) // 2):
        return text
    out: list[str] = []
    for ln in lines:
        if _READ_LINE_PREFIX.match(ln):
            out.append(ln.split("\t", 1)[1] if "\t" in ln else ln)
        else:
            out.append(ln)
    return "\n".join(out)


def _format_tool_result(content: Any, *, char_limit: int = 6000, line_limit: int = 48) -> str:
    """tool_result → 可读正文（去 Read 行号、JSON 缩进、过长截断）。"""
    if isinstance(content, list):
        text = "\n".join(
            (b.get("text", "") if isinstance(b, dict) else str(b))
            for b in content
            if (isinstance(b, dict) and b.get("text")) or (not isinstance(b, dict) and b)
        )
    elif isinstance(content, dict):
        text = json.dumps(content, ensure_ascii=False, indent=2)
    else:
        text = str(content or "").strip()

    if not text:
        return "(empty)"

    text = _strip_read_line_numbers(text)
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            text = json.dumps(json.loads(stripped), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pass

    lines = text.splitlines()
    if len(lines) > line_limit:
        text = "\n".join(lines[:line_limit]) + f"\n… ({len(lines) - line_limit} more lines)"
    if len(text) > char_limit:
        text = text[:char_limit] + "\n…"
    return text


def _render_tool_result_lines(mark: str, body: str) -> list[str]:
    """单行摘要 vs 多行正文 — 后者缩进展示，避免行号与 JSON 挤成一行。"""
    if "\n" not in body and len(body) <= 160:
        return [f"  {mark} {body}"]
    out = [f"  {mark}"]
    out.extend(f"    {ln}" for ln in body.splitlines())
    return out


def _render_stream_event(obj: dict) -> Optional[str]:
    """单个 stream-json 事件 → 展示行（None = 不展示）。"""
    typ = obj.get("type")
    if typ == "system":
        if obj.get("subtype") == "init":
            return f"● 会话启动 · model={obj.get('model') or '?'}"
        return None
    if typ == "assistant":
        out = []
        for block in (obj.get("message") or {}).get("content") or []:
            kind = block.get("type")
            if kind == "text":
                text = (block.get("text") or "").strip()
                if text:
                    out.append(text)
            elif kind == "tool_use":
                out.append(f"▸ {block.get('name') or 'tool'}({_brief(block.get('input'))})")
        return "\n".join(out) or None
    if typ == "user":
        out: list[str] = []
        for block in (obj.get("message") or {}).get("content") or []:
            if block.get("type") == "tool_result":
                mark = "✗" if block.get("is_error") else "✓"
                body = _format_tool_result(block.get("content"))
                out.extend(_render_tool_result_lines(mark, body))
        return "\n".join(out) if out else None
    if typ == "result":
        head = [f"● 结束 · {obj.get('subtype') or ''}"]
        duration = obj.get("duration_ms")
        if isinstance(duration, (int, float)):
            head.append(f"{duration / 1000:.0f}s")
        cost = obj.get("total_cost_usd")
        if isinstance(cost, (int, float)):
            head.append(f"${cost:.4f}")
        result = (obj.get("result") or "").strip()
        line = " · ".join(head)
        return f"{line}\n{result}" if result else line
    return None


def render_run_log(raw: str) -> list[str]:
    """NDJSON 日志 → 展示行。非 JSON 行（CLI 报错、崩溃栈）原样保留——
    失败诊断恰恰依赖它们。"""
    lines: list[str] = []
    for raw_line in raw.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if not stripped.startswith("{"):
            lines.append(raw_line)
            continue
        try:
            event = json.loads(stripped)
        except json.JSONDecodeError:
            lines.append(raw_line)
            continue
        rendered = _render_stream_event(event) if isinstance(event, dict) else None
        if rendered:
            lines.extend(rendered.splitlines())
    return lines


def _log_tail(log_path: Path, chars: int) -> str:
    if not log_path.is_file():
        return ""
    try:
        # 按字节切尾会截断首行 JSON——丢掉它，避免半行事件混进展示。
        data = log_path.read_bytes()
        truncated = len(data) > chars
        text = data[-chars:].decode("utf-8", errors="replace")
        if truncated:
            text = text.split("\n", 1)[1] if "\n" in text else ""
        return "\n".join(render_run_log(text))
    except OSError:
        return ""


def _read_runs_from_disk(project_dir: Path, *, limit: int = 8) -> list[dict]:
    runs_dir = _runs_dir(project_dir)
    if not runs_dir.is_dir():
        return []
    entries = []
    for path in sorted(runs_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        state = _read_json(path)
        if state:
            entries.append(state)
        if len(entries) >= limit:
            break
    return entries


def _reconcile_orphan_runs(project_dir: Path) -> None:
    """磁盘上仍标 running/queued 但 pid 已死的 run —— 定终态并释放锁。

    否则 Flow 会一直显示「进行中」、重试按钮被 liveRun 挡住。
    """
    for state in _read_runs_from_disk(project_dir, limit=KEEP_RUNS):
        if state.get("status") not in ("queued", "running"):
            continue
        pid = state.get("pid")
        if isinstance(pid, int) and pid > 0 and _pid_alive(pid):
            continue
        task_id = state.get("task_id", "")
        task = _TASKS.get(project_dir.name)
        if task and task.task_id == task_id and task.status in ("queued", "running"):
            continue
        _finalize_reconciled(project_dir, state, interrupted=True)
        _patch_stuck_in_progress(
            RunTask(
                task_id=str(task_id),
                project_dir=project_dir,
                project_id=project_dir.name,
                stage=str(state.get("stage") or ""),
                pipeline_type="",
                status="aborted",
                error=state.get("error") or "agent 进程已退出（孤儿 run 回收）",
            )
        )


def _list_runs(project_dir: Path, *, limit: int = 8) -> list[dict]:
    _reconcile_orphan_runs(project_dir)
    return _read_runs_from_disk(project_dir, limit=limit)


def list_runs(project_dir: Path, *, limit: int = 8) -> list[dict]:
    """最近运行摘要（API 层使用）。"""
    return _list_runs(project_dir, limit=limit)


def read_run_log(project_dir: Path, task_id: str, *, offset: int = 0, limit: int = 200) -> dict:
    log_path = project_dir / RUNS_DIRNAME / f"{task_id}.log"
    if not log_path.is_file():
        raise StageRunError("日志文件不存在")
    raw = log_path.read_bytes().decode("utf-8", errors="replace")
    lines = render_run_log(raw)
    return {
        "offset": offset,
        "total": len(lines),
        "lines": lines[offset:offset + limit],
    }


def _cleanup_old_runs(project_dir: Path) -> None:
    runs_dir = _runs_dir(project_dir)
    if not runs_dir.is_dir():
        return
    keep: set[str] = set()
    for state in _list_runs(project_dir, limit=KEEP_RUNS):
        keep.add(state.get("task_id", ""))
    for path in runs_dir.iterdir():
        if path.suffix == ".json" and path.stem not in keep:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
            log = runs_dir / f"{path.stem}.log"
            try:
                log.unlink(missing_ok=True)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# 进程管理
# ---------------------------------------------------------------------------


async def _spawn_agent(cmd: list[str], *, cwd: Path, stdout, stderr) -> asyncio.subprocess.Process:
    """唯一 spawn 点（测试 seam）。Windows: DETACHED + 无窗口，孩子存活于
    server 重启（供 reconcile 接回）；POSIX: start_new_session。"""
    kwargs: dict[str, Any] = {
        "cwd": str(cwd),
        "stdout": stdout,
        "stderr": stderr,
        "stdin": asyncio.subprocess.PIPE,
        "env": _child_env(),
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        )
    else:
        kwargs["start_new_session"] = True
    return await asyncio.create_subprocess_exec(*cmd, **kwargs)


def _kill_process_tree(pid: int) -> None:
    """Windows taskkill /T /F（claude 是 node，有子进程树）；POSIX killpg。"""
    if pid <= 0:
        return
    try:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            import signal

            os.killpg(os.getpgid(pid), signal.SIGTERM)
    except (OSError, ProcessLookupError):
        pass


async def _heartbeat(task: RunTask) -> None:
    while task.status in ("queued", "running"):
        await asyncio.sleep(HEARTBEAT_SECONDS)
        if task.status in ("queued", "running"):
            _write_run_state(task)


async def _monitor(task: RunTask) -> None:
    deadline = task.started_ts + task.timeout_seconds
    while True:
        await asyncio.sleep(MONITOR_POLL_SECONDS)
        if task.status not in ("queued", "running"):
            return
        if time.time() > deadline:
            task.requested_status = "timed_out"
            task.error = (
                f"超时（{task.timeout_seconds / 60:.0f} 分钟墙钟上限），已终止"
            )
            if task.pid:
                _kill_process_tree(task.pid)
            return


# ---------------------------------------------------------------------------
# 运行生命周期
# ---------------------------------------------------------------------------


def prepare_stage_run(
    project_dir: Path,
    *,
    stage: Optional[str] = None,
    parameters: Optional[dict] = None,
    feedback: Optional[str] = None,
) -> RunTask:
    """同步校验 + 加锁 + 组装 prompt + 注册任务（不 spawn）。

    校验顺序（契约）：manifest 加载 → stage == get_next_stage（同时覆盖
    首次运行与驳回/失败重跑）→ 加锁（409）→ 组装 prompt。
    """
    from lib.checkpoint import get_next_stage, read_checkpoint
    from lib.pipeline_loader import get_stage_order, load_pipeline_readonly

    project_id = project_dir.name
    marker = _read_json(project_dir / "project.json") or {}
    pipeline_type = marker.get("pipeline_type")
    if not pipeline_type:
        raise StageRunError("项目缺少 pipeline_type（project.json 未初始化）")

    try:
        manifest = load_pipeline_readonly(pipeline_type)
    except FileNotFoundError as exc:
        raise StageRunError(f"未知流水线 {pipeline_type!r}——manifest 不存在") from exc

    stages = get_stage_order(manifest)
    next_stage = get_next_stage(PROJECTS_DIR, project_id, pipeline_type)
    target = stage or next_stage
    if target is None:
        raise StageRunError("流水线已完结，没有可运行的阶段")
    if target not in stages:
        raise StageRunError(f"阶段 {target!r} 不在流水线 {pipeline_type!r} 中")
    if target != next_stage:
        raise StageRunError(
            f"只能运行 {next_stage!r}（get_next_stage 指向的阶段）——当前是 {target!r}"
        )

    awaiting = _awaiting_human_stage(project_dir, pipeline_type)
    if awaiting:
        raise StageRunError(
            f"阶段 {awaiting!r} 待审批，请先批准或驳回后再继续"
        )

    # 驳回后重跑：反馈落在 checkpoint 的 metadata.revision_request 上。调用方
    # 没显式带 feedback 时必须从那里捞回来——否则 agent 拿不到修改意见，
    # 驳回就成了空转（页面「运行下一阶段」按钮正是这条路径）。
    if feedback is None:
        prior = read_checkpoint(PROJECTS_DIR, project_id, target)
        if prior:
            feedback = (prior.get("metadata") or {}).get("revision_request") or None

    task = RunTask(
        task_id=uuid.uuid4().hex[:12],
        project_dir=project_dir,
        project_id=project_id,
        stage=target,
        pipeline_type=pipeline_type,
    )
    orchestration = manifest.get("orchestration") or {}
    wall_minutes = int(orchestration.get("max_wall_time_minutes") or DEFAULT_WALL_TIME_MINUTES)
    task.timeout_seconds = max(wall_minutes, MIN_WALL_TIME_MINUTES) * 60
    task.budget_usd = float(orchestration.get("budget_default_usd") or DEFAULT_BUDGET_USD)

    # 锁携带 pid —— spawn 前 pid 未知，先占位 0，spawn 后补写。
    task.pid = 0
    _acquire_lock(project_dir, task)
    try:
        task.prompt = build_stage_prompt(
            project_dir,
            target,
            manifest=manifest,
            wall_time_minutes=wall_minutes,
            budget_usd=task.budget_usd,
            feedback=feedback,
            parameters=parameters,
        )
    except Exception:
        _release_lock(project_dir, task.task_id)
        raise

    _TASKS[project_id] = task
    return task


async def run_task(task: RunTask, *, chain: bool = True) -> None:
    """核心协程：spawn → stdin 送 prompt → 等退出 → 定终态。"""
    runs = _runs_dir(task.project_dir)
    runs.mkdir(parents=True, exist_ok=True)
    log_fh = open(task.log_path, "wb", buffering=0)  # 二进制句柄，防混编码
    succeeded = False
    try:
        cmd = [*_resolve_claude_cmd(), *_build_cli_args(task.budget_usd)]
        task.proc = await _spawn_agent(cmd, cwd=REPO_ROOT, stdout=log_fh, stderr=log_fh)
        task.pid = task.proc.pid
        # 锁补写真实 pid（供 stale 判定与并发检查）。
        _update_lock_pid(task.project_dir, task)
        task.status = "running"
        _write_run_state(task)
        task.monitor_task = asyncio.create_task(_monitor(task))
        task.heartbeat_task = asyncio.create_task(_heartbeat(task))

        await task.proc.communicate(input=task.prompt.encode("utf-8"))
        task.exit_code = task.proc.returncode
        if task.requested_status == "aborted":
            _finalize(task, "aborted")
        elif task.requested_status == "timed_out":
            _finalize(task, "failed")
        elif task.exit_code == 0:
            _finalize(task, "succeeded")
            succeeded = True
        else:
            task.error = f"agent 退出码 {task.exit_code}"
            _finalize(task, "failed")
    except asyncio.CancelledError:
        if task.pid:
            _kill_process_tree(task.pid)
        _finalize(task, "aborted")
        raise
    except Exception as exc:
        task.error = f"启动失败: {exc}"
        _finalize(task, "failed")
    finally:
        for bg in (task.monitor_task, task.heartbeat_task):
            if bg and not bg.done():
                bg.cancel()
        try:
            log_fh.close()
        except OSError:
            pass
    if chain and succeeded:
        await auto_advance_chain(task.project_dir, from_stage=task.stage)


def _finalize(task: RunTask, status: str) -> None:
    task.status = status
    task.finished_at = _now_iso()
    if status in ("failed", "aborted"):
        # agent 已留下 in_progress checkpoint 时补写 failed，避免 rail 永续
        # "进行中"（cancel/超时/服务重启专用；正常失败由 agent 自己写）。
        _patch_stuck_in_progress(task)
    _write_run_state(task)
    _release_lock(task.project_dir, task.task_id)
    _TASKS.pop(task.project_id, None)
    _cleanup_old_runs(task.project_dir)


def _stage_requires_human_gate(manifest: dict, stage_name: str) -> bool:
    from lib.pipeline_loader import get_stage_human_approval_default

    gate = get_stage_human_approval_default(manifest, stage_name)
    return bool(gate) if gate is not None else False


def _awaiting_human_stage(project_dir: Path, pipeline_type: str) -> Optional[str]:
    """Return a stage name blocked on human approval, if any."""
    from lib.checkpoint import read_checkpoint, get_pipeline_stages

    project_id = project_dir.name
    for stage in get_pipeline_stages(pipeline_type):
        cp = read_checkpoint(PROJECTS_DIR, project_id, stage)
        if cp and cp.get("status") == "awaiting_human":
            return stage
    return None


def maybe_auto_advance(
    project_dir: Path,
    *,
    completed_stage: str,
) -> Optional[RunTask]:
    """上一阶段已完成（gated 阶段须已批准）→ 自动排队运行下一阶段。

    ``human_approval_default`` 只表示该阶段**完成后**需人工审批，
    不阻止从上游自动启动；gated 阶段跑完后会停在 awaiting_human。
    """
    from lib.checkpoint import get_next_stage, read_checkpoint
    from lib.pipeline_loader import load_pipeline_readonly

    project_id = project_dir.name
    busy = _busy_or_none(project_dir)
    if busy:
        return None

    cp = read_checkpoint(PROJECTS_DIR, project_id, completed_stage)
    if not cp or cp.get("status") != "completed":
        return None

    pipeline_type = cp.get("pipeline_type")
    if not pipeline_type:
        return None

    if _awaiting_human_stage(project_dir, pipeline_type):
        return None

    try:
        manifest = load_pipeline_readonly(pipeline_type)
    except Exception:
        return None

    if _stage_requires_human_gate(manifest, completed_stage) and not cp.get("human_approved"):
        return None

    next_stage = get_next_stage(PROJECTS_DIR, project_id, pipeline_type)
    if not next_stage:
        return None

    try:
        return prepare_stage_run(project_dir, stage=next_stage)
    except (StageRunError, StageBusyError):
        return None


async def auto_advance_chain(project_dir: Path, *, from_stage: str) -> None:
    """连续运行所有无需人工审批的后续阶段（直到 gated 阶段或失败）。"""
    completed = from_stage
    while True:
        next_task = await asyncio.to_thread(
            maybe_auto_advance, project_dir, completed_stage=completed,
        )
        if not next_task:
            break
        await run_task(next_task, chain=False)
        if next_task.status != "succeeded":
            break
        completed = next_task.stage


def _patch_stuck_in_progress(task: RunTask) -> None:
    """cancel/超时/服务重启时：若 agent 已写该阶段 in_progress checkpoint
    且无更新状态，补写 failed（保留 artifacts，rail 显示失败而非永续进行中）。"""
    from lib.checkpoint import read_checkpoint, write_checkpoint

    cp = read_checkpoint(PROJECTS_DIR, task.project_id, task.stage)
    if not cp or cp.get("status") != "in_progress":
        return
    try:
        write_checkpoint(
            PROJECTS_DIR,
            task.project_id,
            task.stage,
            "failed",
            artifacts=cp.get("artifacts") or {},
            pipeline_type=task.pipeline_type,
            checkpoint_policy=cp.get("checkpoint_policy", "guided"),
            error=task.error or f"运行被 {task.status}",
            metadata={**(cp.get("metadata") or {}), "runner_aborted": task.status},
        )
    except Exception:
        pass  # 尽力而为——checkpoint 契约写失败不该阻断 run 终态上报


# ---------------------------------------------------------------------------
# 取消 / 服务重启恢复
# ---------------------------------------------------------------------------


def cancel_run(project_dir: Path, task_id: str) -> dict:
    project_id = project_dir.name
    task = _TASKS.get(project_id)
    if task and task.task_id == task_id and task.status in ("queued", "running"):
        task.requested_status = "aborted"
        task.error = "用户在 Backlot 页面取消"
        if task.pid:
            _kill_process_tree(task.pid)
        _finalize(task, "aborted")
        return {"ok": True, "task_id": task_id, "status": "aborted"}
    # 非内存态任务（服务重启后）：直接按 pid 杀 + 标状态。
    state = _read_run(project_dir, task_id)
    if not state:
        raise StageRunError("未知任务")
    if state.get("status") not in ("queued", "running"):
        return {"ok": False, "task_id": task_id, "status": state.get("status")}
    pid = state.get("pid")
    if isinstance(pid, int) and pid > 0:
        _kill_process_tree(pid)
    state["status"] = "aborted"
    state["finished_at"] = _now_iso()
    state["error"] = "用户在 Backlot 页面取消（服务重启后补记）"
    _write_state_dict(project_dir, state)
    _release_lock(project_dir, task_id)
    return {"ok": True, "task_id": task_id, "status": "aborted"}


def _read_run(project_dir: Path, task_id: str) -> Optional[dict]:
    return _read_json(_run_state_path(project_dir, task_id))


def _write_state_dict(project_dir: Path, state: dict) -> None:
    path = _run_state_path(project_dir, state.get("task_id", ""))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


async def reconcile_runs() -> None:
    """服务启动时接回运行中的无头任务（DETACHED 子进程在 server 重启后存活）。

    - pid 已死 → 依据 checkpoint 终态定 succeeded/failed，否则 failed(中断)。
    - pid 存活 → 重建监控：完成判定 = 日志停滞 + checkpoint 终态；
      超时看门狗 = 原 deadline 失效后按剩余时间放宽 5 分钟。
    """
    if not PROJECTS_DIR.is_dir():
        return
    for project_dir in sorted(PROJECTS_DIR.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith(("_", ".")):
            continue
        _reconcile_lock(project_dir)
        for state in _list_runs(project_dir, limit=KEEP_RUNS):
            if state.get("status") not in ("queued", "running"):
                continue
            task_id = state.get("task_id", "")
            pid = state.get("pid")
            if not isinstance(pid, int) or pid <= 0 or not _pid_alive(pid):
                _finalize_reconciled(project_dir, state, interrupted=True)
                continue
            task = RunTask(
                task_id=task_id,
                project_dir=project_dir,
                project_id=project_dir.name,
                stage=state.get("stage", ""),
                pipeline_type=state.get("pipeline_type", ""),
                status="running",
            )
            task.pid = pid
            task.started_at = state.get("started_at", task.started_at)
            # 已跑时长计入墙钟，但服务停机时长不算——clamp 到 timeout 内，
            # 保证重启后至少还留足剩余时间。
            elapsed = max(0.0, time.time() - _parse_ts(state.get("started_at")))
            task.started_ts = time.time() - min(elapsed, task.timeout_seconds)
            _TASKS[project_dir.name] = task
            asyncio.create_task(_reconcile_watch(task))


def _parse_ts(iso: Any) -> float:
    if not isinstance(iso, str):
        return time.time()
    try:
        from datetime import datetime as dt

        parsed = dt.fromisoformat(iso.replace("Z", "+00:00"))
        return parsed.timestamp()
    except ValueError:
        return time.time()


def _finalize_reconciled(project_dir: Path, state: dict, *, interrupted: bool) -> None:
    from lib.checkpoint import read_checkpoint

    cp = read_checkpoint(PROJECTS_DIR, project_dir.name, state.get("stage", ""))
    if cp and cp.get("status") in ("completed", "awaiting_human", "failed"):
        state["status"] = "succeeded"
        state["error"] = None
    elif interrupted:
        state["status"] = "failed"
        state["error"] = "服务重启导致进程状态丢失（任务中断）"
    else:
        state["status"] = "failed"
        state["error"] = "agent 未写入终态 checkpoint"
    state["finished_at"] = _now_iso()
    _write_state_dict(project_dir, state)
    _release_lock(project_dir, state.get("task_id", ""))


async def _reconcile_watch(task: RunTask) -> None:
    """重启后监控：log 停滞 + checkpoint 终态 → 定终态；超时看门狗。"""
    last_size = task.log_path.stat().st_size if task.log_path.is_file() else 0
    stagnant_since: Optional[float] = None
    deadline = task.started_ts + task.timeout_seconds + 300
    while True:
        await asyncio.sleep(MONITOR_POLL_SECONDS)
        if task.status != "running":
            return
        if time.time() > deadline:
            _kill_process_tree(task.pid or 0)
            _finalize_reconciled(task.project_dir, _read_run(task.project_dir, task.task_id) or {}, interrupted=True)
            _TASKS.pop(task.project_id, None)
            return
        if not task.log_path.is_file():
            continue
        size = task.log_path.stat().st_size
        if size != last_size:
            last_size = size
            stagnant_since = None
            continue
        if stagnant_since is None:
            stagnant_since = time.time()
        elif time.time() - stagnant_since > RECONCILE_STAGNANT_SECONDS:
            from lib.checkpoint import read_checkpoint

            cp = read_checkpoint(PROJECTS_DIR, task.project_id, task.stage)
            if cp and cp.get("status") in ("completed", "awaiting_human", "failed"):
                _finalize_reconciled(task.project_dir, _read_run(task.project_dir, task.task_id) or {}, interrupted=False)
                _TASKS.pop(task.project_id, None)
                return


# ---------------------------------------------------------------------------
# prompt 组装（纯函数，可单测）
# ---------------------------------------------------------------------------


def build_stage_prompt(
    project_dir: Path,
    stage: str,
    *,
    manifest: dict,
    wall_time_minutes: int,
    budget_usd: float,
    feedback: Optional[str] = None,
    parameters: Optional[dict] = None,
) -> str:
    """组装无头 agent 的完整 prompt：粘贴 director skill 全文 + 项目状态
    JSON + manifest 本阶段定义 + 前置 artifacts 清单 + 驳回反馈。"""
    from lib.pipeline_loader import (
        get_stage_human_approval_default,
        resolve_stage_skill_file,
    )

    project_id = project_dir.name
    marker = _read_json(project_dir / "project.json") or {}
    pipeline_type = marker.get("pipeline_type", "")
    title = marker.get("title", project_id)

    skill_path = resolve_stage_skill_file(manifest, stage) or ""
    skill_text = ""
    if skill_path:
        skill_file = REPO_ROOT / skill_path
        if skill_file.is_file():
            skill_text = skill_file.read_text(encoding="utf-8")
        else:
            # 不要沉默：prompt 声称"全文已粘贴"，贴空块会让 agent 自己去
            # Grep/Read 翻技能，白烧若干轮。说清楚它得自己读。
            skill_text = (
                f"（技能文件未找到：{skill_path} —— 请先用 Read 打开该路径，"
                f"找不到再用 Glob 在 skills/ 下搜索同名文件）"
            )

    gated = bool(get_stage_human_approval_default(manifest, stage))
    stage_block = next(
        (s for s in (manifest.get("stages") or []) if s.get("name") == stage),
        {},
    )

    # 前置 artifacts：project_status 提供 completed stages 的 artifact 清单。
    try:
        from lib.project_status import build_project_status

        status = build_project_status(project_id, projects_dir=PROJECTS_DIR)
    except Exception:
        status = {}
    artifact_paths = []
    for st in status.get("stages") or []:
        if st.get("status") == "completed":
            artifact = st.get("canonical_artifact")
            if artifact and st.get("artifact_exists"):
                artifact_paths.append(f"projects/{project_id}/artifacts/{artifact}.json")
    artifact_list = "\n".join(f"  - {p}" for p in artifact_paths) or "  （无）"

    feedback_text = f"\n{feedback}\n" if feedback else "（无）"
    parameters_text = json.dumps(parameters or {}, ensure_ascii=False)

    from lib.python_runtime import python_invocation_hint

    om_python = python_invocation_hint()

    return f"""【角色】你是 OpenMontage 的无头流水线 agent，执行且只执行一个阶段。
项目: {project_id} 「{title}」  流水线: {pipeline_type}
本次阶段: {stage}（页面「运行下一阶段」触发）

【与交互式 agent 的差异 — 必须遵守】
- 没有交互式用户。绝不要提问、绝不等待输入、绝不调用需要人类回答的流程。
  一切自主决策。你唯一的人类交互是写 checkpoint。
- 若关键资源不可用（API key 缺失、工具不可用、素材缺失）：不要空转，
  写 status='failed' 的 checkpoint，error 说明原因，然后结束。
- 只做这一个阶段。绝不串联多个阶段、绝不改写其他阶段的 checkpoint。
- 结束时输出一行便于服务端定位: agent_run_summary: <status> — <一句话>

【Python 运行时 — 强制】
所有 registry 工具调用必须使用仓库解释器，禁止用 Cursor/宿主默认 python：
  {om_python} -c "..."
preflight 示例：
  {om_python} -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"
若 video_selector 显示 unavailable 但本机已装 diffusers，先检查是否误用了其它 venv 的 python。

【必读材料】
1. 阶段导演技能（本阶段唯一执行规程，全文已粘贴）:
   {skill_path}
   --- 技能全文开始 ---
   {skill_text}
   --- 技能全文结束 ---
2. 项目状态（lib.project_status；get_next_stage 必须等于 {stage}）:
   {json.dumps(status, ensure_ascii=False, indent=1)[:12000]}
3. 流水线 manifest 中本阶段定义:
   {json.dumps(stage_block, ensure_ascii=False, indent=1)[:6000]}
4. 前置 artifacts（仓库相对路径，优先用 Read 读取）:
   {artifact_list}
5. 上次审阅反馈（页面驳回时产生，必须逐条回应）:
   {feedback_text}
6. 用户附加参数:
   {parameters_text}

【执行规程（强制）】
1. 进入阶段先写 in_progress checkpoint（lib.checkpoint.write_checkpoint，
   pipeline_dir=lib.paths.PROJECTS_DIR, pipeline_type='{pipeline_type}',
   status='in_progress', artifacts={{}}，可带 metadata.partial_progress）。
2. 用注册表工具执行（``registry.execute(name, {{...}})`` 或 ``registry.get(name).execute(...)`` 的 {om_python} -c 单行调用，
   符合 AGENT_GUIDE「Allowed python -c」）。工具调用自动写入 events.jsonl。
   禁止写脚本串联、禁止直接编辑 projects/ 下的 checkpoint/artifacts/decision_log。
3. 完成后:
   - 本阶段 human_approval_default: {gated}
   - gated: 写 status='awaiting_human'，带齐规范 artifact，human_approved 保持
     False，决策以 user_approved=false 追加，然后停止（END YOUR TURN）——
     人类在 Backlot 页面批准或驳回。
   - 非 gated: 写 status='completed'。
   - 永远不要对 gated 阶段写 completed + human_approved=False（checkpoint 库
     会拒绝，GATE VIOLATION）。
4. 任何失败: 写 status='failed' + error（≤400 字符，简述原因），不要留下 in_progress。
5. 时间预算 {wall_time_minutes} 分钟（服务端到点强杀）；成本预算 ${budget_usd}。
   稳步推进，频繁 checkpoint。
"""


# ---------------------------------------------------------------------------
# 页面审批（纯 lib 调用——与 nle_edit.apply_draft 同构的受管控写路径）
# ---------------------------------------------------------------------------


def _busy_or_none(project_dir: Path) -> Optional[str]:
    _reconcile_orphan_runs(project_dir)
    task = _TASKS.get(project_dir.name)
    if task and task.status in ("queued", "running"):
        pid = task.pid if isinstance(task.pid, int) else 0
        if pid > 0 and not _pid_alive(pid):
            # 内存里仍标 running 但子进程已死 —— 视为孤儿，勿阻塞批准/驳回。
            _TASKS.pop(project_dir.name, None)
            _reconcile_lock(project_dir)
        else:
            return f"该项目已有任务 {task.task_id} 在运行，请等待完成"
    # 磁盘上的 running 状态（服务重启后 reconcile 尚未接回/标记）同样视为 busy。
    for state in _list_runs(project_dir, limit=KEEP_RUNS):
        if state.get("status") not in ("queued", "running"):
            continue
        pid = state.get("pid")
        if isinstance(pid, int) and pid > 0 and not _pid_alive(pid):
            _finalize_reconciled(project_dir, state, interrupted=True)
            continue
        return "该项目已有任务在运行（服务重启后恢复中），请等待完成"
    return None


def approve_stage(project_dir: Path, stage: str, *, notes: str = "") -> dict:
    """页面批准：awaiting_human → completed + human_approved=True（保留
    artifacts）+ 镜像追加同 (category, subject) 的 user_approved=true 决策
    —— 唯一 audit 干净的页面批准路径（approval_gate_drift 要求）。"""
    from lib.checkpoint import get_next_stage, read_checkpoint, write_checkpoint
    from lib.decision_log import append_decisions

    project_id = project_dir.name
    busy = _busy_or_none(project_dir)
    if busy:
        raise StageBusyError(busy)

    cp = read_checkpoint(PROJECTS_DIR, project_id, stage)
    if not cp or cp.get("status") != "awaiting_human":
        raise StageRunError(f"阶段 {stage!r} 不在等待批准状态（awaiting_human）")

    # 顺序是契约的一部分：**先**追加决策再写 checkpoint。反过来（先 completed +
    # human_approved=True，再追加）一旦追加失败，就恰好留下
    # approval_gate_drift 要抓的那种状态——阶段标着"人已批准"而决策仍是
    # user_approved=false，且无人知晓。反向失败只是"日志记了、阶段还挂着
    # awaiting"，板面照实显示，用户重按一次即自愈。
    to_append, skipped = _approval_mirror(project_dir, stage, notes)
    append_decisions(project_id, to_append)

    write_checkpoint(
        PROJECTS_DIR,
        project_id,
        stage,
        "completed",
        artifacts=cp.get("artifacts") or {},
        pipeline_type=cp.get("pipeline_type"),
        checkpoint_policy=cp.get("checkpoint_policy", "guided"),
        human_approved=True,  # 页面批准 = 真实人类确认（与 NLE apply 同构）
        metadata={**(cp.get("metadata") or {}), "approved_via": "backlot-web"},
    )

    next_stage = get_next_stage(PROJECTS_DIR, project_id, cp.get("pipeline_type"))
    result = {"ok": True, "stage": stage, "status": "completed", "next_stage": next_stage}
    if skipped:
        # 不静默：镜像不了的决策仍会让 audit 报 drift，调用方必须知道。
        result["unmirrored_decisions"] = skipped
    return result


def _approval_mirror(project_dir: Path, stage: str, notes: str) -> tuple[list[dict], list[str]]:
    """构造批准的镜像决策：该阶段每条 user_visible 且未批准的最新决策，
    按**同 (category, subject)** 追加一条 user_approved=true —— 这是
    ``approval_gate_drift`` 认可的唯一清账方式。

    返回 (待追加, 无法镜像的决策描述)。
    """
    from lib.decision_log import (
        latest_decisions_for_stage,
        load_decision_log,
        suggest_next_decision_id,
    )
    from schemas.artifacts import validate_artifact

    project_id = project_dir.name
    log = load_decision_log(project_dir)
    pending = latest_decisions_for_stage(log.get("decisions", []), stage)

    # suggest_next_decision_id 从磁盘算，循环里反复调会给每条同一个 id
    # （随后被 append_decisions 静默去重 → 只落一条）。取一次基号后自增。
    base = suggest_next_decision_id(project_dir, prefix="wa")
    start = int(base.rsplit("-", 1)[1])

    to_append: list[dict] = []
    skipped: list[str] = []
    reason = notes or "用户在 Backlot 页面批准该阶段"
    default_options = [
        {
            "option_id": "approved",
            "label": "批准",
            "score": 1,
            "reason": "用户在 Backlot 页面批准该阶段",
        },
    ]

    for d in pending:
        if not d.get("user_visible") or d.get("user_approved"):
            continue
        entry = {
            "decision_id": f"wa-{start + len(to_append):03d}",
            "stage": stage,
            "category": d.get("category", "unknown"),
            "subject": d.get("subject", f"{stage} decision"),
            "options_considered": d.get("options_considered") or default_options,
            "selected": d.get("selected") or "approved",
            "reason": reason,
            "user_visible": True,
            "user_approved": True,
        }
        try:
            validate_artifact("decision_log", {
                "version": "1.0", "project_id": project_id, "decisions": [entry],
            })
        except Exception as exc:
            # 源决策本身不合 schema（例如经 checkpoint 内嵌 decision_log 旁路
            # 写入的自造 category）。整单批准不该因此 500 —— 跳过并上报。
            skipped.append(f"{d.get('decision_id')}({d.get('category')}): {str(exc)[:80]}")
            continue
        to_append.append(entry)

    if not to_append:
        to_append.append({
            "decision_id": f"wa-{start:03d}",
            "stage": stage,
            "category": "human_approval",
            "subject": f"{stage} approval",
            "options_considered": default_options,
            "selected": "approved",
            "reason": reason,
            "user_visible": True,
            "user_approved": True,
        })
    return to_append, skipped


def _revision_count(project_dir: Path, stage: str) -> int:
    from lib.decision_log import load_decision_log

    log = load_decision_log(project_dir)
    return sum(
        1
        for d in log.get("decisions", [])
        if d.get("category") == "human_rejection" and d.get("stage") == stage
    )


def reject_stage(project_dir: Path, stage: str, *, feedback: str) -> dict:
    """页面驳回：追加 human_rejection 决策（隔离 category，不污染 drift 检查）
    + checkpoint 重写 in_progress（保留 artifacts，rail 显示 active 而非
    丢失产物）+ metadata 记录反馈。重跑仍走 stage == get_next_stage 同一条路。"""
    from lib.checkpoint import get_next_stage, read_checkpoint, write_checkpoint
    from lib.decision_log import append_decisions, suggest_next_decision_id
    from lib.pipeline_loader import load_pipeline_readonly

    project_id = project_dir.name
    busy = _busy_or_none(project_dir)
    if busy:
        raise StageBusyError(busy)

    cp = read_checkpoint(PROJECTS_DIR, project_id, stage)
    if not cp or cp.get("status") != "awaiting_human":
        raise StageRunError(f"阶段 {stage!r} 不在等待批准状态（awaiting_human）")

    pipeline_type = cp.get("pipeline_type") or ""
    limit = REVISION_LIMIT_DEFAULT
    try:
        manifest = load_pipeline_readonly(pipeline_type)
        limit = int(
            (manifest.get("orchestration") or {}).get("max_revisions_per_stage")
            or REVISION_LIMIT_DEFAULT
        )
    except Exception:
        pass
    count = _revision_count(project_dir, stage)
    if count >= limit:
        raise RevisionLimitError(
            f"已驳回 {count} 次，达到本流水线上限（{limit}）——请与 agent 在聊天中处理"
        )

    append_decisions(project_id, [{
        "decision_id": suggest_next_decision_id(project_dir, prefix="wr"),
        "stage": stage,
        "category": "human_rejection",
        "subject": f"{stage} 驳回",
        "options_considered": [
            {
                "option_id": "revision",
                "label": "要求修改并重跑",
                "score": 1,
                "reason": "用户在 Backlot 页面驳回该阶段",
            },
        ],
        "selected": "revision",
        "reason": feedback,
        "user_visible": True,
        # 驳回是**用户亲手做的决定**，user_approved=true 才是准确的：该字段
        # 记的是"人类是否签了这条"。写 false 会让它在重跑+批准后仍算一条
        # 未批准的当前决策，gated 阶段就此永久 approval_gate_drift。
        "user_approved": True,
    }])

    write_checkpoint(
        PROJECTS_DIR,
        project_id,
        stage,
        "in_progress",
        artifacts=cp.get("artifacts") or {},  # 保留产物供板面展示
        pipeline_type=pipeline_type,
        checkpoint_policy=cp.get("checkpoint_policy", "guided"),
        metadata={
            **(cp.get("metadata") or {}),
            "revision_request": feedback,
            "revision_count": count + 1,
        },
    )

    next_stage = get_next_stage(PROJECTS_DIR, project_id, pipeline_type)
    return {
        "ok": True,
        "stage": stage,
        "status": "in_progress",
        "revision_count": count + 1,
        "next_stage": next_stage,
    }


def run_state_for_board(project_dir: Path) -> list[dict]:
    """BoardState 注入：最新运行摘要（含 log_tail 供 UI 预览）。"""
    _reconcile_lock(project_dir)
    runs = [
        {
            "task_id": r["task_id"],
            "stage": r["stage"],
            "status": r["status"],
            "started_at": r["started_at"],
            "finished_at": r.get("finished_at"),
            "exit_code": r.get("exit_code"),
            "error": r.get("error"),
            "log_tail": (r.get("log_tail") or "")[-500:],
        }
        for r in _list_runs(project_dir, limit=5)
    ]
    lock = _read_json(_lock_path(project_dir))
    if lock and not _lock_is_stale(lock, project_dir):
        task_id = str(lock.get("task_id") or "")
        active = next(
            (r for r in runs if r["task_id"] == task_id and r["status"] in ("queued", "running")),
            None,
        )
        if task_id and not active:
            log_path = project_dir / RUNS_DIRNAME / f"{task_id}.log"
            runs.insert(0, {
                "task_id": task_id,
                "stage": lock.get("stage"),
                "status": "running",
                "started_at": lock.get("started_at"),
                "finished_at": None,
                "exit_code": None,
                "error": None,
                "log_tail": _log_tail(log_path, 500) if log_path.is_file() else "",
            })
    return runs[:5]
