"""OpenMontage —— 指令驱动的视频生产能力，作为 Hermes 插件挂载。

大脑（Hermes）负责编排与对话，本插件负责视频生产：工具注册表、流水线定义、
导演技能、Backlot 看板。

暴露给大脑的是**能力面**而非全部 102 个内部工具 —— 后者是流水线内的执行
单元，由导演技能按阶段调度，平铺出来只会让大脑面对它无法正确排序的选项。
理由与工具清单见 ``bridge.py``。

命名消歧：本插件内的 ``tools`` / ``lib`` / ``skills`` 是 OpenMontage 的，
全限定名为 ``plugins.openmontage.*``；Hermes 内核也有同名的 ``src/tools``
与 ``src/skills``，二者不是一回事，不要混用。

三个根的解析见 ``lib/paths.py``：代码根是本目录，仓库根容纳 vendor/ 与
.agents/ 这类大件，数据根默认在 ``{HUB_DATA_DIR}/montage``。
"""

from __future__ import annotations

from plugins.openmontage.bridge import READONLY_TOOLS, TOOLSET, check_available
from plugins.openmontage.capability_lock import llm_request_middleware
from plugins.openmontage.exec_tools import EXEC_TOOLS
from plugins.openmontage.governance import post_tool_call, pre_tool_call
from plugins.openmontage.skills import DIRECTOR_TOOLS, pre_llm_call, register_skills
from plugins.openmontage.stage_tools import STAGE_TOOLS, TOOLSET as STAGE_TOOLSET

__all__ = ["register", "on_ready"]

_EMOJI = {
    "om_preflight": "🩺",
    "om_catalog": "📋",
    "om_pipeline": "🎞️",
    "om_project": "📊",
    "om_director": "🎯",
    "om_run": "▶️",
    "om_job": "⏳",
    "om_state": "📝",
    "om_registry": "🧰",
    "om_checkpoint": "📌",
    "om_artifact_read": "📖",
    "om_artifact_write": "💾",
    "om_decision_append": "🧾",
}


def register(ctx) -> None:  # noqa: ANN001  (ctx 类型由宿主提供)
    """Hermes 插件注册入口，由插件加载器调用一次。"""
    for name, schema, handler in (*READONLY_TOOLS, *DIRECTOR_TOOLS, *EXEC_TOOLS):
        ctx.register_tool(
            name=name,
            toolset=TOOLSET,
            schema=schema,
            handler=handler,
            check_fn=check_available,
            emoji=_EMOJI.get(name, "🎬"),
        )

    # 无头 stage 专用面：与编排 openmontage 拆开，避免无头拿到 om_run/om_job
    for name, schema, handler in STAGE_TOOLS:
        ctx.register_tool(
            name=name,
            toolset=STAGE_TOOLSET,
            schema=schema,
            handler=handler,
            check_fn=check_available,
            emoji=_EMOJI.get(name, "🎬"),
        )

    register_skills(ctx)

    # 硬规则运行时化：文档里的 "HARD RULE" 只在被读到时生效，
    # 挂到 pre_tool_call 上才是真拦得住。理由见 governance.py。
    ctx.register_hook("pre_tool_call", pre_tool_call)
    ctx.register_hook("post_tool_call", post_tool_call)
    # 按需注入 AGENT_GUIDE 顶部 session-brief：仅当用户消息像 OM/视频
    # 意图时才注入，避免问候触发 onboarding / om_preflight（见 skills.py）。
    ctx.register_hook("pre_llm_call", pre_llm_call)
    # 能力收口：OM 生产会话从发往模型的 tools 列表拿掉 read_file 等
    # （见 capability_lock.py）。比「拦调用」更早 —— 模型根本看不见工具。
    ctx.register_middleware("llm_request", llm_request_middleware)

    from plugins.openmontage.backlot.server import (
        build_api_router,
        build_media_router,
        build_ui_router,
    )

    ctx.register_routes(
        build_api_router(),
        prefix="/api/plugins/openmontage",
        tags=["openmontage-backlot"],
    )
    # Canonical media/thumb under the plugin API namespace (used by lib.js mediaPrefix).
    ctx.register_routes(
        build_media_router(),
        prefix="/api/plugins/openmontage",
        tags=["openmontage-backlot"],
    )
    # Compat: keep /thumb and /media at hub root so legacy/hardcoded img src still work.
    ctx.register_routes(
        build_media_router(),
        prefix="",
        tags=["openmontage-backlot"],
    )
    ctx.register_routes(
        build_ui_router(hub=True),
        prefix="/plugins/openmontage",
        tags=["openmontage-backlot"],
    )


def on_ready(ctx) -> None:  # noqa: ANN001
    from plugins.openmontage.backlot.server import start_runtime_sync

    start_runtime_sync()
