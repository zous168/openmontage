"""把 OpenMontage 的能力桥接成 Hermes 工具。

设计取舍：

**不是逐个转发 102 个工具。** OpenMontage 的工具是流水线内部的执行单元，
由导演技能按阶段调度。把它们平铺到 Hermes 的工具列表里，只会让大脑面对
一百多个它无法正确排序的选项。这里暴露的是**能力面**——大脑用它了解状态、
决定下一步，具体执行仍由 OpenMontage 的流水线负责。

**发现结果做进程内缓存。** ``registry.discover()`` 要 import 整棵 tools/
树（102 个模块，含若干重依赖），冷启动是秒级。Hermes 每次列工具都触发一次
是不可接受的。

只读工具在此，执行面（run/job/state）见 ``exec_tools.py``。
"""

from __future__ import annotations

import json
from typing import Any

# 大脑侧看到的工具名统一 om_ 前缀，避免与 Hermes 内置工具混淆。
TOOLSET = "openmontage"


def _json(payload: Any) -> str:
    """统一的返回格式：紧凑 JSON，非 ASCII 不转义（中文直出）。"""
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


def _error(message: str, **extra: Any) -> str:
    return _json({"ok": False, "error": message, **extra})


# ─── 工具注册表（懒加载 + 进程内缓存）──────────────────────────────────

_registry = None


def _get_registry():
    """拿到已完成发现的 OpenMontage 工具注册表。

    第一次调用会 import 整棵 tools/ 树，耗时秒级；之后复用。
    """
    global _registry
    if _registry is None:
        from plugins.openmontage.tools.tool_registry import registry

        registry.ensure_discovered()
        _registry = registry
    return _registry


def check_available() -> bool:
    """OpenMontage 能力是否可用。

    只验证包结构完整（能定位到流水线定义），不验证 provider 凭据 ——
    那是 ``om_preflight`` 要报告的内容，而不是把工具整个藏起来的理由。
    """
    try:
        from plugins.openmontage.lib.paths import PIPELINE_DEFS_DIR

        return PIPELINE_DEFS_DIR.is_dir()
    except Exception:
        return False


# ─── om_preflight ────────────────────────────────────────────────────

OM_PREFLIGHT_SCHEMA = {
    "name": "om_preflight",
    "description": (
        "OpenMontage 开工前的能力体检：哪些视频/图像/音频 provider 已配置、"
        "哪些缺凭据、合成运行时（ffmpeg / Remotion / HyperFrames）是否就绪。"
        "AGENT_GUIDE 要求在提案阶段把这份菜单如实呈现给用户后再动工。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "detail": {
                "type": "string",
                "enum": ["menu", "full"],
                "description": "menu=面向用户的精简菜单（默认）；full=完整支持包络",
            }
        },
    },
}


def handle_preflight(args: dict, **_kw: Any) -> str:
    detail = str((args or {}).get("detail") or "menu").strip().lower()
    try:
        registry = _get_registry()
        payload: dict[str, Any] = {"ok": True}
        if detail == "full":
            payload["support_envelope"] = registry.support_envelope()
        else:
            payload["provider_menu"] = registry.provider_menu_summary()
    except Exception as exc:  # 体检本身失败也要说清楚，不能静默返回空菜单
        return _error(f"preflight 失败: {exc}")

    # Remotion 单独报：它是 Node 工程，装没装依赖 registry 看不出来，
    # 而缺依赖的失败要等到渲染跑几分钟后才以 webpack 报错的形式冒出来。
    try:
        from plugins.openmontage.lib.remotion_bootstrap import status as remotion_status

        payload["remotion"] = remotion_status().as_dict()
    except Exception as exc:
        payload["remotion"] = {"ready": False, "notes": [f"体检失败: {exc}"]}
    return _json(payload)


# ─── om_catalog ──────────────────────────────────────────────────────

OM_CATALOG_SCHEMA = {
    "name": "om_catalog",
    "description": (
        "按能力（capability）列出 OpenMontage 的工具清单及其可用状态。"
        "用于回答「有哪些方式可以生成视频/配音/图像」这类问题。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "capability": {
                "type": "string",
                "description": "只看某个能力，如 video_generation、tts、image_generation。省略则返回全部",
            }
        },
    },
}


