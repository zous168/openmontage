"""把 AGENT_GUIDE 的硬规则运行时化。

文档里的 "HARD RULE" 只有在 agent 读了、记住了、且没被长对话冲淡时才生效。
**读过**和**照做**之间隔着整个上下文窗口。这里把其中可机械判定的几条挂到
``pre_tool_call`` 上 —— 违规不是被劝阻，是被拒绝执行。

只拦能确定判错的情况。判不准的（"这个创意好不好"）不在这里管，
那是 reviewer 技能和人工审批门的职责。

Hermes 契约：``pre_tool_call`` 回调返回
``{"action": "block", "message": ...}`` 即拦截，返回 None 放行。
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Rule Zero：所有生产必须走流水线。这些 repo-root 脚本是开发自用的，
# agent 拿它们跑生产就是绕过阶段门与导演技能。
_NON_PRODUCTION_SCRIPT_MARK = "OPENMONTAGE_NON_PRODUCTION_SCRIPT"

_BYPASS_HINTS = (
    "scripts/rerun_",
    "scripts\\rerun_",
    "scripts/run_my_copy",
    "scripts\\run_my_copy",
    "scripts/advance_koubo",
    "scripts\\advance_koubo",
)


def _block(message: str) -> dict[str, str]:
    return {"action": "block", "message": message}


def _text_of(args: dict[str, Any]) -> str:
    """把工具参数摊平成一段可搜索的文本。"""
    try:
        return json.dumps(args, ensure_ascii=False, default=str)
    except Exception:
        return str(args)


def pre_tool_call(tool_name: str = "", args: dict | None = None, **_kw: Any):
    """在工具执行前做契约检查。"""
    args = args if isinstance(args, dict) else {}

    if tool_name in ("terminal", "execute_code"):
        verdict = _check_pipeline_bypass(_text_of(args))
        if verdict:
            return verdict

    if tool_name == "om_run":
        verdict = _check_stage_order(args)
        if verdict:
            return verdict

    return None


def _check_pipeline_bypass(payload: str) -> dict | None:
    """Rule Zero：不许用临时脚本直接调工具跑生产。"""
    lowered = payload.lower()
    for hint in _BYPASS_HINTS:
        if hint in lowered:
            return _block(
                f"Rule Zero 拦截：{hint} 是标记了 {_NON_PRODUCTION_SCRIPT_MARK} 的"
                "开发自用脚本，不能用于生产。所有产出必须走流水线阶段"
                "（om_run），这样才有导演技能、审批门和检查点。"
            )
    return None


def _check_stage_order(args: dict[str, Any]) -> dict | None:
    """阶段不许跳：显式传入的 stage 必须等于当前 next_stage。

    stage_runner 内部也有这道校验，但那时锁已经加上、prompt 已经组装。
    在这里拦掉能省一次无谓的启动，而且能给大脑一个可执行的下一步。
    """
    stage = str(args.get("stage") or "").strip()
    if not stage:
        return None  # 不指定就是跑 next_stage，本身不可能跳
    project_id = str(args.get("project_id") or "").strip()
    if not project_id:
        return None  # 缺参数由工具自己报错，不在这里越俎代庖

    try:
        from plugins.openmontage.lib.paths import PROJECTS_DIR
        from plugins.openmontage.lib.project_status import build_project_status

        if not (PROJECTS_DIR / project_id / "project.json").is_file():
            return None
        expected = build_project_status(project_id).get("next_stage")
    except Exception as exc:
        # 判不准就放行 —— 治理钩子不该因为自己出错而堵住正常流程。
        logger.debug("阶段顺序检查跳过: %s", exc)
        return None

    if expected and stage != expected:
        return _block(
            f"阶段顺序拦截：项目 {project_id} 的 next_stage 是 {expected}，"
            f"但请求跑 {stage}。跳阶段会让下游拿不到上游产物。"
            f"请改跑 {expected}，或先用 om_project 确认当前进度。"
        )
    return None


def post_tool_call(tool_name: str = "", **_kw: Any):
    """执行后事件回写。

    目前只落调试日志：OpenMontage 自己的 events.jsonl 已经在 BaseTool 层
    记录了工具轨迹，这里再写一份只会产生两份可能不一致的真相。
    保留钩子是为了后续接审批门推送。
    """
    if tool_name.startswith("om_"):
        logger.debug("OpenMontage 工具执行完毕: %s", tool_name)
    return None
