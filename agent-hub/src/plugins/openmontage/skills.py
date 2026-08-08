"""向大脑供给 OpenMontage 的技能。

技能分三层，供给策略不同：

AGENT_GUIDE.md（契约层）
    整个能力的操作手册。注册为常驻技能，大脑随时可显式加载。
    顶部 ``om:session-brief`` 块由 ``pre_llm_call`` **按需**注入：仅当本轮
    用户消息像视频生产 / OpenMontage 工作时才追加，避免 ``hi`` 之类问候
    触发 onboarding / om_preflight。同一会话只注入一次。

meta/（跨阶段方法论）
    reviewer、checkpoint-protocol、taste-direction 之类，与具体流水线无关。
    同样常驻。

pipelines/<type>/<stage>-director.md（阶段导演）
    **不**常驻。十几条流水线乘以七八个阶段，全塞进技能索引只会淹没大脑，
    而且它同一时刻只需要当前阶段那一份。改由 ``om_director`` 按项目的
    next_stage 动态取用。
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from plugins.openmontage.bridge import _error, _json

logger = logging.getLogger(__name__)

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

_BRIEF_START = "<!-- om:session-brief:start -->"
_BRIEF_END = "<!-- om:session-brief:end -->"
_BRIEF_RE = re.compile(
    re.escape(_BRIEF_START) + r"\s*(.*?)\s*" + re.escape(_BRIEF_END),
    re.DOTALL,
)

# 同一会话只注入一次完整 brief，避免每轮重复占上下文。
_briefed_sessions: set[str] = set()

# 用户消息里出现这些，才认为在谈 OpenMontage / 视频生产。
_OM_INTENT_RE = re.compile(
    r"("
    r"open\s*montage|openmontage|\bom[_-]"
    r"|视频|短片|短视频|解说|剪辑|成片|片头|片尾|分镜|剧本|旁白|配音"
    r"|流水线|管线|检查点|看板|backlot"
    r"|montage|remotion|hyperframes|ffmpeg"
    r"|做[个一]?[条部]?片|帮我做|做[点个].*内容|创作.*视频|生成.*视频"
    r"|reference[- ]driven|explainer|pipeline"
    r"|om_preflight|om_run|om_job|om_project|om_director|om_pipeline|om_state|om_catalog"
    r")",
    re.IGNORECASE,
)

# 纯问候 / 极短闲聊：即使误伤关键词也不注入。
_GREETING_ONLY_RE = re.compile(
    r"^\s*("
    r"hi|hello|hey|yo|sup"
    r"|你好|您好|嗨|哈喽|早|早安|午安|晚安|在吗|在不在"
    r"|谢谢|感谢|ok|okay|好的|嗯|哦"
    r")[\s!！.。?？~～]*$",
    re.IGNORECASE,
)


def message_looks_like_openmontage_intent(user_message: str | None) -> bool:
    """本轮是否像在谈视频生产 / OpenMontage（而非闲聊问候）。"""
    text = (user_message or "").strip()
    if not text:
        return False
    if _GREETING_ONLY_RE.match(text):
        return False
    return bool(_OM_INTENT_RE.search(text))


def load_session_brief() -> str:
    """从 AGENT_GUIDE.md 抽取 session-brief 块。标记缺失则返回空串。"""
    try:
        from plugins.openmontage.lib.paths import CODE_ROOT

        guide = CODE_ROOT / "AGENT_GUIDE.md"
        if not guide.is_file():
            return ""
        text = guide.read_text(encoding="utf-8")
    except Exception as exc:
        logger.debug("session-brief 读取失败: %s", exc)
        return ""

    match = _BRIEF_RE.search(text)
    if not match:
        logger.debug("AGENT_GUIDE.md 缺少 om:session-brief 标记")
        return ""
    return match.group(1).strip()


def pre_llm_call(**kw: Any) -> dict[str, str] | None:
    """按需把 AGENT_GUIDE 顶部 brief 注入用户消息。

    Hermes 约定：返回 ``{"context": "..."}`` 追加到本轮 user message，
    不改 system prompt（保住 prompt cache）。

    仅当本轮用户消息像 OpenMontage / 视频生产意图时注入；问候与无关闲聊
    不注入。同一 ``session_id`` 只注入一次。

    无头阶段 agent（``OPENMONTAGE_HEADLESS_STAGE=1``）跳过：brief 是给编排
    大脑的（om_run / om_job 轮询），塞进被编排者会触发自我轮询。
    """
    if os.environ.get("OPENMONTAGE_HEADLESS_STAGE"):
        return None
    if not message_looks_like_openmontage_intent(kw.get("user_message")):
        return None
    session_id = str(kw.get("session_id") or "").strip()
    # 进入 OM 生产意图 → 能力收口（从工具列表拿掉读文件等）
    if session_id:
        from plugins.openmontage.capability_lock import mark_session_lockdown

        mark_session_lockdown(session_id, reason="om_intent")
    if session_id and session_id in _briefed_sessions:
        return None
    brief = load_session_brief()
    if not brief:
        return None
    if session_id:
        _briefed_sessions.add(session_id)
    return {"context": brief}


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

    # 附带本阶段 produces 的字段契约，避免只读技能散文后自造 JSON 键名。
    stage_block = next(
        (s for s in (manifest.get("stages") or []) if s.get("name") == stage),
        {},
    )
    produces = [
        str(p) for p in (stage_block.get("produces") or []) if isinstance(p, str) and p
    ]
    artifact_contracts: list = []
    for art_name in produces:
        try:
            from plugins.openmontage.schemas.artifacts import summarize_artifact_schema

            artifact_contracts.append(summarize_artifact_schema(art_name))
        except Exception as exc:
            artifact_contracts.append({"artifact": art_name, "error": str(exc)})

    return _json(
        {
            "ok": True,
            "project_id": project_id,
            "pipeline": pipeline_type,
            "stage": stage,
            "skill_path": rel,
            "skill": skill_file.read_text(encoding="utf-8"),
            "produces": produces,
            "artifact_contracts": artifact_contracts,
            "note": (
                "写产物前对照 artifact_contracts 的 required / items.required；"
                "字段名必须一致，禁止自造别名；不要打开 *.schema.json。"
            ),
        }
    )


DIRECTOR_TOOLS = (("om_director", OM_DIRECTOR_SCHEMA, handle_director),)
