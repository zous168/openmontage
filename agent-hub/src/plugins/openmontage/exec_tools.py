"""OpenMontage 的执行面工具：跑阶段、轮询、写决策。

**为什么是异步 job 而不是同步调用。** 一个阶段动辄跑几分钟到几十分钟
（Remotion 渲染、视频生成 API 轮询、本地扩散模型）。同步阻塞会让对话卡死，
也会撞上 LLM 的工具调用超时。所以 ``om_run`` 立刻返回 task_id，
``om_job`` 负责轮询 —— 大脑可以在等待期间继续跟用户说话。

复用 ``backlot.stage_runner`` 而不是另起一套：审批门、并发锁、阶段顺序校验、
驳回重跑都已经在那里实现且被契约测试覆盖。这里只做协议转换。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from plugins.openmontage.bridge import _error, _json


def _project_dir(project_id: str):
    from plugins.openmontage.lib.paths import PROJECTS_DIR

    return PROJECTS_DIR / project_id


# ─── om_run ──────────────────────────────────────────────────────────

OM_RUN_SCHEMA = {
    "name": "om_run",
    "description": (
        "启动 OpenMontage 项目的下一个阶段（或指定阶段的重跑）。"
        "立即返回 task_id —— 阶段是分钟级的，用 om_job 轮询进度，"
        "不要原地等待。stage 必须等于当前 next_stage，跳阶段会被拒绝。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "项目 id"},
            "stage": {
                "type": "string",
                "description": "阶段名。省略则跑 next_stage。传入值必须与 next_stage 一致",
            },
            "feedback": {
                "type": "string",
                "description": "驳回后重跑时给 agent 的修改意见",
            },
        },
        "required": ["project_id"],
    },
}


def handle_run(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id = str(args.get("project_id") or "").strip()
    if not project_id:
        return _error("缺少 project_id")

    project_dir = _project_dir(project_id)
    if not (project_dir / "project.json").is_file():
        return _error(f"项目不存在或未初始化: {project_id}")

    from plugins.openmontage.backlot import stage_runner

    try:
        task = stage_runner.prepare_stage_run(
            project_dir,
            stage=str(args.get("stage") or "").strip() or None,
            feedback=str(args.get("feedback") or "").strip() or None,
        )
    except stage_runner.StageRunError as exc:
        # 契约违规（跳阶段、锁冲突、manifest 缺失）——原样回传，不要粉饰。
        return _error(str(exc), project_id=project_id)
    except Exception as exc:
        return _error(f"启动失败: {exc}", project_id=project_id)

    # prepare 已完成校验与加锁，spawn 交给事件循环后台跑。
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is not None:
        loop.create_task(stage_runner.run_task(task))
        spawned = True
    else:
        # 无事件循环（同步宿主）：调用方需要自己驱动，如实告知而不是假装已启动。
        spawned = False

    return _json(
        {
            "ok": True,
            "task_id": task.task_id,
            "project_id": project_id,
            "stage": task.stage,
            "spawned": spawned,
            "next": "用 om_job 轮询该 task_id；阶段完成后若配置了审批门会停在 awaiting_human",
        }
    )


# ─── om_job ──────────────────────────────────────────────────────────

OM_JOB_SCHEMA = {
    "name": "om_job",
    "description": (
        "轮询 OpenMontage 阶段任务的状态与日志尾部。"
        "省略 task_id 则返回该项目最近的运行摘要。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "项目 id"},
            "task_id": {"type": "string", "description": "om_run 返回的 task_id"},
            "log_offset": {
                "type": "integer",
                "description": "从第几行开始取日志（默认从头），配合返回的 next_offset 增量拉取",
            },
            "log_limit": {"type": "integer", "description": "最多取多少行日志（默认 80）"},
        },
        "required": ["project_id"],
    },
}


def handle_job(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id = str(args.get("project_id") or "").strip()
    if not project_id:
        return _error("缺少 project_id")

    project_dir = _project_dir(project_id)
    if not project_dir.is_dir():
        return _error(f"项目不存在: {project_id}")

    from plugins.openmontage.backlot import stage_runner

    task_id = str(args.get("task_id") or "").strip()
    if not task_id:
        try:
            return _json({"ok": True, "runs": stage_runner.list_runs(project_dir)})
        except Exception as exc:
            return _error(f"读取运行列表失败: {exc}")

    try:
        payload = stage_runner.read_run_log(
            project_dir,
            task_id,
            offset=int(args.get("log_offset") or 0),
            limit=int(args.get("log_limit") or 80),
        )
    except FileNotFoundError:
        return _error(f"未找到任务: {task_id}")
    except Exception as exc:
        return _error(f"读取任务日志失败: {exc}")
    return _json({"ok": True, "task_id": task_id, **payload})


# ─── om_state ────────────────────────────────────────────────────────

OM_STATE_SCHEMA = {
    "name": "om_state",
    "description": (
        "写入 OpenMontage 的项目状态：批准/驳回当前阶段，或追加决策记录。"
        "决策日志是 append-only 的审计轨迹 —— 用户拍板的每个选择都要落这里，"
        "后续阶段和复盘都靠它。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "项目 id"},
            "action": {
                "type": "string",
                "enum": ["approve", "reject", "append_decisions"],
                "description": "approve=通过审批门续跑；reject=打回并附修改意见；append_decisions=记录用户拍板",
            },
            "stage": {"type": "string", "description": "approve / reject 的目标阶段"},
            "notes": {"type": "string", "description": "approve 时的备注"},
            "feedback": {"type": "string", "description": "reject 时的修改意见（必填）"},
            "decisions": {
                "type": "array",
                "description": "append_decisions 的决策数组，每项含 decision_id、stage、choice、rationale",
                "items": {"type": "object"},
            },
        },
        "required": ["project_id", "action"],
    },
}


def handle_state(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id = str(args.get("project_id") or "").strip()
    action = str(args.get("action") or "").strip()
    if not project_id:
        return _error("缺少 project_id")

    project_dir = _project_dir(project_id)
    if not project_dir.is_dir():
        return _error(f"项目不存在: {project_id}")

    if action == "append_decisions":
        decisions = args.get("decisions")
        if not isinstance(decisions, list) or not decisions:
            return _error("append_decisions 需要非空的 decisions 数组")
        from plugins.openmontage.lib.decision_log import append_decisions

        try:
            path = append_decisions(project_id, decisions)
        except Exception as exc:
            return _error(f"写入决策日志失败: {exc}")
        return _json({"ok": True, "action": action, "decision_log": str(path)})

    stage = str(args.get("stage") or "").strip()
    if not stage:
        return _error(f"{action} 需要 stage")

    from plugins.openmontage.backlot import stage_runner

    if action == "approve":
        try:
            result = stage_runner.approve_stage(
                project_dir, stage, notes=str(args.get("notes") or "")
            )
        except Exception as exc:
            return _error(f"批准失败: {exc}")
        return _json({"ok": True, "action": action, **_as_dict(result)})

    if action == "reject":
        feedback = str(args.get("feedback") or "").strip()
        if not feedback:
            # 无反馈的驳回等于让 agent 盲改，必然烧一轮。
            return _error("reject 必须给 feedback，说明哪里不行、期望改成什么样")
        try:
            result = stage_runner.reject_stage(project_dir, stage, feedback=feedback)
        except Exception as exc:
            return _error(f"驳回失败: {exc}")
        return _json({"ok": True, "action": action, **_as_dict(result)})

    return _error(f"未知 action: {action}")


def _as_dict(value: Any) -> dict:
    if isinstance(value, dict):
        return value
    try:
        return json.loads(json.dumps(value, default=str))
    except Exception:
        return {"result": str(value)}


EXEC_TOOLS = (
    ("om_run", OM_RUN_SCHEMA, handle_run),
    ("om_job", OM_JOB_SCHEMA, handle_job),
    ("om_state", OM_STATE_SCHEMA, handle_state),
)
