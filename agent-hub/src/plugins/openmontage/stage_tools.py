"""无头 stage 专用 Hermes 工具面（toolset ``openmontage_stage``）。

与编排大脑的 ``openmontage``（om_run / om_job / om_state）刻意拆开：
无头 agent 只拿 registry / checkpoint / 产物 I/O，不拿编排轮询工具。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from plugins.openmontage.bridge import _error, _json

TOOLSET = "openmontage_stage"

# 允许写入的项目相对子树（禁止 checkpoint / decision_log / lock / runs）
_WRITE_ALLOW_PREFIXES = (
    "artifacts/",
    "assets/",
    "renders/",
    "exports/",
    "scratch/",
)

_WRITE_DENY_NAMES = frozenset({
    "decision_log.json",
    ".run.lock",
    "project.json",
})


def _env_project_id() -> str:
    return str(os.environ.get("OPENMONTAGE_HEADLESS_PROJECT") or "").strip()


def _env_stage_name() -> str:
    return str(os.environ.get("OPENMONTAGE_HEADLESS_STAGE_NAME") or "").strip()


def _resolve_project_id(args: dict[str, Any]) -> tuple[str | None, str | None]:
    """返回 (project_id, error)。显式 project_id 必须与无头运行中项目一致。"""
    env_pid = _env_project_id()
    arg_pid = str(args.get("project_id") or "").strip()
    if env_pid and arg_pid and arg_pid != env_pid:
        return None, (
            f"project_id={arg_pid!r} 与当前无头运行项目 {env_pid!r} 不一致"
        )
    pid = env_pid or arg_pid
    if not pid:
        return None, "缺少 project_id（无头运行应设置 OPENMONTAGE_HEADLESS_PROJECT）"
    return pid, None


def _project_dir(project_id: str) -> Path:
    from plugins.openmontage.lib.paths import PROJECTS_DIR

    return PROJECTS_DIR / project_id


def _tool_result_payload(result: Any) -> dict[str, Any]:
    """把 BaseTool.ToolResult 收成可 JSON 的 dict。"""
    if result is None:
        return {"success": False, "error": "empty ToolResult"}
    if isinstance(result, dict):
        return result
    success = bool(getattr(result, "success", False))
    payload: dict[str, Any] = {
        "success": success,
        "data": getattr(result, "data", None) or {},
        "artifacts": list(getattr(result, "artifacts", None) or []),
        "cost_usd": getattr(result, "cost_usd", 0.0) or 0.0,
        "duration_seconds": getattr(result, "duration_seconds", 0.0) or 0.0,
    }
    err = getattr(result, "error", None)
    if err:
        payload["error"] = str(err)
    model = getattr(result, "model", None)
    if model:
        payload["model"] = model
    seed = getattr(result, "seed", None)
    if seed is not None:
        payload["seed"] = seed
    return payload


def _stage_tools_available(project_id: str, stage: str) -> list[str] | None:
    """返回当前 stage 的 tools_available；None 表示无法解析 / 不限制。"""
    if not stage:
        return None
    try:
        from plugins.openmontage.lib.checkpoint import read_checkpoint
        from plugins.openmontage.lib.paths import PROJECTS_DIR
        from plugins.openmontage.lib.pipeline_loader import load_pipeline_readonly

        marker = _project_dir(project_id) / "project.json"
        pipeline_type = ""
        if marker.is_file():
            try:
                pipeline_type = str(
                    json.loads(marker.read_text(encoding="utf-8")).get("pipeline_type") or ""
                )
            except (OSError, json.JSONDecodeError):
                pipeline_type = ""
        if not pipeline_type:
            cp = read_checkpoint(PROJECTS_DIR, project_id, stage) or {}
            pipeline_type = str(cp.get("pipeline_type") or "")
        if not pipeline_type:
            return None
        manifest = load_pipeline_readonly(pipeline_type)
        block = next(
            (s for s in (manifest.get("stages") or []) if s.get("name") == stage),
            {},
        )
        tools = [
            str(t) for t in (block.get("tools_available") or [])
            if isinstance(t, str) and t.strip()
        ]
        return tools  # 可能为空列表 = 不硬拦
    except Exception:
        return None


def _safe_rel_path(project_id: str, rel: str) -> tuple[Path | None, str | None]:
    """解析项目相对路径；拒绝逃逸。"""
    raw = (rel or "").strip().replace("\\", "/")
    if not raw:
        return None, "缺少 path"
    # 允许 projects/<id>/... 前缀（prompt 里常见）
    prefix = f"projects/{project_id}/"
    if raw.startswith(prefix):
        raw = raw[len(prefix):]
    if raw.startswith("/"):
        return None, "路径必须是项目相对路径"
    if ".." in raw.split("/"):
        return None, "路径不允许 '..'"
    root = _project_dir(project_id).resolve()
    target = (root / raw).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return None, "路径逃逸出项目目录"
    return target, None


# ─── om_registry ─────────────────────────────────────────────────────

OM_REGISTRY_SCHEMA = {
    "name": "om_registry",
    "description": (
        "调用 OpenMontage 注册表工具（BaseTool）。"
        "action=execute 时传 tool + params；"
        "action=menu/catalog 做轻量能力预检。"
        "禁止用 terminal / execute_code / python -c 绕道。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "项目 id（无头运行可省略，取自环境）",
            },
            "action": {
                "type": "string",
                "enum": ["execute", "menu", "catalog"],
                "description": "execute=跑工具；menu/catalog=预检",
            },
            "tool": {
                "type": "string",
                "description": "注册表工具名，如 video_compose、tts_selector",
            },
            "params": {
                "type": "object",
                "description": "传给 BaseTool.execute 的参数字典",
            },
            "label": {
                "type": "string",
                "description": "3–8 字，说明这一次在做什么",
            },
        },
        "required": ["action", "label"],
    },
}


def handle_registry(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id, err = _resolve_project_id(args)
    if err:
        return _error(err)
    assert project_id is not None

    action = str(args.get("action") or "execute").strip().lower()
    from plugins.openmontage.bridge import _get_registry

    registry = _get_registry()

    if action == "menu":
        return _json({
            "ok": True,
            "action": "menu",
            "project_id": project_id,
            "menu": registry.provider_menu_summary(),
        })
    if action == "catalog":
        return _json({
            "ok": True,
            "action": "catalog",
            "project_id": project_id,
            "catalog": registry.capability_catalog(),
        })
    if action != "execute":
        return _error(f"未知 action: {action!r}", allowed=["execute", "menu", "catalog"])

    tool_name = str(args.get("tool") or "").strip()
    if not tool_name:
        return _error("action=execute 需要 tool")

    stage = _env_stage_name()
    allowed = _stage_tools_available(project_id, stage)
    if allowed:  # 非空名单才硬拦
        if tool_name not in allowed:
            return _error(
                f"工具 {tool_name!r} 不在本阶段 tools_available 内",
                stage=stage,
                tools_available=allowed,
            )

    params = args.get("params")
    if params is None:
        params = {}
    if not isinstance(params, dict):
        return _error("params 必须是对象")

    # 常见约定：许多工具要 project_id
    if "project_id" not in params:
        params = {**params, "project_id": project_id}

    result = registry.execute(tool_name, params)
    payload = _tool_result_payload(result)
    return _json({
        "ok": bool(payload.get("success")),
        "action": "execute",
        "project_id": project_id,
        "tool": tool_name,
        "result": payload,
    })


# ─── om_checkpoint ───────────────────────────────────────────────────

OM_CHECKPOINT_SCHEMA = {
    "name": "om_checkpoint",
    "description": (
        "写入阶段 checkpoint（唯一合法写路径）。"
        "status: in_progress | awaiting_human | completed | failed。"
        "门控阶段完成用 awaiting_human，不要写 completed+human_approved=false。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "stage": {
                "type": "string",
                "description": "阶段名；无头运行可省略，取自环境",
            },
            "status": {
                "type": "string",
                "enum": ["in_progress", "awaiting_human", "completed", "failed"],
            },
            "artifacts": {
                "type": "object",
                "description": "规范产物字典；in_progress 可为 {}",
            },
            "error": {"type": "string", "description": "失败原因（≤400 字）"},
            "metadata": {"type": "object"},
            "pipeline_type": {"type": "string"},
            "human_approved": {"type": "boolean"},
            "label": {"type": "string"},
        },
        "required": ["status", "label"],
    },
}


def handle_checkpoint(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id, err = _resolve_project_id(args)
    if err:
        return _error(err)
    assert project_id is not None

    stage = str(args.get("stage") or "").strip() or _env_stage_name()
    if not stage:
        return _error("缺少 stage")

    status = str(args.get("status") or "").strip()
    if status not in ("in_progress", "awaiting_human", "completed", "failed"):
        return _error(f"非法 status: {status!r}")

    artifacts = args.get("artifacts")
    if artifacts is None:
        artifacts = {}
    if not isinstance(artifacts, dict):
        return _error("artifacts 必须是对象")

    from plugins.openmontage.lib.checkpoint import (
        CheckpointValidationError,
        write_checkpoint,
    )
    from plugins.openmontage.lib.paths import PROJECTS_DIR

    pipeline_type = str(args.get("pipeline_type") or "").strip() or None
    if not pipeline_type:
        marker = _project_dir(project_id) / "project.json"
        if marker.is_file():
            try:
                pipeline_type = json.loads(marker.read_text(encoding="utf-8")).get(
                    "pipeline_type"
                )
            except (OSError, json.JSONDecodeError):
                pipeline_type = None

    error = str(args.get("error") or "").strip() or None
    if error and len(error) > 400:
        error = error[:400]
    metadata = args.get("metadata") if isinstance(args.get("metadata"), dict) else None
    human_approved = bool(args.get("human_approved") or False)

    try:
        path = write_checkpoint(
            PROJECTS_DIR,
            project_id,
            stage,
            status,
            artifacts,
            pipeline_type=pipeline_type,
            human_approved=human_approved,
            error=error,
            metadata=metadata,
        )
    except CheckpointValidationError as exc:
        return _error(str(exc), code="checkpoint_validation")
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")

    return _json({
        "ok": True,
        "project_id": project_id,
        "stage": stage,
        "status": status,
        "path": str(path),
    })


# ─── om_artifact_read ────────────────────────────────────────────────

OM_ARTIFACT_READ_SCHEMA = {
    "name": "om_artifact_read",
    "description": (
        "读取当前项目内产物（artifacts/ 或其它项目相对路径）。"
        "用 artifact 名（如 research_brief）或相对 path；禁止读仓库源码。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "artifact": {
                "type": "string",
                "description": "规范产物名 → artifacts/<name>.json",
            },
            "path": {
                "type": "string",
                "description": "项目相对路径（与 artifact 二选一）",
            },
            "label": {"type": "string"},
        },
        "required": ["label"],
    },
}


def handle_artifact_read(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id, err = _resolve_project_id(args)
    if err:
        return _error(err)
    assert project_id is not None

    artifact = str(args.get("artifact") or "").strip()
    path_arg = str(args.get("path") or "").strip()
    if artifact and path_arg:
        return _error("artifact 与 path 只能传一个")
    if not artifact and not path_arg:
        return _error("需要 artifact 或 path")

    if artifact:
        if "/" in artifact or "\\" in artifact or artifact.endswith(".json"):
            return _error("artifact 应为规范名（不含路径/后缀），如 research_brief")
        rel = f"artifacts/{artifact}.json"
    else:
        rel = path_arg

    target, path_err = _safe_rel_path(project_id, rel)
    if path_err:
        return _error(path_err)
    assert target is not None

    # 拒绝读 checkpoint / runs / lock（进度走编排通道；无头用 om_checkpoint 写）
    name = target.name.lower()
    rel_norm = str(target.relative_to(_project_dir(project_id).resolve())).replace("\\", "/")
    if (
        name.startswith("checkpoint")
        or name == ".run.lock"
        or rel_norm.startswith("runs/")
        or rel_norm.startswith("checkpoints/")
    ):
        return _error(
            "禁止直接读 checkpoint / runs / .run.lock；"
            "写状态用 om_checkpoint，读产物用 artifacts/"
        )

    if not target.is_file():
        return _error(f"文件不存在: {rel_norm}", path=rel_norm)

    try:
        text = target.read_text(encoding="utf-8")
    except OSError as exc:
        return _error(f"读取失败: {exc}")

    # JSON 尽量解析
    data: Any
    try:
        data = json.loads(text)
        kind = "json"
    except json.JSONDecodeError:
        data = text
        kind = "text"

    return _json({
        "ok": True,
        "project_id": project_id,
        "path": rel_norm,
        "kind": kind,
        "content": data,
        "bytes": target.stat().st_size,
    })


# ─── om_artifact_write ───────────────────────────────────────────────

OM_ARTIFACT_WRITE_SCHEMA = {
    "name": "om_artifact_write",
    "description": (
        "写入项目允许子树：artifacts/、assets/、renders/、exports/、scratch/。"
        "禁止写 checkpoint、decision_log、.run.lock、project.json；"
        "决策用 om_decision_append，阶段状态用 om_checkpoint。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "path": {
                "type": "string",
                "description": "项目相对路径，如 artifacts/script.json",
            },
            "content": {
                "description": "字符串或 JSON 对象/数组（对象会 pretty-print）",
            },
            "label": {"type": "string"},
        },
        "required": ["path", "content", "label"],
    },
}


def handle_artifact_write(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id, err = _resolve_project_id(args)
    if err:
        return _error(err)
    assert project_id is not None

    path_arg = str(args.get("path") or "").strip().replace("\\", "/")
    target, path_err = _safe_rel_path(project_id, path_arg)
    if path_err:
        return _error(path_err)
    assert target is not None

    root = _project_dir(project_id).resolve()
    rel_norm = str(target.relative_to(root)).replace("\\", "/")
    if target.name in _WRITE_DENY_NAMES or target.name.startswith("checkpoint"):
        return _error(f"禁止写入 {target.name}；改用 om_checkpoint / om_decision_append")

    allowed = any(
        rel_norm == p.rstrip("/") or rel_norm.startswith(p)
        for p in _WRITE_ALLOW_PREFIXES
    )
    if not allowed:
        return _error(
            f"路径不在允许子树内: {rel_norm}",
            allowed_prefixes=list(_WRITE_ALLOW_PREFIXES),
        )

    content = args.get("content")
    if isinstance(content, (dict, list)):
        text = json.dumps(content, ensure_ascii=False, indent=2) + "\n"
    elif isinstance(content, str):
        text = content
    else:
        return _error("content 须为字符串或 JSON 对象/数组")

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    except OSError as exc:
        return _error(f"写入失败: {exc}")

    return _json({
        "ok": True,
        "project_id": project_id,
        "path": rel_norm,
        "bytes": len(text.encode("utf-8")),
    })


# ─── om_decision_append ──────────────────────────────────────────────

OM_DECISION_APPEND_SCHEMA = {
    "name": "om_decision_append",
    "description": (
        "向 decision_log 追加已校验的决策条目（唯一合法写路径）。"
        "不要用 om_artifact_write 改 decision_log.json。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "decisions": {
                "type": "array",
                "description": "决策对象列表（或传单个 decision）",
                "items": {"type": "object"},
            },
            "decision": {
                "type": "object",
                "description": "单条决策（与 decisions 二选一）",
            },
            "label": {"type": "string"},
        },
        "required": ["label"],
    },
}


def handle_decision_append(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id, err = _resolve_project_id(args)
    if err:
        return _error(err)
    assert project_id is not None

    decisions = args.get("decisions")
    if decisions is None and isinstance(args.get("decision"), dict):
        decisions = [args["decision"]]
    if not isinstance(decisions, list) or not decisions:
        return _error("需要非空 decisions 列表或单个 decision 对象")

    from plugins.openmontage.lib.decision_log import append_decisions

    try:
        path = append_decisions(project_id, decisions)
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")

    return _json({
        "ok": True,
        "project_id": project_id,
        "appended": len(decisions),
        "path": str(path),
    })


STAGE_TOOLS = (
    ("om_registry", OM_REGISTRY_SCHEMA, handle_registry),
    ("om_checkpoint", OM_CHECKPOINT_SCHEMA, handle_checkpoint),
    ("om_artifact_read", OM_ARTIFACT_READ_SCHEMA, handle_artifact_read),
    ("om_artifact_write", OM_ARTIFACT_WRITE_SCHEMA, handle_artifact_write),
    ("om_decision_append", OM_DECISION_APPEND_SCHEMA, handle_decision_append),
)
