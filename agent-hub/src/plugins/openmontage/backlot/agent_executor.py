"""In-process Hermes AIAgent executor for Backlot stage runs.

Replaces the former Claude Code CLI subprocess spawn. The agent runs in a
worker thread (``run_conversation`` is synchronous) so the asyncio event loop
stays free for heartbeats, timeouts, and cancel via ``agent.interrupt()``.

Run log events are written as NDJSON in the same Claude stream-json *shape*
that ``stage_runner.render_run_log`` / the board UI already understand
(``system`` / ``assistant`` / ``user`` / ``result``).
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from plugins.openmontage.lib.paths import REPO_ROOT

log = logging.getLogger("backlot.stage.agent")

LogAppend = Callable[[dict[str, Any]], None]

# 无头 stage 开放：
# - openmontage_stage → om_registry / om_checkpoint / om_artifact_* / om_decision_append
# - web → Hermes 通用 web_search / web_extract（研究等阶段必需；不另造 OM 包装）
# - skills_view → 必要时只读 skill_view（导演全文已在 prompt）
# 故意不含：file、terminal、execute_code、编排用 openmontage(om_run/om_job)…
_HEADLESS_STAGE_TOOLSET_ORDER: tuple[str, ...] = (
    "openmontage_stage",
    "web",
    "skills_view",
)


def _filter_stage_toolsets(enabled_toolsets: list[str]) -> list[str]:
    """兼容旧名：解析无头 stage 最终启用的 toolset 列表。"""
    return _resolve_stage_toolsets(enabled_toolsets)


def _resolve_stage_toolsets(available_toolsets: list[str] | None = None) -> list[str]:
    """无头 stage：固定 allowlist（不依赖平台 cli 是否列出插件 toolset）。

    ``openmontage_stage`` 由插件动态注册，常不在 ``platform_toolsets.cli`` 里；
    若再与平台配置取交集会被静默丢掉。编排用 ``openmontage`` 永不进入此面。
    """
    from plugins.openmontage.bridge import TOOLSET as OM_TOOLSET

    chosen = list(_HEADLESS_STAGE_TOOLSET_ORDER)
    if OM_TOOLSET in chosen:
        chosen = [ts for ts in chosen if ts != OM_TOOLSET]
    # available_toolsets 仅作可观测性；不裁剪固定面
    _ = available_toolsets
    return chosen


def _tool_result_text(result: Any) -> str:
    if result is None:
        return ""
    if isinstance(result, dict) and result.get("_multimodal"):
        parts = []
        for block in result.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "\n".join(parts) if parts else str(result)
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(result)
    return str(result)


def _make_log_append(log_fh: Any, lock: threading.Lock) -> LogAppend:
    """Append one NDJSON event to the run log (binary or text file handle)."""

    def append(event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False) + "\n"
        data = line.encode("utf-8")
        with lock:
            try:
                if hasattr(log_fh, "buffer"):
                    log_fh.buffer.write(data)
                    log_fh.flush()
                else:
                    log_fh.write(data)
                    if hasattr(log_fh, "flush"):
                        log_fh.flush()
            except OSError as exc:
                log.debug("run log write failed: %s", exc)

    return append


def _auto_approve_callback(append: LogAppend):
    """Dangerous-tool approval: never block; audit to the run log."""

    def callback(command: str, description: str, *, allow_permanent: bool = True) -> str:
        append({
            "type": "system",
            "subtype": "approval",
            "decision": "auto-approved",
            "description": description,
            "command": (command or "")[:500],
        })
        return "once"

    return callback


def _clarify_callback(question: str, choices=None) -> str:
    if choices:
        return (
            f"[backlot headless: no user available. Pick the best option from "
            f"{choices} using your own judgment and continue.]"
        )
    return (
        "[backlot headless: no user available. Make the most reasonable "
        "assumption you can and continue.]"
    )


def _build_agent(
    *,
    session_id: str,
    append: LogAppend,
    text_buf: list[str],
    text_lock: threading.Lock,
) -> Any:
    from run_agent import AIAgent
    from gateway.run import (
        _resolve_runtime_agent_kwargs,
        _resolve_gateway_model,
        _load_gateway_config,
        GatewayRunner,
    )
    from hermes_cli.tools_config import _get_platform_tools
    from plugins.openmontage.lib.tool_log import (
        summarize_tool_call,
        truncate_tool_result_body,
    )

    runtime_kwargs = _resolve_runtime_agent_kwargs()
    reasoning_config = GatewayRunner._load_reasoning_config()
    model = _resolve_gateway_model()
    user_config = _load_gateway_config()
    # 平台配置只作「哪些 toolset 本机开了」的交集来源；最终面由
    # _resolve_stage_toolsets allowlist 决定（不是整份 cli）。
    platform_toolsets = sorted(_get_platform_tools(user_config, "cli"))
    if not platform_toolsets:
        platform_toolsets = sorted(_get_platform_tools(user_config, "api_server"))
    enabled_toolsets = _resolve_stage_toolsets(platform_toolsets)
    log.info("headless stage toolsets=%s", enabled_toolsets)

    max_iterations = int(os.getenv("HERMES_MAX_ITERATIONS", "90"))
    fallback_model = GatewayRunner._load_fallback_model()

    def on_delta(delta: str) -> None:
        if not delta:
            return
        with text_lock:
            text_buf.append(delta)

    def flush_text() -> None:
        with text_lock:
            text = "".join(text_buf).strip()
            text_buf.clear()
        if text:
            append({
                "type": "assistant",
                "message": {"content": [{"type": "text", "text": text}]},
            })

    def on_tool_start(tool_id: str, name: str, args: Any) -> None:
        flush_text()
        append({
            "type": "assistant",
            "message": {
                "content": [{
                    "type": "tool_use",
                    "id": tool_id,
                    "name": name or "tool",
                    "input": args if isinstance(args, dict) else {"value": args},
                }],
            },
        })

    def on_tool_complete(tool_id: str, name: str, args: Any, result: Any) -> None:
        body = _tool_result_text(result)
        is_error = False
        if isinstance(result, dict) and result.get("error"):
            is_error = True
        lower = body[:80].lower()
        if lower.startswith("error") or "blocked:" in lower:
            is_error = True

        # Skim line in the same runs/*.log (does not replace events.jsonl audit).
        action = summarize_tool_call(name or "tool", args, body, is_error=is_error)
        append({
            "type": "system",
            "subtype": "tool_action",
            "tool": action.get("tool"),
            "ok": action.get("ok"),
            "label": action.get("label"),
            "summary": action.get("summary"),
            "detail": action.get("detail") or {},
            "tool_use_id": tool_id,
        })

        append({
            "type": "user",
            "message": {
                "content": [{
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": truncate_tool_result_body(body),
                    "is_error": is_error,
                }],
            },
        })

    agent = AIAgent(
        model=model,
        **runtime_kwargs,
        max_iterations=max_iterations,
        quiet_mode=True,
        verbose_logging=False,
        enabled_toolsets=enabled_toolsets,
        session_id=session_id,
        platform="cli",
        stream_delta_callback=on_delta,
        tool_start_callback=on_tool_start,
        tool_complete_callback=on_tool_complete,
        clarify_callback=_clarify_callback,
        fallback_model=fallback_model,
        reasoning_config=reasoning_config,
    )
    # Attach flush helper for end-of-run (attribute, not ctor kw).
    agent._backlot_flush_text = flush_text  # type: ignore[attr-defined]
    return agent


def run_agent_conversation(
    prompt: str,
    *,
    task_id: str,
    log_fh: Any,
    agent_holder: list,
    project_cwd: Optional[Path] = None,
    project_id: Optional[str] = None,
    stage: Optional[str] = None,
    on_agent_ready: Optional[Callable[[Any], None]] = None,
) -> dict[str, Any]:
    """Synchronously build AIAgent and run one conversation.

    Designed to be called from ``asyncio.to_thread`` / ``run_in_executor``.
    Stores the live agent at ``agent_holder[0]`` (and via ``on_agent_ready``)
    so callers can ``interrupt()`` as soon as construction finishes.

    Returns a result dict with at least ``exit_code`` (0 = normal finish /
    interrupt handled by caller; 1 = hard failure).
    """
    lock = threading.Lock()
    append = _make_log_append(log_fh, lock)
    text_buf: list[str] = []
    text_lock = threading.Lock()
    cwd = Path(project_cwd or REPO_ROOT)
    session_id = f"backlot-{task_id}-{uuid.uuid4().hex[:8]}"
    started = time.time()

    # Non-interactive: never hang on approvals / shell hooks.
    prev_yolo = os.environ.get("HERMES_YOLO_MODE")
    prev_hooks = os.environ.get("HERMES_ACCEPT_HOOKS")
    prev_headless = os.environ.get("OPENMONTAGE_HEADLESS_STAGE")
    prev_project = os.environ.get("OPENMONTAGE_HEADLESS_PROJECT")
    prev_stage = os.environ.get("OPENMONTAGE_HEADLESS_STAGE_NAME")
    os.environ["HERMES_YOLO_MODE"] = "1"
    os.environ["HERMES_ACCEPT_HOOKS"] = "1"
    # Skip interactive session-brief injection (om_run/om_job polling guidance).
    os.environ["OPENMONTAGE_HEADLESS_STAGE"] = "1"
    if project_id:
        os.environ["OPENMONTAGE_HEADLESS_PROJECT"] = str(project_id)
    if stage:
        os.environ["OPENMONTAGE_HEADLESS_STAGE_NAME"] = str(stage)

    approval_token = None
    prev_cwd = None
    try:
        from tools.approval import (
            enable_session_yolo,
            set_current_session_key,
            reset_current_session_key,
        )
        from tools.terminal_tool import set_approval_callback

        approval_token = set_current_session_key(session_id)
        enable_session_yolo(session_id)
        set_approval_callback(_auto_approve_callback(append))
    except Exception as exc:
        log.warning("approval wiring failed (continuing): %s", exc)

    try:
        prev_cwd = os.getcwd()
        os.chdir(str(cwd))
    except OSError as exc:
        log.warning("chdir(%s) failed: %s", cwd, exc)
        prev_cwd = None

    try:
        agent = _build_agent(
            session_id=session_id,
            append=append,
            text_buf=text_buf,
            text_lock=text_lock,
        )
        agent_holder.clear()
        agent_holder.append(agent)
        if on_agent_ready is not None:
            try:
                on_agent_ready(agent)
            except Exception:
                log.debug("on_agent_ready failed", exc_info=True)

        model_name = getattr(agent, "model", None) or "?"
        append({
            "type": "system",
            "subtype": "init",
            "model": model_name,
            "session_id": session_id,
            "cwd": str(cwd),
            "project_id": project_id,
            "stage": stage,
        })

        result = agent.run_conversation(
            user_message=prompt,
            conversation_history=None,
            task_id=task_id,
        ) or {}

        flush = getattr(agent, "_backlot_flush_text", None)
        if callable(flush):
            flush()

        duration_ms = int((time.time() - started) * 1000)
        interrupted = bool(result.get("interrupted"))
        completed = result.get("completed")
        final = (result.get("final_response") or "").strip()
        subtype = "success"
        exit_code = 0
        if interrupted:
            subtype = "interrupted"
        elif completed is False:
            subtype = "error"
            exit_code = 1

        append({
            "type": "result",
            "subtype": subtype,
            "duration_ms": duration_ms,
            "result": final[:4000],
            "interrupted": interrupted,
            "completed": completed,
        })
        return {
            "exit_code": exit_code,
            "interrupted": interrupted,
            "completed": completed,
            "final_response": final,
            "result": result,
        }
    except Exception as exc:
        log.exception("backlot agent run failed task=%s", task_id)
        append({
            "type": "result",
            "subtype": "error",
            "duration_ms": int((time.time() - started) * 1000),
            "result": f"agent failed: {exc}",
        })
        # Non-JSON diagnostic line for operators (render_run_log preserves it).
        with lock:
            try:
                msg = f"agent exception: {type(exc).__name__}: {exc}\n".encode("utf-8")
                if hasattr(log_fh, "buffer"):
                    log_fh.buffer.write(msg)
                else:
                    log_fh.write(msg)
            except OSError:
                pass
        return {
            "exit_code": 1,
            "interrupted": False,
            "completed": False,
            "error": str(exc),
        }
    finally:
        try:
            from tools.terminal_tool import set_approval_callback
            set_approval_callback(None)
        except Exception:
            pass
        if approval_token is not None:
            try:
                from tools.approval import reset_current_session_key, clear_session
                clear_session(session_id)
                reset_current_session_key(approval_token)
            except Exception:
                pass
        if prev_cwd is not None:
            try:
                os.chdir(prev_cwd)
            except OSError:
                pass
        if prev_yolo is None:
            os.environ.pop("HERMES_YOLO_MODE", None)
        else:
            os.environ["HERMES_YOLO_MODE"] = prev_yolo
        if prev_hooks is None:
            os.environ.pop("HERMES_ACCEPT_HOOKS", None)
        else:
            os.environ["HERMES_ACCEPT_HOOKS"] = prev_hooks
        if prev_headless is None:
            os.environ.pop("OPENMONTAGE_HEADLESS_STAGE", None)
        else:
            os.environ["OPENMONTAGE_HEADLESS_STAGE"] = prev_headless
        if prev_project is None:
            os.environ.pop("OPENMONTAGE_HEADLESS_PROJECT", None)
        else:
            os.environ["OPENMONTAGE_HEADLESS_PROJECT"] = prev_project
        if prev_stage is None:
            os.environ.pop("OPENMONTAGE_HEADLESS_STAGE_NAME", None)
        else:
            os.environ["OPENMONTAGE_HEADLESS_STAGE_NAME"] = prev_stage


async def execute_stage_agent(task: Any, log_fh: Any) -> int:
    """Async seam used by ``run_task`` (and tests).

    Runs ``run_agent_conversation`` in a worker thread. Stores the live
    AIAgent on ``task.agent`` for cancel/timeout via ``interrupt()``.
    Returns a process-style exit code (0 ok, non-zero failure).
    """
    import asyncio

    holder: list = []
    task.agent_holder = holder  # type: ignore[attr-defined]

    def _on_ready(agent: Any) -> None:
        task.agent = agent

    def _run() -> dict[str, Any]:
        return run_agent_conversation(
            task.prompt,
            task_id=task.task_id,
            log_fh=log_fh,
            agent_holder=holder,
            project_cwd=REPO_ROOT,
            project_id=getattr(task, "project_id", None),
            stage=getattr(task, "stage", None),
            on_agent_ready=_on_ready,
        )

    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(None, _run)
    return int(result.get("exit_code") or 0)