def handle_catalog(args: dict, **_kw: Any) -> str:
    capability = str((args or {}).get("capability") or "").strip()
    try:
        catalog = _get_registry().capability_catalog()
    except Exception as exc:
        return _error(f"catalog 失败: {exc}")

    if capability:
        entries = catalog.get(capability)
        if entries is None:
            return _error(
                f"未知能力: {capability}",
                available_capabilities=sorted(catalog),
            )
        return _json({"ok": True, "capability": capability, "tools": entries})
    return _json(
        {
            "ok": True,
            "capabilities": sorted(catalog),
            "tool_count": sum(len(v) for v in catalog.values()),
        }
    )


# ─── om_pipeline ─────────────────────────────────────────────────────

OM_PIPELINE_SCHEMA = {
    "name": "om_pipeline",
    "description": (
        "查看 OpenMontage 的流水线定义：有哪些流水线、某条流水线的阶段顺序、"
        "每个阶段的导演技能与是否需要人工审批。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "流水线名（如 reference-driven、explainer）。省略则列出全部",
            }
        },
    },
}


def handle_pipeline(args: dict, **_kw: Any) -> str:
    name = str((args or {}).get("name") or "").strip()
    from plugins.openmontage.lib.pipeline_loader import (
        get_stage_human_approval_default,
        get_stage_order,
        list_pipelines,
        load_pipeline_readonly,
        resolve_stage_skill_file,
    )

    if not name:
        return _json({"ok": True, "pipelines": list_pipelines()})

    try:
        manifest = load_pipeline_readonly(name)
    except Exception as exc:
        return _error(f"流水线 {name} 载入失败: {exc}", available=list_pipelines())

    stages = []
    for stage in get_stage_order(manifest):
        stages.append(
            {
                "name": stage,
                "director_skill": resolve_stage_skill_file(manifest, stage),
                "human_approval": get_stage_human_approval_default(manifest, stage),
            }
        )
    return _json(
        {
            "ok": True,
            "pipeline": name,
            "description": manifest.get("description", ""),
            "stages": stages,
        }
    )


# ─── om_project ──────────────────────────────────────────────────────

OM_PROJECT_SCHEMA = {
    "name": "om_project",
    "description": (
        "读取 OpenMontage 项目状态：next_stage、已完成阶段、产物路径、"
        "本阶段该读哪份导演技能、工具调用痕迹。这是判断「进行到哪了」的"
        "唯一权威来源 —— 不要靠翻文件目录猜。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {
                "type": "string",
                "description": "项目 id（projects/ 下的目录名）。省略则列出全部项目",
            },
            "audit": {
                "type": "boolean",
                "description": "附带契约审计结果（跳阶段、缺产物等）",
            },
        },
    },
}


def handle_project(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id = str(args.get("project_id") or "").strip()
    from plugins.openmontage.lib.paths import PROJECTS_DIR

    if not project_id:
        if not PROJECTS_DIR.is_dir():
            return _json({"ok": True, "projects": [], "projects_dir": str(PROJECTS_DIR)})
        names = sorted(
            p.name for p in PROJECTS_DIR.iterdir() if (p / "project.json").is_file()
        )
        return _json({"ok": True, "projects": names, "projects_dir": str(PROJECTS_DIR)})

    from plugins.openmontage.lib.project_status import build_project_status

    try:
        status = build_project_status(
            project_id, include_audit=bool(args.get("audit"))
        )
    except FileNotFoundError:
        return _error(f"项目不存在: {project_id}", projects_dir=str(PROJECTS_DIR))
    except Exception as exc:
        return _error(f"读取项目状态失败: {exc}")
    return _json({"ok": True, **status})


READONLY_TOOLS = (
    ("om_preflight", OM_PREFLIGHT_SCHEMA, handle_preflight),
    ("om_catalog", OM_CATALOG_SCHEMA, handle_catalog),
    ("om_pipeline", OM_PIPELINE_SCHEMA, handle_pipeline),
    ("om_project", OM_PROJECT_SCHEMA, handle_project),
)
