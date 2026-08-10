"""Stage runner — headless-agent stage execution + page-driven approval for Backlot.

页面驱动通道：``POST /api/project/{id}/stage/run`` 在 hub 进程内构造 Hermes
``AIAgent``，于工作线程调用 ``run_conversation`` 执行**单一** pipeline 阶段。
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
import logging
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from plugins.openmontage.lib.paths import CODE_ROOT, PROJECTS_DIR
from plugins.openmontage.backlot.agent_executor import execute_stage_agent

# Backlot had no logging at all: a rejected run or a halted auto-advance left
# nothing on disk, so "the board just stopped" was unattributable after the fact.
log = logging.getLogger("backlot.stage")

# Dedicated loop for om_run / sync callers when no asyncio loop is running (CLI).
_bg_loop: Optional[asyncio.AbstractEventLoop] = None
_bg_thread: Optional[threading.Thread] = None
_bg_lock = threading.Lock()

RUNS_DIRNAME = "runs"
LOCK_FILENAME = ".run.lock"
RUN_STATUSES = ("queued", "running", "succeeded", "failed", "aborted")
KEEP_RUNS = 20
HEARTBEAT_SECONDS = 25
MONITOR_POLL_SECONDS = 5
# prepare 加锁 → run_task 写出 runs/*.json 之间的窗口；超出视为孤儿锁。
ORPHAN_LOCK_GRACE_SECONDS = 45
DEFAULT_WALL_TIME_MINUTES = 30
MIN_WALL_TIME_MINUTES = 10
DEFAULT_BUDGET_USD = 5  # advisory only (prompt guidance); no CLI budget kill
REVISION_LIMIT_DEFAULT = 3
# 尾巴按**原始 NDJSON 字节**切——一个事件动辄数百字节，取得太小渲染后
# 只剩一两行，板面预览就没信息量了。
LOG_TAIL_CHARS = 8000


class StageRunError(Exception):
    """Bad request (400) — stage order violation, missing checkpoint, etc."""

    status = 400

    def __init__(self, message: str, *, diagnostics: Optional[dict] = None):
        super().__init__(message)
        self.diagnostics = diagnostics or {}


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
    # 取消/超时由外部设置（cancel_run / _monitor），execute_stage_agent
    # 返回后据此定终态。
    requested_status: Optional[str] = None
    agent: Any = None  # live Hermes AIAgent (in-process)
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
# In-process agent helpers (Claude CLI spawn removed — see agent_executor.py)
# ---------------------------------------------------------------------------


def _interrupt_agent(task: "RunTask", reason: str = "") -> None:
    """Ask the live AIAgent to stop; no subprocess kill."""
    agent = task.agent
    if agent is None:
        return
    try:
        agent.interrupt(reason or None)
    except Exception as exc:
        log.debug("agent.interrupt failed: %s", exc)


# ---------------------------------------------------------------------------
# 锁（server 侧行为，不进 lib/checkpoint.py——交互式 agent 通道零改动）
# ---------------------------------------------------------------------------


def _pid_alive(pid: int) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        import psutil  # type: ignore

        return bool(psutil.pid_exists(pid))
    except ImportError:
        pass
    if os.name == "nt":
        try:
            import ctypes

            # Prefer OpenProcess — ``tasklist`` text matching ``f"PID {pid}"``
            # is brittle across locales and previously false-positived.
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            handle = ctypes.windll.kernel32.OpenProcess(
                PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid),
            )
            if handle:
                ctypes.windll.kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            pass
        try:
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            text = (out.stdout or b"").decode("utf-8", errors="replace").strip()
            if not text or text.upper().startswith("INFO:"):
                return False
            for row in text.splitlines():
                cols = [c.strip().strip('"') for c in row.split(",")]
                if len(cols) >= 2 and cols[1] == str(pid):
                    return True
            return False
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
        report = inspect_project_runtime(project_dir, reconcile=False)
        raise StageBusyError(
            f"该项目已有任务 {existing.get('task_id')} 在运行，请等待完成",
            diagnostics=report,
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
    """agent 启动后把 hub pid 补进锁（供 stale 判定与并发检查）。"""
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
        if obj.get("subtype") == "approval":
            desc = obj.get("description") or "dangerous tool"
            return f"● 自动批准 · {desc}"
        if obj.get("subtype") == "tool_action":
            mark = "✓" if obj.get("ok") else "✗"
            summary = obj.get("summary") or obj.get("tool") or "tool"
            label = obj.get("label")
            extra = f" · {label}" if label else ""
            return f"{mark} {summary}{extra}"
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
        try:
            pid_i = int(pid) if pid is not None else 0
        except (TypeError, ValueError):
            pid_i = 0
        if pid_i > 0 and _pid_alive(pid_i):
            continue
        task_id = state.get("task_id", "")
        task = _TASKS.get(project_dir.name)
        # 内存里还挂着同 task，但 pid 已死 → 清掉内存占位，继续回收磁盘。
        if task and task.task_id == task_id and task.status in ("queued", "running"):
            if pid_i > 0 and _pid_alive(pid_i):
                continue
            _TASKS.pop(project_dir.name, None)
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
    _reconcile_work_done_runs(project_dir)
    return _read_runs_from_disk(project_dir, limit=limit)


def list_runs(project_dir: Path, *, limit: int = 8) -> list[dict]:
    """最近运行摘要（API 层使用）。"""
    return _list_runs(project_dir, limit=limit)


def _stage_disk_truth(project_dir: Path, stage: str) -> dict[str, Any]:
    """对照 checkpoint + 规范产物，给出该 stage 的磁盘真相（与 run.status 解耦）。"""
    stage = str(stage or "").strip()
    out: dict[str, Any] = {
        "stage": stage or None,
        "checkpoint_status": None,
        "artifact": None,
        "artifact_exists": False,
        "work_done": False,
        "gate_blocked": False,
    }
    if not stage:
        return out
    marker = _read_json(project_dir / "project.json") or {}
    pipeline_type = str(marker.get("pipeline_type") or "")
    from plugins.openmontage.lib.checkpoint import read_checkpoint
    from plugins.openmontage.lib.project_status import resolve_canonical_artifact_name

    try:
        cp = read_checkpoint(PROJECTS_DIR, project_dir.name, stage)
    except Exception:
        cp = None
    cp_status = (cp or {}).get("status") if isinstance(cp, dict) else None
    out["checkpoint_status"] = cp_status
    out["gate_blocked"] = cp_status == "awaiting_human"

    artifact_name = resolve_canonical_artifact_name(
        stage, pipeline_type=pipeline_type or None,
    )
    out["artifact"] = artifact_name
    if artifact_name:
        art_path = project_dir / "artifacts" / f"{artifact_name}.json"
        out["artifact_exists"] = art_path.is_file()

    # 阶段工作在磁盘上已闭环：checkpoint 终态，或产物在且 checkpoint 非失败中
    if cp_status in ("completed", "awaiting_human"):
        out["work_done"] = True
    return out


def _memory_task_active(project_dir: Path, task_id: str) -> bool:
    """该 task 是否仍有内存态 RunTask（in-process agent 会话未返回）。"""
    mem = _TASKS.get(project_dir.name)
    if mem is None:
        return False
    if mem.task_id != task_id:
        return False
    return mem.status in ("queued", "running")


def _agent_live(project_dir: Path, task_id: str) -> bool:
    mem = _TASKS.get(project_dir.name)
    if mem is None or mem.task_id != task_id:
        return False
    return mem.agent is not None and mem.status in ("queued", "running")


def _run_activity(project_dir: Path, task_id: str, state: dict) -> dict[str, Any]:
    """拆开 hub pid 与真实 agent 活动（in-process 下 pid 永远是 hub）。"""
    try:
        pid_i = int(state.get("pid") or 0)
    except (TypeError, ValueError):
        pid_i = 0
    hub_alive = _pid_alive(pid_i) if pid_i > 0 else False
    mem_active = _memory_task_active(project_dir, task_id)
    agent_live = _agent_live(project_dir, task_id)
    log_path = project_dir / RUNS_DIRNAME / f"{task_id}.log"
    log_age_s: Optional[float] = None
    if log_path.is_file():
        try:
            log_age_s = max(0.0, time.time() - log_path.stat().st_mtime)
        except OSError:
            log_age_s = None
    # hub pid 存活 ≠ worker 在干活；以内存任务 / live agent / 近期日志为准
    worker_active = bool(mem_active or agent_live)
    if not worker_active and log_age_s is not None and log_age_s < 45.0:
        worker_active = str(state.get("status") or "") in ("queued", "running")
    return {
        "pid": pid_i or None,
        "pid_scope": "hub",  # in-process executor: runs record hub pid
        "hub_pid_alive": hub_alive,
        "memory_task_active": mem_active,
        "agent_live": agent_live,
        "log_age_seconds": log_age_s,
        "worker_active": worker_active,
        # 兼容旧字段：勿再把 hub 存活当成「阶段还在跑」
        "pid_alive": worker_active,
    }


def _suggested_action_for_run(
    *,
    run_status: str,
    truth: dict[str, Any],
    activity: dict[str, Any],
) -> dict[str, Any]:
    """给编排大脑的可执行建议（停轮询 / 审批 / 继续等）。"""
    stage = truth.get("stage")
    if truth.get("gate_blocked"):
        return {
            "action": "om_state approve",
            "message": (
                f"阶段 {stage} 已 awaiting_human，停止轮询本 task；"
                f"用 om_state(action='approve', stage={stage!r}) 或 Backlot 批准。"
            ),
        }
    if truth.get("work_done"):
        return {
            "action": "stop_polling",
            "message": (
                f"阶段 {stage} 磁盘工作已闭环"
                f"（checkpoint={truth.get('checkpoint_status')}），"
                "停止对本 task_id 空转轮询；等 run finalize 或直接推进 next_stage。"
            ),
        }
    if run_status in ("failed", "aborted"):
        if truth.get("artifact_exists") and truth.get("checkpoint_status") not in (
            "completed",
            "awaiting_human",
        ):
            return {
                "action": "om_state complete_from_disk",
                "message": (
                    f"产物已在磁盘但 checkpoint 仍是 {truth.get('checkpoint_status') or 'pending'}；"
                    f"om_state(action='complete_from_disk', stage={stage!r})。"
                ),
            }
        return {
            "action": "om_run retry or inspect diagnostics",
            "message": "任务已失败；读 error/diagnostics 后决定重跑或修复。",
        }
    if run_status == "succeeded":
        return {
            "action": "stop_polling",
            "message": "任务已成功，停止轮询；用 om_project 看 next_stage。",
        }
    if activity.get("worker_active"):
        return {
            "action": "om_job continue",
            "message": "阶段仍在推进（worker_active）；约 15–60s 后再 om_job。",
        }
    return {
        "action": "om_job continue",
        "message": "run 仍标 running 但未见 worker 活动；再查一次 om_job/runtime，勿空等数分钟。",
    }


def _enrich_run_truth(project_dir: Path, state: dict) -> dict[str, Any]:
    """把 run 元数据与磁盘 checkpoint/产物对齐，供 om_job 返回。"""
    task_id = str(state.get("task_id") or "")
    stage = str(state.get("stage") or "")
    run_status = str(state.get("status") or "")
    truth = _stage_disk_truth(project_dir, stage)
    activity = _run_activity(project_dir, task_id, state)
    suggestion = _suggested_action_for_run(
        run_status=run_status, truth=truth, activity=activity,
    )
    return {
        "run_status": run_status,
        "checkpoint_status": truth.get("checkpoint_status"),
        "artifact": truth.get("artifact"),
        "artifact_exists": truth.get("artifact_exists"),
        "work_done": truth.get("work_done"),
        "gate_blocked": truth.get("gate_blocked"),
        **activity,
        "suggested_action": suggestion.get("action"),
        "suggested_message": suggestion.get("message"),
    }


def _reconcile_work_done_runs(project_dir: Path) -> None:
    """checkpoint 已闭环但 runs 仍标 running（常因 hub pid 永不 stale）时回收。

    hub 进程 pid 一直活着，``_reconcile_orphan_runs`` 不会回收这类僵尸。
    有内存态时 interrupt；无论有无内存，都 finalize 磁盘 run 并释放锁，
    避免 busy 永久挡住 om_run / approve。
    """
    for state in _read_runs_from_disk(project_dir, limit=KEEP_RUNS):
        if state.get("status") not in ("queued", "running"):
            continue
        stage = str(state.get("stage") or "")
        tid = str(state.get("task_id") or "")
        if not stage or not tid:
            continue
        truth = _stage_disk_truth(project_dir, stage)
        if not truth.get("work_done"):
            continue
        mem = _TASKS.get(project_dir.name)
        if mem and mem.task_id == tid and mem.status in ("queued", "running"):
            _interrupt_agent(mem, "stage checkpoint already closed on disk")
            # 标终态，使 busy 不再认这笔内存任务（agent 收尾可异步）
            mem.status = "succeeded"
            mem.error = None
            mem.finished_at = _now_iso()
        log.info(
            "reconcile.work_done project=%s task=%s stage=%s checkpoint=%s",
            project_dir.name, tid, stage, truth.get("checkpoint_status"),
        )
        _finalize_reconciled(project_dir, state, interrupted=False)
    _reconcile_lock(project_dir)


def read_run_log(project_dir: Path, task_id: str, *, offset: int = 0, limit: int = 200) -> dict:
    """Return run metadata + a log window. Prefer this over reading runs/*.json by hand."""
    # 先按磁盘真相回收「已完成却仍 running」的谎言状态
    _reconcile_work_done_runs(project_dir)
    state = _read_run(project_dir, task_id) or {}
    log_path = project_dir / RUNS_DIRNAME / f"{task_id}.log"
    lines: list[str] = []
    if log_path.is_file():
        raw = log_path.read_bytes().decode("utf-8", errors="replace")
        lines = render_run_log(raw)
    elif not state:
        raise StageRunError("日志文件不存在")

    next_offset = min(offset + limit, len(lines))
    truth = _enrich_run_truth(project_dir, state) if state else {}
    payload: dict[str, Any] = {
        "task_id": task_id,
        # 兼容旧字段
        "status": state.get("status"),
        "stage": state.get("stage"),
        "error": state.get("error"),
        "started_at": state.get("started_at"),
        "finished_at": state.get("finished_at"),
        "exit_code": state.get("exit_code"),
        "offset": offset,
        "next_offset": next_offset,
        "total": len(lines),
        "lines": lines[offset:offset + limit],
        # 真相字段（编排应以这些为准，勿只看 status+pid_alive）
        **truth,
    }
    recovery = _recovery_hint_for_run(project_dir, state)
    if recovery:
        payload["recovery"] = recovery
    elif truth.get("work_done") and str(state.get("status") or "") in ("queued", "running"):
        payload["recovery"] = {
            "work_done_on_disk": True,
            "stage": state.get("stage"),
            "checkpoint_status": truth.get("checkpoint_status"),
            "suggested_action": truth.get("suggested_action"),
            "message": truth.get("suggested_message"),
        }
    if str(state.get("status") or "") in ("queued", "running", "failed", "aborted"):
        payload["runtime"] = inspect_project_runtime(project_dir, reconcile=False)
    elif truth.get("work_done"):
        # succeeded 也附带精简 runtime，方便确认 busy 已清
        payload["runtime"] = inspect_project_runtime(project_dir, reconcile=False)
    return payload


def _recovery_hint_for_run(project_dir: Path, state: dict) -> Optional[dict]:
    """When a run ended but the stage artifact sits orphaned on disk, tell om_* how to close it."""
    status = str(state.get("status") or "")
    stage = str(state.get("stage") or "").strip()
    if not stage:
        return None
    truth = _stage_disk_truth(project_dir, stage)
    # running 但已 work_done → 由 read_run_log 的 recovery 分支处理
    if status in ("queued", "running") and truth.get("work_done"):
        return None
    if status not in ("failed", "aborted", "succeeded"):
        return None
    if truth.get("work_done"):
        return None
    if not truth.get("artifact_exists"):
        return None
    artifact_name = truth.get("artifact")
    cp_status = truth.get("checkpoint_status")
    return {
        "orphan_on_disk": True,
        "stage": stage,
        "artifact": artifact_name,
        "checkpoint_status": cp_status or "pending",
        "suggested_action": "om_state complete_from_disk",
        "message": (
            f"阶段 {stage} 的规范产物 {artifact_name}.json 已在磁盘，"
            f"但 checkpoint 仍是 {cp_status or 'pending'}。"
            f"请调用 om_state(action='complete_from_disk', project_id={project_dir.name!r}, "
            f"stage={stage!r}) 闭环；不要去读 checkpoint.py / stage_runner.py。"
        ),
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
# Agent 运行监控（in-process；无子进程）
# ---------------------------------------------------------------------------


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
            _interrupt_agent(task, "wall-clock timeout")
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
    """Validate + lock + build prompt, logging both outcomes.

    A rejected run leaves no other trace: no runs/ entry, no checkpoint change.
    """
    project_id = project_dir.name
    try:
        task = _prepare_stage_run(
            project_dir, stage=stage, parameters=parameters, feedback=feedback,
        )
    except StageRunError as exc:
        log.warning(
            "run.rejected project=%s stage=%s reason=%s: %s",
            project_id, stage or "(next)", type(exc).__name__, exc,
        )
        raise
    log.info(
        "run.accepted project=%s stage=%s task=%s revision=%s",
        project_id, task.stage, task.task_id, bool(feedback),
    )
    return task


def _prepare_stage_run(
    project_dir: Path,
    *,
    stage: Optional[str] = None,
    parameters: Optional[dict] = None,
    feedback: Optional[str] = None,
) -> RunTask:
    """同步校验 + 加锁 + 组装 prompt + 注册任务（不启动 agent）。

    校验顺序（契约）：manifest 加载 → stage == get_next_stage（同时覆盖
    首次运行与驳回/失败重跑）→ 加锁（409）→ 组装 prompt。
    """
    from plugins.openmontage.lib.checkpoint import get_next_stage, read_checkpoint
    from plugins.openmontage.lib.pipeline_loader import get_stage_order, load_pipeline_readonly

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
    if next_stage is None:
        # 显式请求某阶段时 target 非空，会落到下面的分支报"只能运行 None"。
        raise StageRunError(f"流水线已完结，无法再运行 {target!r}")
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

    # 锁携带 pid —— agent 启动前占位 0，启动后写 hub pid。
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


def ensure_background_loop() -> asyncio.AbstractEventLoop:
    """Start (once) a daemon thread running a dedicated asyncio event loop."""
    global _bg_loop, _bg_thread
    with _bg_lock:
        if _bg_loop is not None and _bg_loop.is_running():
            return _bg_loop
        loop = asyncio.new_event_loop()

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(
            target=_runner,
            name="openmontage-stage-runner",
            daemon=True,
        )
        thread.start()
        _bg_loop = loop
        _bg_thread = thread
        return loop


def schedule_run_task(task: RunTask, *, chain: bool = True) -> None:
    """Schedule ``run_task`` on the current loop or the background runner loop."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop is not None:
        loop.create_task(run_task(task, chain=chain))
        return

    bg_loop = ensure_background_loop()
    future = asyncio.run_coroutine_threadsafe(run_task(task, chain=chain), bg_loop)

    def _log_failure(done: "asyncio.Future[None]") -> None:
        try:
            done.result()
        except Exception as exc:
            log.exception(
                "run_task failed project=%s stage=%s task=%s: %s",
                task.project_id,
                task.stage,
                task.task_id,
                exc,
            )

    future.add_done_callback(_log_failure)


async def run_task(task: RunTask, *, chain: bool = True) -> None:
    """核心协程：in-process AIAgent → 等待结束 → 定终态。"""
    runs = _runs_dir(task.project_dir)
    runs.mkdir(parents=True, exist_ok=True)
    log_fh = open(task.log_path, "wb", buffering=0)  # 二进制句柄，防混编码
    succeeded = False
    try:
        task.pid = os.getpid()  # hub pid — stale lock after server restart
        log.info(
            "run.started project=%s stage=%s task=%s pid=%s timeout=%ss",
            task.project_id, task.stage, task.task_id, task.pid,
            task.timeout_seconds,
        )
        _update_lock_pid(task.project_dir, task)
        task.status = "running"
        _write_run_state(task)
        task.monitor_task = asyncio.create_task(_monitor(task))
        task.heartbeat_task = asyncio.create_task(_heartbeat(task))

        # Test seam: monkeypatch execute_stage_agent.
        task.exit_code = await execute_stage_agent(task, log_fh)
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
        _interrupt_agent(task, "task cancelled")
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
        task.agent = None
    if chain and succeeded:
        await auto_advance_chain(task.project_dir, from_stage=task.stage)



def _finalize(task: RunTask, status: str) -> None:
    task.status = status
    task.finished_at = _now_iso()
    (log.info if status == "succeeded" else log.warning)(
        "run.finished project=%s stage=%s task=%s status=%s exit=%s error=%s",
        task.project_id, task.stage, task.task_id, status, task.exit_code,
        task.error or "-",
    )
    if status in ("failed", "aborted"):
        # agent 已留下 in_progress checkpoint 时补写 failed，避免 rail 永续
        # "进行中"（cancel/超时/服务重启专用；正常失败由 agent 自己写）。
        _patch_stuck_in_progress(task)
    _write_run_state(task)
    _release_lock(task.project_dir, task.task_id)
    _TASKS.pop(task.project_id, None)
    _cleanup_old_runs(task.project_dir)


def _stage_requires_human_gate(manifest: dict, stage_name: str) -> bool:
    from plugins.openmontage.lib.pipeline_loader import get_stage_human_approval_default

    gate = get_stage_human_approval_default(manifest, stage_name)
    return bool(gate) if gate is not None else False


def _awaiting_human_stage(project_dir: Path, pipeline_type: str) -> Optional[str]:
    """Return a stage name blocked on human approval, if any."""
    from plugins.openmontage.lib.checkpoint import read_checkpoint, get_pipeline_stages

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
    from plugins.openmontage.lib.checkpoint import get_next_stage, read_checkpoint
    from plugins.openmontage.lib.pipeline_loader import load_pipeline_readonly

    project_id = project_dir.name

    def halt(reason: str) -> None:
        # Every stop is named: a silent `return None` here is indistinguishable
        # from a crash when the board simply stops advancing.
        log.info(
            "advance.halt project=%s after=%s reason=%s",
            project_id, completed_stage, reason,
        )
        return None

    busy = _busy_or_none(project_dir)
    if busy:
        return halt(f"busy: {busy}")

    cp = read_checkpoint(PROJECTS_DIR, project_id, completed_stage)
    if not cp or cp.get("status") != "completed":
        return halt(f"stage_not_completed status={(cp or {}).get('status')}")

    pipeline_type = cp.get("pipeline_type")
    if not pipeline_type:
        return halt("no_pipeline_type")

    awaiting = _awaiting_human_stage(project_dir, pipeline_type)
    if awaiting:
        return halt(f"awaiting_human stage={awaiting}")

    try:
        manifest = load_pipeline_readonly(pipeline_type)
    except Exception as exc:
        return halt(f"manifest_load_failed {type(exc).__name__}: {exc}")

    if _stage_requires_human_gate(manifest, completed_stage) and not cp.get("human_approved"):
        return halt("gated_not_approved")

    next_stage = get_next_stage(PROJECTS_DIR, project_id, pipeline_type)
    if not next_stage:
        return halt("pipeline_complete")

    try:
        return prepare_stage_run(project_dir, stage=next_stage)
    except (StageRunError, StageBusyError) as exc:
        return halt(f"prepare_failed {type(exc).__name__}: {exc}")


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
    from plugins.openmontage.lib.checkpoint import read_checkpoint, write_checkpoint

    try:
        cp = read_checkpoint(PROJECTS_DIR, task.project_id, task.stage)
    except Exception as exc:
        log.warning(
            "patch_stuck.read_checkpoint_failed project=%s stage=%s: %s",
            task.project_id, task.stage, exc,
        )
        return
    if not cp or cp.get("status") != "in_progress":
        return
    try:
        write_checkpoint(
            PROJECTS_DIR,
            task.project_id,
            task.stage,
            "failed",
            artifacts=cp.get("artifacts") if isinstance(cp.get("artifacts"), dict) else {},
            pipeline_type=task.pipeline_type or cp.get("pipeline_type"),
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
        _interrupt_agent(task, "user cancel")
        _finalize(task, "aborted")
        return {"ok": True, "task_id": task_id, "status": "aborted"}
    # 非内存态任务（服务重启后）：in-process agent 已随 hub 消亡，只标状态。
    state = _read_run(project_dir, task_id)
    if not state:
        raise StageRunError("未知任务")
    if state.get("status") not in ("queued", "running"):
        return {"ok": False, "task_id": task_id, "status": state.get("status")}
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
    """服务启动时回收磁盘上仍标 running/queued 的任务。

    In-process AIAgent 随 hub 进程消亡，无法 PID 接回——一律标 failed/interrupted。
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
            _finalize_reconciled(project_dir, state, interrupted=True)
            stage = str(state.get("stage") or "")
            if stage:
                _patch_stuck_in_progress(
                    RunTask(
                        task_id=str(state.get("task_id") or ""),
                        project_dir=project_dir,
                        project_id=project_dir.name,
                        stage=stage,
                        pipeline_type=str(state.get("pipeline_type") or ""),
                        status="aborted",
                        error=state.get("error")
                        or "服务重启导致进程状态丢失（任务中断）",
                    )
                )


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
    from plugins.openmontage.lib.checkpoint import read_checkpoint

    # 残缺 checkpoint（缺 artifacts 字典等）不能阻断孤儿 run 回收，
    # 否则磁盘会永远卡在 running，om_run / complete_from_disk 全被 busy 挡住。
    cp = None
    try:
        cp = read_checkpoint(PROJECTS_DIR, project_dir.name, state.get("stage", ""))
    except Exception as exc:
        log.warning(
            "reconcile.read_checkpoint_failed project=%s stage=%s: %s",
            project_dir.name, state.get("stage"), exc,
        )
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
    from plugins.openmontage.lib.pipeline_loader import (
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
        # 技能随代码走，落在插件目录下，不在仓库根。
        skill_file = CODE_ROOT / skill_path
        if skill_file.is_file():
            skill_text = skill_file.read_text(encoding="utf-8")
        else:
            # 不要沉默：prompt 声称"全文已粘贴"，贴空块会让 agent 自己去
            # Grep/Read 翻技能，白烧若干轮。说清楚它得自己读。
            skill_text = (
                f"（技能文件未找到：{skill_path} —— 请用 skill_view 或确认导演技能路径；"
                f"不要用 search_files / terminal 翻仓库）"
            )

    # reference_analysis 依赖 meta 技能：全文一并粘贴。
    if stage == "reference_analysis":
        meta_ref = CODE_ROOT / "skills" / "meta" / "video-reference-analyst.md"
        if meta_ref.is_file():
            skill_text = (
                f"{skill_text}\n\n"
                "--- 元技能 openmontage:video-reference-analyst 全文开始 ---\n"
                f"{meta_ref.read_text(encoding='utf-8')}\n"
                "--- 元技能全文结束 ---\n"
            )

    gated = bool(get_stage_human_approval_default(manifest, stage))
    stage_block = next(
        (s for s in (manifest.get("stages") or []) if s.get("name") == stage),
        {},
    )

    # 前置 artifacts：project_status 提供 completed stages 的 artifact 清单。
    try:
        from plugins.openmontage.lib.project_status import build_project_status

        status = build_project_status(project_id, projects_dir=PROJECTS_DIR)
    except Exception:
        status = {}
    # 写成可直接复制的 om_artifact_read 调用，避免模型去猜 checkpoint_*.json
    artifact_lines: list[str] = []
    for st in status.get("stages") or []:
        if st.get("status") != "completed":
            continue
        artifact = st.get("canonical_artifact")
        if not artifact or not st.get("artifact_exists"):
            continue
        upstream = st.get("stage") or "?"
        artifact_lines.append(
            f'  - om_artifact_read(artifact="{artifact}", '
            f'label="读{artifact}")  '
            f"# 上游 {upstream} → artifacts/{artifact}.json"
        )
    artifact_list = "\n".join(artifact_lines) or "  （无）"

    feedback_text = f"\n{feedback}\n" if feedback else "（无）"
    parameters_text = json.dumps(parameters or {}, ensure_ascii=False)

    # 规范产物字段契约：导演技能常只说「按 schema 校验」却不列 JSON 键名，
    # 模型会自造 stat/source 等别名。把契约摘要钉进 prompt，从源头对齐。
    produces = [
        str(p) for p in (stage_block.get("produces") or []) if isinstance(p, str) and p
    ]
    artifact_contracts: list[dict] = []
    for art_name in produces:
        try:
            from plugins.openmontage.schemas.artifacts import summarize_artifact_schema

            artifact_contracts.append(summarize_artifact_schema(art_name))
        except Exception as exc:
            artifact_contracts.append({"artifact": art_name, "error": str(exc)})
    contracts_text = (
        json.dumps(artifact_contracts, ensure_ascii=False, indent=1)[:14000]
        if artifact_contracts
        else "（本阶段无规范产物）"
    )

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

【Hermes 工具面 — 强制】
你只有 openmontage_stage + web + skills_view。禁止 terminal / execute_code / read_file /
write_file / search_files / python -c。
通用联网（Hermes 原生工具，已在本会话工具列表里 — 直接调用函数名）：
  - web_search(query=..., limit=...)
  - web_extract(urls=[...])  —— 拉取页面正文；没有 web_fetch，用本工具
禁止：把 web_* 当成 om_registry 里的 tool 名去 execute；om_registry 只管 OpenMontage
媒体/分析注册表，本来就没有 web/research 类。缺检索时先直接调 web_search，
禁止因「注册表无 web」而 status=failed。
OpenMontage 专用：
  - om_registry(action="menu"|"catalog"|"execute", tool=..., params={{...}}, label=...)
  - om_checkpoint(status=..., artifacts={{...}}, label=...)  —— 写阶段状态的唯一通道
  - om_artifact_read(artifact=<规范名> 或 path=artifacts|assets|renders|exports/..., label=...)
    禁止 path=checkpoint_*.json / runs/ / .run.lock；不要用本工具读阶段状态账本
  - om_artifact_write(path="artifacts/....json", content={{...}}, label=...)
  - om_decision_append(decisions=[...], label=...)
  - skill_view（必要时只读补技能，如
    skill_view("openmontage:video-reference-analyst")）
project_id 默认取自运行环境（{project_id}）；stage 默认 {stage}。

【必读材料】
1. 阶段导演技能（本阶段唯一执行规程，全文已粘贴）:
   {skill_path}
   --- 技能全文开始 ---
   {skill_text}
   --- 技能全文结束 ---
2. 项目状态（get_next_stage 必须等于 {stage}）:
   {json.dumps(status, ensure_ascii=False, indent=1)[:12000]}
3. 流水线 manifest 中本阶段定义:
   {json.dumps(stage_block, ensure_ascii=False, indent=1)[:6000]}
4. 前置 artifacts（必须用下列 om_artifact_read；禁止读 checkpoint_*.json）:
   {artifact_list}
5. 上次审阅反馈（页面驳回时产生，必须逐条回应）:
   {feedback_text}
6. 用户附加参数:
   {parameters_text}
7. 规范产物字段契约（写入 artifacts / checkpoint 前必须一字不差对齐；
   禁止自造字段名；不要再去打开 *.schema.json）:
   {contracts_text}

【执行规程（强制）】
1. 进入阶段先 om_checkpoint(status='in_progress', artifacts={{}}, label=...)，
   可带 metadata.partial_progress。
2. 联网用 web_search / web_extract；OM 注册表工具用
   om_registry(action='execute', tool=..., params={{...}})。
   tools_available 非空时只约束 om_registry 名单（web_* 始终可用）。
   禁止脚本串联、禁止直接编辑 checkpoint / decision_log。
3. 规范产物可先 om_artifact_write 落到 artifacts/，再写入 checkpoint.artifacts。
4. 完成后:
   - 本阶段 human_approval_default: {gated}
   - gated: om_checkpoint(status='awaiting_human', artifacts=...), human_approved
     保持 False，决策以 user_approved=false 经 om_decision_append 追加，然后停止
     （END YOUR TURN）——人类在 Backlot 页面批准或驳回。
   - 非 gated: om_checkpoint(status='completed', artifacts=...).
   - 永远不要对 gated 阶段写 completed + human_approved=False（库会 GATE VIOLATION）。
5. 任何失败: om_checkpoint(status='failed', error=≤400字)，不要留下 in_progress。
6. 时间预算 {wall_time_minutes} 分钟（服务端到点中断）。参考成本提示 ${budget_usd}。
   稳步推进，频繁 checkpoint。
"""


# ---------------------------------------------------------------------------
# 页面审批（纯 lib 调用——与 nle_edit.apply_draft 同构的受管控写路径）
# ---------------------------------------------------------------------------


def inspect_project_runtime(project_dir: Path, *, reconcile: bool = True) -> dict[str, Any]:
    """结构化运行时快照 —— om_* 失败时原样回传，避免猜 busy / 僵尸进程。

    默认会先 reconcile 孤儿 run + work_done 僵尸（与 ``_busy_or_none`` 同副作用）。
    pid 字段语义：runs/lock 记的是 hub pid；``pid_alive``/``worker_active`` 表示
    真实 worker，勿把 hub 存活当成阶段还在跑。
    """
    project_id = project_dir.name
    if reconcile:
        _reconcile_orphan_runs(project_dir)
        _reconcile_work_done_runs(project_dir)
        task = _TASKS.get(project_id)
        if task and task.status in ("queued", "running"):
            mem_pid = task.pid if isinstance(task.pid, int) else 0
            # hub pid 永活时不要靠「pid 死了」清内存；仅当确无 worker 迹象
            # 且磁盘 checkpoint 已闭环时，上面 work_done 已处理。
            if mem_pid > 0 and not _pid_alive(mem_pid):
                _TASKS.pop(project_id, None)
                _reconcile_lock(project_dir)
        for state in _read_runs_from_disk(project_dir, limit=KEEP_RUNS):
            if state.get("status") not in ("queued", "running"):
                continue
            try:
                pid_i = int(state.get("pid") or 0)
            except (TypeError, ValueError):
                pid_i = 0
            # hub pid 仍活时保留（work_done 僵尸已由 _reconcile_work_done_runs 处理）
            if pid_i > 0 and _pid_alive(pid_i):
                continue
            _finalize_reconciled(project_dir, state, interrupted=True)
        _reconcile_lock(project_dir)

    lock_raw = _read_json(_lock_path(project_dir))
    lock_info: Optional[dict[str, Any]] = None
    if isinstance(lock_raw, dict):
        try:
            lock_pid = int(lock_raw.get("pid") or 0)
        except (TypeError, ValueError):
            lock_pid = 0
        lock_stage = str(lock_raw.get("stage") or "")
        lock_truth = _stage_disk_truth(project_dir, lock_stage) if lock_stage else {}
        hub_alive = _pid_alive(lock_pid) if lock_pid > 0 else False
        stale = _lock_is_stale(lock_raw, project_dir)
        # work_done 阶段的锁不挡 busy（即便 hub pid 仍活）
        blocks_busy = bool(
            not stale
            and not lock_truth.get("work_done")
            and (
                hub_alive
                or _memory_task_active(project_dir, str(lock_raw.get("task_id") or ""))
            )
        )
        lock_info = {
            "path": LOCK_FILENAME,
            "exists": True,
            "task_id": lock_raw.get("task_id"),
            "stage": lock_raw.get("stage"),
            "pid": lock_pid or None,
            "pid_scope": "hub",
            "hub_pid_alive": hub_alive,
            "pid_alive": hub_alive,  # lock 层仍报 hub；busy 看 blocks_busy
            "started_at": lock_raw.get("started_at"),
            "expires_at": lock_raw.get("expires_at"),
            "stale": stale,
            "work_done": lock_truth.get("work_done"),
            "blocks_busy": blocks_busy,
        }

    memory_task: Optional[dict[str, Any]] = None
    task = _TASKS.get(project_id)
    mem_blocks_busy = False
    if task is not None:
        mem_pid = task.pid if isinstance(task.pid, int) else 0
        mem_truth = _stage_disk_truth(project_dir, task.stage)
        hub_alive = _pid_alive(mem_pid) if mem_pid > 0 else False
        agent_live = task.agent is not None and task.status in ("queued", "running")
        mem_blocks_busy = bool(
            task.status in ("queued", "running") and not mem_truth.get("work_done")
        )
        memory_task = {
            "task_id": task.task_id,
            "stage": task.stage,
            "status": task.status,
            "pid": mem_pid or None,
            "pid_scope": "hub",
            "hub_pid_alive": hub_alive,
            "agent_live": agent_live,
            # 内存态 queued/running 即视为 worker（编排侧应轮询）；≠ hub pid 存活
            "worker_active": task.status in ("queued", "running"),
            "pid_alive": task.status in ("queued", "running"),
            "work_done": mem_truth.get("work_done"),
            "checkpoint_status": mem_truth.get("checkpoint_status"),
            "error": task.error,
            "started_at": task.started_at,
            "finished_at": task.finished_at,
        }

    disk_active: list[dict[str, Any]] = []
    for state in _read_runs_from_disk(project_dir, limit=KEEP_RUNS):
        if state.get("status") not in ("queued", "running"):
            continue
        stage = str(state.get("stage") or "")
        st_truth = _stage_disk_truth(project_dir, stage)
        if st_truth.get("work_done"):
            continue  # 不计入 busy
        act = _run_activity(project_dir, str(state.get("task_id") or ""), state)
        disk_active.append({
            "task_id": state.get("task_id"),
            "stage": state.get("stage"),
            "status": state.get("status"),
            "pid": act.get("pid"),
            "pid_scope": "hub",
            "hub_pid_alive": act.get("hub_pid_alive"),
            "worker_active": act.get("worker_active"),
            "pid_alive": act.get("pid_alive"),
            "work_done": False,
            "checkpoint_status": st_truth.get("checkpoint_status"),
            "error": state.get("error"),
            "started_at": state.get("started_at"),
            "finished_at": state.get("finished_at"),
        })

    blockers: list[dict[str, Any]] = []
    busy_message: Optional[str] = None

    if mem_blocks_busy and task is not None and memory_task is not None:
        busy_message = f"该项目已有任务 {task.task_id} 在运行，请等待完成"
        blockers.append({
            "source": "memory",
            "task_id": task.task_id,
            "stage": task.stage,
            "status": task.status,
            "pid": memory_task.get("pid"),
            "pid_scope": "hub",
            "pid_alive": memory_task.get("pid_alive"),
            "worker_active": memory_task.get("worker_active"),
            "work_done": memory_task.get("work_done"),
        })
    elif disk_active:
        first = disk_active[0]
        busy_message = (
            f"该项目已有任务 {first.get('task_id')} 在运行"
            f"（磁盘 status={first.get('status')} worker_active={first.get('worker_active')}），"
            "请用 om_job 轮询"
        )
        for entry in disk_active:
            blockers.append({"source": "disk", **entry})
    elif lock_info and lock_info.get("blocks_busy"):
        busy_message = (
            f"该项目已有任务 {lock_info.get('task_id')} 在运行，请等待完成"
        )
        blockers.append({"source": "lock", **lock_info})

    suggested: list[str] = []
    if busy_message:
        tid = next((b.get("task_id") for b in blockers if b.get("task_id")), None)
        stage_hint = next((b.get("stage") for b in blockers if b.get("stage")), None)
        truth = _stage_disk_truth(project_dir, str(stage_hint or "")) if stage_hint else {}
        worker = any(b.get("worker_active") or b.get("pid_alive") for b in blockers)
        if truth.get("gate_blocked"):
            suggested.append(
                f"om_state(action='approve', project_id={project_id!r}, "
                f"stage={stage_hint!r})  # gate_blocked，停止对本 task 空转轮询"
            )
        elif worker and tid:
            suggested.append(
                f"om_job(project_id={project_id!r}, task_id={tid!r}) 轮询进度；"
                "任务仍在跑时不要 complete_from_disk / approve"
            )
        else:
            suggested.append(
                "未见 worker_active —— 再调 om_project/om_job 确认 runtime.busy；"
                "仍 busy 则把本 diagnostics 原样反馈，不要 find/读 stage_runner 源码"
            )
        suggested.append("不要用 terminal/execute_code 手工改 .run.lock 或 runs/*.json")
    else:
        suggested.append(f"om_project(project_id={project_id!r})")
        suggested.append(
            f"om_run(action='start', project_id={project_id!r}, stage=...)"
        )

    report: dict[str, Any] = {
        "project_id": project_id,
        "busy": busy_message is not None,
        "busy_message": busy_message,
        "lock": lock_info,
        "memory_task": memory_task,
        "disk_active_runs": disk_active,
        "blockers": blockers,
        "suggested_actions": suggested,
    }
    if busy_message:
        log.warning(
            "runtime.busy project=%s message=%s blockers=%s",
            project_id,
            busy_message,
            json.dumps(blockers, ensure_ascii=False, default=str),
        )
    else:
        log.info(
            "runtime.idle project=%s has_lock=%s disk_active=%d",
            project_id,
            bool(lock_info),
            len(disk_active),
        )
    return report


def _schema_validation_diagnostics(artifact_name: str, exc: BaseException) -> dict[str, Any]:
    """展开 jsonschema 错误，供 om_state 原样返回，无需再找 schema 文件。"""
    try:
        import jsonschema
    except ImportError:
        jsonschema = None  # type: ignore

    if jsonschema is not None and isinstance(exc, jsonschema.ValidationError):
        errors = [{
            "message": exc.message,
            "path": list(exc.absolute_path),
            "schema_path": list(exc.absolute_schema_path),
            "validator": exc.validator,
            "validator_value": exc.validator_value,
        }]
        # 附带同级更多错误（最多 8 条），避免只看到第一个
        try:
            from plugins.openmontage.schemas.artifacts import load_schema

            schema = load_schema(artifact_name)
            Validator = jsonschema.validators.validator_for(schema)
            Validator.check_schema(schema)
            validator = Validator(schema)
            for err in list(validator.iter_errors(exc.instance))[:8]:
                item = {
                    "message": err.message,
                    "path": list(err.absolute_path),
                    "schema_path": list(err.absolute_schema_path),
                    "validator": err.validator,
                    "validator_value": err.validator_value,
                }
                if item not in errors:
                    errors.append(item)
        except Exception:
            pass
        return {
            "artifact": artifact_name,
            "message": exc.message,
            "path": list(exc.absolute_path),
            "errors": errors[:8],
        }
    return {"artifact": artifact_name, "message": str(exc), "errors": [{"message": str(exc)}]}


def _busy_or_none(project_dir: Path) -> Optional[str]:
    """兼容旧调用方：返回 busy 文案或 None。完整信息见 ``inspect_project_runtime``。"""
    return inspect_project_runtime(project_dir).get("busy_message")


def _require_not_busy(project_dir: Path) -> dict[str, Any]:
    """若项目 busy 则抛 ``StageBusyError``（带 diagnostics）；否则返回 runtime 报告。"""
    report = inspect_project_runtime(project_dir)
    if report.get("busy"):
        raise StageBusyError(
            str(report.get("busy_message") or "项目忙碌"),
            diagnostics=report,
        )
    return report


def approve_stage(project_dir: Path, stage: str, *, notes: str = "") -> dict:
    """页面批准：awaiting_human → completed + human_approved=True（保留
    artifacts）+ 镜像追加同 (category, subject) 的 user_approved=true 决策
    —— 唯一 audit 干净的页面批准路径（approval_gate_drift 要求）。"""
    from plugins.openmontage.lib.checkpoint import get_next_stage, read_checkpoint, write_checkpoint
    from plugins.openmontage.lib.decision_log import append_decisions

    project_id = project_dir.name
    log.info("approve.request project=%s stage=%s", project_id, stage)
    try:
        _require_not_busy(project_dir)
    except StageBusyError as exc:
        log.warning(
            "approve.rejected project=%s stage=%s reason=busy: %s",
            project_id, stage, exc,
        )
        raise

    cp = read_checkpoint(PROJECTS_DIR, project_id, stage)
    if not cp or cp.get("status") != "awaiting_human":
        log.warning(
            "approve.rejected project=%s stage=%s reason=not_awaiting status=%s",
            project_id, stage, (cp or {}).get("status"),
        )
        raise StageRunError(f"阶段 {stage!r} 不在等待批准状态（awaiting_human）")

    # 顺序是契约的一部分：**先**追加决策再写 checkpoint。反过来（先 completed +
    # human_approved=True，再追加）一旦追加失败，就恰好留下
    # approval_gate_drift 要抓的那种状态——阶段标着"人已批准"而决策仍是
    # user_approved=false，且无人知晓。反向失败只是"日志记了、阶段还挂着
    # awaiting"，板面照实显示，用户重按一次即自愈。
    #
    # 另：若仍有无法镜像的待批决策，**拒绝**写 completed——过去「跳过并继续」
    # 会制造 audit CRITICAL（真实 E2E：非法 category 被 skip 后 checkpoint 已批准）。
    to_append, skipped, grandfather = _approval_mirror(project_dir, stage, notes)
    if skipped:
        log.warning(
            "approve.rejected project=%s stage=%s reason=unmirrorable count=%d detail=%s",
            project_id, stage, len(skipped), skipped,
        )
        raise StageRunError(
            f"阶段 {stage!r} 有 {len(skipped)} 条待批决策无法镜像清账，"
            f"拒绝批准以免 approval_gate_drift。"
            f"详情: {'; '.join(skipped)}",
            diagnostics={
                "project_id": project_id,
                "stage": stage,
                "unmirrored_decisions": skipped,
                "suggested_actions": [
                    "用合法 category（见 decision_log.schema.json enum）"
                    "经 om_decision_append 追加同 subject 的新决策后重试批准",
                    "或修复源决策结构（options_considered / selected / reason）后重试",
                ],
            },
        )
    append_decisions(
        project_id,
        to_append,
        grandfather_categories=grandfather or None,
    )

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
    log.info(
        "approve.done project=%s stage=%s mirrored=%d next=%s",
        project_id, stage, len(to_append), next_stage,
    )
    return {"ok": True, "stage": stage, "status": "completed", "next_stage": next_stage}


def complete_stage_from_disk(project_dir: Path, stage: str) -> dict:
    """Adopt an orphan stage artifact on disk into a completed checkpoint.

    Used when a run failed / aborted but the canonical artifact was already
    written (e.g. video_analysis_brief.json). Gated stages cannot skip human
    approval via this path — they must use awaiting_human + approve.
    """
    from plugins.openmontage.lib.checkpoint import get_next_stage, read_checkpoint, write_checkpoint
    from plugins.openmontage.lib.pipeline_loader import load_pipeline_readonly
    from plugins.openmontage.lib.project_status import resolve_canonical_artifact_name
    from plugins.openmontage.schemas.artifacts import validate_artifact

    project_id = project_dir.name
    log.info("complete_from_disk.request project=%s stage=%s", project_id, stage)

    # 已闭环：先于 busy 检查返回，避免「checkpoint 已 completed 却被僵尸 busy 挡住」
    try:
        existing_cp = read_checkpoint(PROJECTS_DIR, project_id, stage)
    except Exception as exc:
        raise StageRunError(
            f"读取 checkpoint 失败: {exc}",
            diagnostics={
                "project_id": project_id,
                "stage": stage,
                "suggested_actions": [
                    "checkpoint 可能畸形；可 om_run 重跑该 stage，或把本 diagnostics 反馈给开发",
                ],
            },
        ) from exc
    existing_status = (existing_cp or {}).get("status")
    if existing_status in ("completed", "awaiting_human"):
        next_stage = get_next_stage(
            PROJECTS_DIR,
            project_id,
            (existing_cp or {}).get("pipeline_type"),
        )
        return {
            "ok": True,
            "stage": stage,
            "status": existing_status,
            "already_done": True,
            "next_stage": next_stage,
            "suggested_action": "stop_polling",
            "message": (
                f"阶段 {stage} 已是 {existing_status}，无需 complete_from_disk；"
                "停止轮询，用 om_project 看 next_stage / gate。"
            ),
        }

    _require_not_busy(project_dir)

    marker = _read_json(project_dir / "project.json") or {}
    pipeline_type = str(marker.get("pipeline_type") or "")
    if not pipeline_type:
        raise StageRunError(
            "project.json 缺少 pipeline_type",
            diagnostics={"project_id": project_id, "stage": stage},
        )

    try:
        manifest = load_pipeline_readonly(pipeline_type)
    except Exception as exc:
        raise StageRunError(
            f"无法加载流水线清单: {exc}",
            diagnostics={"project_id": project_id, "pipeline_type": pipeline_type},
        ) from exc

    if _stage_requires_human_gate(manifest, stage):
        raise StageRunError(
            f"阶段 {stage!r} 设有人工审批门，不能用 complete_from_disk 跳过。"
            "请写 awaiting_human 后走 om_state approve / Backlot 批准按钮。",
            diagnostics={
                "project_id": project_id,
                "stage": stage,
                "gated": True,
                "suggested_actions": [
                    "写 awaiting_human checkpoint 后 om_state approve",
                    "不要 complete_from_disk 门控阶段",
                ],
            },
        )

    artifact_name = resolve_canonical_artifact_name(
        stage, pipeline_type=pipeline_type, manifest=manifest,
    )
    if not artifact_name:
        raise StageRunError(
            f"阶段 {stage!r} 没有规范产物映射",
            diagnostics={
                "project_id": project_id,
                "stage": stage,
                "pipeline_type": pipeline_type,
            },
        )

    artifact_path = project_dir / "artifacts" / f"{artifact_name}.json"
    if not artifact_path.is_file():
        raise StageRunError(
            f"磁盘上找不到规范产物: {artifact_path.name}",
            diagnostics={
                "project_id": project_id,
                "stage": stage,
                "artifact": artifact_name,
                "expected_path": str(artifact_path),
                "suggested_actions": [
                    f"om_run 重跑 {stage}",
                    "不要去找 schema 文件猜字段",
                ],
            },
        )

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StageRunError(
            f"读取产物失败: {exc}",
            diagnostics={"artifact": artifact_name, "path": str(artifact_path)},
        ) from exc
    if not isinstance(payload, dict):
        raise StageRunError(
            "产物 JSON 必须是 object",
            diagnostics={"artifact": artifact_name, "got_type": type(payload).__name__},
        )

    try:
        validate_artifact(artifact_name, payload)
    except Exception as exc:
        schema_diag = _schema_validation_diagnostics(artifact_name, exc)
        expected = None
        try:
            from plugins.openmontage.schemas.artifacts import summarize_artifact_schema

            expected = summarize_artifact_schema(artifact_name)
        except Exception as sum_exc:
            expected = {"artifact": artifact_name, "error": str(sum_exc)}
        raise StageRunError(
            f"产物 schema 校验失败: {schema_diag.get('message') or exc}",
            diagnostics={
                "project_id": project_id,
                "stage": stage,
                "artifact": artifact_name,
                "path": str(artifact_path),
                "schema": schema_diag,
                "expected": expected,
                "suggested_actions": [
                    "按 diagnostics.expected 的 required / items.required 改字段名"
                    "（不要自造 stat/source 等别名）",
                    "或 om_run 重跑该 stage，prompt 已含同一字段契约",
                    "不要 search_files 找 *.schema.json",
                ],
            },
        ) from exc

    cp = existing_cp

    write_checkpoint(
        PROJECTS_DIR,
        project_id,
        stage,
        "completed",
        artifacts={artifact_name: payload},
        pipeline_type=pipeline_type,
        checkpoint_policy=(cp or {}).get("checkpoint_policy", "guided"),
        human_approved=False,
        metadata={
            **((cp or {}).get("metadata") or {}),
            "completed_via": "complete_from_disk",
            "orphan_artifact": artifact_name,
        },
    )
    next_stage = get_next_stage(PROJECTS_DIR, project_id, pipeline_type)
    log.info(
        "complete_from_disk.done project=%s stage=%s artifact=%s next=%s",
        project_id, stage, artifact_name, next_stage,
    )
    return {
        "ok": True,
        "stage": stage,
        "status": "completed",
        "artifact": artifact_name,
        "next_stage": next_stage,
    }


def _approval_mirror(
    project_dir: Path, stage: str, notes: str,
) -> tuple[list[dict], list[str], set[str]]:
    """构造批准的镜像决策：该阶段每条 user_visible 且未批准的最新决策，
    按**同 (category, subject)** 追加一条 user_approved=true —— 这是
    ``approval_gate_drift`` 认可的唯一清账方式。

    历史脏数据：非法 category 已在磁盘上时，仍用**同 category** 镜像清账
    （经 ``grandfather_categories``），不得改名成 fallback 后留下旧键漂移。

    返回 (待追加, 无法镜像的决策描述, 需祖父化的 category 集合)。
    """
    from plugins.openmontage.lib.decision_log import (
        _DECISION_CATEGORY_ENUM,
        latest_decisions_for_stage,
        load_decision_log,
        suggest_next_decision_id,
        validate_decision_entry,
    )

    project_id = project_dir.name
    log = load_decision_log(project_dir)
    pending = latest_decisions_for_stage(log.get("decisions", []), stage)

    # suggest_next_decision_id 从磁盘算，循环里反复调会给每条同一个 id
    # （随后被 append_decisions 静默去重 → 只落一条）。取一次基号后自增。
    base = suggest_next_decision_id(project_dir, prefix="wa")
    start = int(base.rsplit("-", 1)[1])

    to_append: list[dict] = []
    skipped: list[str] = []
    grandfather: set[str] = set()
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
        category = str(d.get("category") or "unknown")
        entry = {
            "decision_id": f"wa-{start + len(to_append):03d}",
            "stage": stage,
            "category": category,
            "subject": d.get("subject", f"{stage} decision"),
            "options_considered": d.get("options_considered") or default_options,
            "selected": d.get("selected") or "approved",
            "reason": reason,
            "user_visible": True,
            "user_approved": True,
        }
        gf = {category} if category not in _DECISION_CATEGORY_ENUM else set()
        try:
            validate_decision_entry(
                project_id, entry, grandfather_categories=gf or None,
            )
        except Exception as exc:
            # 结构烂掉（缺 options 等）——不能静默 skip 后 completed，否则必 drift。
            skipped.append(f"{d.get('decision_id')}({category}): {str(exc)[:120]}")
            continue
        if gf:
            grandfather |= gf
        to_append.append(entry)

    if not to_append and not skipped:
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
    return to_append, skipped, grandfather


def repair_approval_drift(project_dir: Path, stage: str, *, notes: str = "") -> dict:
    """对已是 completed+human_approved 的阶段补写镜像决策，清掉 approval_gate_drift。

    用于历史 bug（批准时 skip 非法 category 却仍 completed）的修复；不改 checkpoint。
    """
    from plugins.openmontage.lib.checkpoint import read_checkpoint
    from plugins.openmontage.lib.decision_log import append_decisions
    from plugins.openmontage.lib.production_audit import check_approval_gate_drift

    project_id = project_dir.name
    cp = read_checkpoint(PROJECTS_DIR, project_id, stage)
    if not cp or cp.get("status") != "completed" or not cp.get("human_approved"):
        raise StageRunError(
            f"阶段 {stage!r} 不是 completed+human_approved，不能用 repair_approval_drift"
        )

    reason = notes or "补镜像：修复批准时未清账的 decision_log（approval_gate_drift）"
    to_append, skipped, grandfather = _approval_mirror(project_dir, stage, reason)
    if skipped:
        raise StageRunError(
            f"无法修复 stage={stage!r} 的 drift：{skipped}",
            diagnostics={"unmirrored_decisions": skipped},
        )

    # 仅有 human_approval 占位且无待批键时不写噪音
    real = [
        e for e in to_append
        if not (
            e.get("category") == "human_approval"
            and e.get("subject") == f"{stage} approval"
            and len(to_append) == 1
            and not grandfather
        )
    ]
    if not real:
        findings = check_approval_gate_drift(project_dir)
        drift = [f for f in findings if f.get("stage") == stage]
        return {
            "ok": True,
            "stage": stage,
            "repaired": 0,
            "message": "无需补写",
            "drift_remaining": drift,
        }

    append_decisions(
        project_id,
        real,
        grandfather_categories=grandfather or None,
    )
    findings = check_approval_gate_drift(project_dir)
    drift = [f for f in findings if f.get("stage") == stage]
    return {
        "ok": True,
        "stage": stage,
        "repaired": len(real),
        "mirrored_ids": [e.get("decision_id") for e in real],
        "drift_remaining": drift,
    }


def _revision_count(project_dir: Path, stage: str) -> int:
    from plugins.openmontage.lib.decision_log import load_decision_log

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
    from plugins.openmontage.lib.checkpoint import get_next_stage, read_checkpoint, write_checkpoint
    from plugins.openmontage.lib.decision_log import append_decisions, suggest_next_decision_id
    from plugins.openmontage.lib.pipeline_loader import load_pipeline_readonly

    project_id = project_dir.name
    log.info("reject.request project=%s stage=%s", project_id, stage)
    try:
        _require_not_busy(project_dir)
    except StageBusyError as exc:
        log.warning(
            "reject.rejected project=%s stage=%s reason=busy: %s",
            project_id, stage, exc,
        )
        raise

    cp = read_checkpoint(PROJECTS_DIR, project_id, stage)
    if not cp or cp.get("status") != "awaiting_human":
        log.warning(
            "reject.rejected project=%s stage=%s reason=not_awaiting status=%s",
            project_id, stage, (cp or {}).get("status"),
        )
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
    log.info(
        "reject.done project=%s stage=%s revision=%d/%d next=%s",
        project_id, stage, count + 1, limit, next_stage,
    )
    return {
        "ok": True,
        "stage": stage,
        "status": "in_progress",
        "revision_count": count + 1,
        "next_stage": next_stage,
    }


def run_state_for_board(project_dir: Path) -> list[dict]:
    """BoardState 注入：每阶段最新一条运行摘要（含 log_tail 供 UI 预览）。"""
    _reconcile_lock(project_dir)
    # 全局最近若干条里，每个 stage 只保留最新一条，便于已完成阶段也能点「查看运行日志」
    latest_by_stage: list[dict] = []
    seen_stages: set[str] = set()
    for r in _list_runs(project_dir, limit=KEEP_RUNS):
        stage = str(r.get("stage") or "").strip()
        if not stage or stage in seen_stages:
            continue
        seen_stages.add(stage)
        latest_by_stage.append(
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
        )
    runs = latest_by_stage
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
    return runs
