"""向大脑供给 OpenMontage 的技能。

技能分三层，供给策略不同：

AGENT_GUIDE.md（契约层）
    整个能力的操作手册。注册为常驻技能，大脑随时可显式加载。

meta/（跨阶段方法论）
    reviewer、checkpoint-protocol、taste-direction 之类，与具体流水线无关。
    同样常驻。

pipelines/<type>/<stage>-director.md（阶段导演）
    **不**常驻。十几条流水线乘以七八个阶段，全塞进技能索引只会淹没大脑，
    而且它同一时刻只需要当前阶段那一份。改由 ``om_director`` 按项目的
    next_stage 动态取用。
"""

from __future__ import annotations

from typing import Any

from plugins.openmontage.bridge import _error, _json

_META_DESCRIPTIONS = {
    "reviewer": "阶段产出的批判性复核清单——交付前自查用",
    "checkpoint-protocol": "检查点与人工审批门的读写协议",
    "skill-creator": "新增导演技能时的写法规范",
    "creative-intake": "把模糊需求问成可执行创意简报",
    "taste-direction": "视觉品味方向的判定标准",
    "onboarding": "新用户首次接触时的引导流程",
    "capability-extension": "需要新能力时的扩展路径（禁止绕流水线）",
    "animation-runtime-selector": "在 Remotion / HyperFrames / ffmpeg 间选运行时",
    "bespoke-composition": "模板不适用时的定制合成路径",
    "video-reference-analyst": "参考视频的拆解方法",
    "voice-performance-director": "配音表演指导与可听性把关",
}


def register_skills(ctx) -> None:  # noqa: ANN001
    """注册契约层与 meta 层技能。阶段导演技能走 om_director。"""
    from plugins.openmontage.lib.paths import CODE_ROOT, SKILLS_DIR

    guide = CODE_ROOT / "AGENT_GUIDE.md"
    if guide.is_file():
        ctx.register_skill(
            name="agent-guide",
            path=guide,
            description="OpenMontage 完整操作指南与 agent 契约——动手前必读",
        )

    meta_dir = SKILLS_DIR / "meta"
    if not meta_dir.is_dir():
        return
    for path in sorted(meta_dir.glob("*.md")):
        bare = path.stem
        ctx.register_skill(
            name=bare,
            path=path,
            description=_META_DESCRIPTIONS.get(bare, f"OpenMontage meta 技能：{bare}"),
        )


# ─── om_director ─────────────────────────────────────────────────────

OM_DIRECTOR_SCHEMA = {
    "name": "om_director",
    "description": (
        "取当前阶段的导演技能全文。导演技能是该阶段唯一的执行规程——"
        "开工前必须完整读一遍，不要凭印象操作。"
        "省略 stage 则自动取项目的 next_stage。"
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string", "description": "项目 id"},
            "stage": {
                "type": "string",
                "description": "阶段名。省略则用 next_stage",
            },
        },
        "required": ["project_id"],
    },
}


def handle_director(args: dict, **_kw: Any) -> str:
    args = args or {}
    project_id = str(args.get("project_id") or "").strip()
    if not project_id:
        return _error("缺少 project_id")

    from plugins.openmontage.lib.paths import CODE_ROOT, PROJECTS_DIR

    project_dir = PROJECTS_DIR / project_id
    marker = project_dir / "project.json"
    if not marker.is_file():
        return _error(f"项目不存在或未初始化: {project_id}")

    from plugins.openmontage.lib.pipeline_loader import (
        load_pipeline_readonly,
        resolve_stage_skill_file,
    )
    from plugins.openmontage.lib.project_status import build_project_status

    # next_stage 与 pipeline_type 都从 project_status 取 ——
    # AGENT_GUIDE 指定它是这两者的唯一权威来源，别在这里另算一套。
    try:
        status = build_project_status(project_id)
    except Exception as exc:
        return _error(f"读取项目状态失败: {exc}")

    pipeline_type = status.get("pipeline_type") or ""
    if not pipeline_type or pipeline_type == "unknown":
        return _error("项目未声明 pipeline_type")

    stage = str(args.get("stage") or "").strip() or (status.get("next_stage") or "")
    if not stage:
        return _json(
            {
                "ok": True,
                "project_id": project_id,
                "stage": None,
                "note": "流水线已跑完，没有待执行阶段",
            }
        )

    try:
        manifest = load_pipeline_readonly(pipeline_type)
    except Exception as exc:
        return _error(f"流水线 {pipeline_type} 载入失败: {exc}")

    rel = resolve_stage_skill_file(manifest, stage)
    if not rel:
        return _error(f"阶段 {stage} 未声明导演技能", pipeline=pipeline_type)

    skill_file = CODE_ROOT / rel
    if not skill_file.is_file():
        # 不要沉默返回空技能：那会让大脑以为这个阶段没有规程而自由发挥。
        return _error(f"导演技能文件缺失: {rel}", resolved_to=str(skill_file))

    return _json(
        {
            "ok": True,
            "project_id": project_id,
            "pipeline": pipeline_type,
            "stage": stage,
            "skill_path": rel,
            "skill": skill_file.read_text(encoding="utf-8"),
        }
    )


DIRECTOR_TOOLS = (("om_director", OM_DIRECTOR_SCHEMA, handle_director),)
