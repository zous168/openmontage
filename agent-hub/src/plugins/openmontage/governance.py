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
import re
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

# execute_code / terminal 里手写 import 跑流水线 = 绕过 om_run。
_EXECUTE_PIPELINE_HINTS = (
    "stage_runner",
    "prepare_stage_run",
    "schedule_run_task",
    "run_task(",
    "plugins.openmontage.backlot",
    "from plugins.openmontage",
    "import plugins.openmontage",
)


# execute_code / terminal / om_job / stage tools 没 label = UI 只能显示空壳。
_LABEL_REQUIRED_RUNTIME = frozenset({
    "execute_code",
    "terminal",
    "om_job",
    "om_registry",
    "om_checkpoint",
    "om_artifact_read",
    "om_artifact_write",
    "om_decision_append",
})

_FILE_BROWSE_TOOLS = frozenset({
    "read_file",
    "search_files",
    "find_files",
    "list_files",
    "write_file",
    "patch",
})

# 无头已去掉这些 Hermes 工具；幻觉调用仍硬拦。
_HEADLESS_FORBIDDEN_GENERIC = frozenset({
    "terminal",
    "execute_code",
    "read_file",
    "search_files",
    "find_files",
    "list_files",
    "write_file",
    "patch",
})

_HEADLESS_GENERIC_BLOCK_MSG = (
    "无头 stage 通道拦截：禁止 terminal / execute_code / 通用文件工具。"
    "请改用 om_registry / om_checkpoint / om_artifact_read / "
    "om_artifact_write / om_decision_append。"
)

# 契约/导演/流水线定义：只能 skill_view / om_director / om_pipeline。
_OM_CONTRACT_PATH_MARKERS = (
    "plugins/openmontage/agent_guide.md",
    "plugins\\openmontage\\agent_guide.md",
    "/openmontage/agent_guide.md",
    "\\openmontage\\agent_guide.md",
    "plugins/openmontage/skills/",
    "plugins\\openmontage\\skills\\",
    "/openmontage/skills/",
    "\\openmontage\\skills\\",
    "plugins/openmontage/pipeline_defs/",
    "plugins\\openmontage\\pipeline_defs\\",
    "/openmontage/pipeline_defs/",
    "\\openmontage\\pipeline_defs\\",
    "plugins/openmontage/schemas/",
    "plugins\\openmontage\\schemas\\",
    "/openmontage/schemas/",
    "\\openmontage\\schemas\\",
    ".schema.json",
)

# 插件源码浏览：用 om_* 通道，不要 read_file 猜实现。
_OM_SOURCE_PATH_MARKERS = (
    "plugins/openmontage/lib/",
    "plugins\\openmontage\\lib\\",
    "plugins/openmontage/backlot/",
    "plugins\\openmontage\\backlot\\",
    "plugins/openmontage/tools/",
    "plugins\\openmontage\\tools\\",
    "plugins/openmontage/governance.py",
    "plugins\\openmontage\\governance.py",
    "plugins/openmontage/bridge.py",
    "plugins\\openmontage\\bridge.py",
    "plugins/openmontage/exec_tools.py",
    "plugins\\openmontage\\exec_tools.py",
    "plugins/openmontage/skills.py",
    "plugins\\openmontage\\skills.py",
    "plugins/openmontage/__init__.py",
    "plugins\\openmontage\\__init__.py",
)

# 项目进度/锁/run 状态：只能 om_project / om_job / om_state。
_PROJECT_META_PATH_RE = re.compile(
    r"(?:"
    r"[/\\]projects[/\\][^/\\]+[/\\](?:meta\.json|project\.json|"
    r"checkpoint[^/\\]*\.json|\.run\.lock|"
    r"checkpoints[/\\]|runs[/\\]|history[/\\])"
    r"|"
    r"[/\\]montage[/\\]projects[/\\][^/\\]+[/\\](?:meta\.json|project\.json|"
    r"checkpoint[^/\\]*\.json|\.run\.lock|"
    r"checkpoints[/\\]|runs[/\\]|history[/\\])"
    r")",
    re.IGNORECASE,
)

# Layer 3 供应商技能按路径读是契约允许的。
_LAYER3_SKILL_ALLOW_RE = re.compile(
    r"[/\\]\.agents[/\\]skills[/\\]",
    re.IGNORECASE,
)

# 项目产物内容可读（进度仍走 om_project）。
_ARTIFACT_ALLOW_RE = re.compile(
    r"[/\\]projects[/\\][^/\\]+[/\\]artifacts[/\\]",
    re.IGNORECASE,
)

# 禁止「Wait 10min」这类超长空等 label / 命令。
_LONG_WAIT_LABEL_RE = re.compile(
    r"(?:"
    r"wait\s*\d+\s*(?:min(?:ute)?s?|m)\b"
    r"|\b\d+\s*(?:min(?:ute)?s?)\b.*(?:poll|wait|check|再查|轮询)"
    r"|等\s*\d+\s*(?:分钟|分)\b"
    r"|轮询.*\d+\s*(?:分钟|分|min)"
    r")",
    re.IGNORECASE,
)

# 禁止「等 90 秒查 edit 进度」这类假等待：label 声称等待，实际 0.1s 返回刷屏。
# 轮询只能反复调 om_job，label 写「轮询 edit 进度」，不要写「等 Ns」。
_FAKE_WAIT_LABEL_RE = re.compile(
    r"(?:"
    r"等\s*\d+\s*(?:秒|s)\b"
    r"|wait\s*\d+\s*(?:s|sec|secs|seconds?)\b"
    r"|等\s*\d+.*(?:查|进度|轮询|poll|再查)"
    r"|wait\s*\d+.*(?:check|poll|进度|再查)"
    r")",
    re.IGNORECASE,
)

_LONG_SLEEP_CMD_RE = re.compile(
    r"(?:"
    r"\bsleep\s+(?:[5-9]\d|\d{3,})\b"  # sleep >= 50s
    r"|\bStart-Sleep\s+(?:-Seconds\s+)?(?:[5-9]\d|\d{3,})\b"
    r")",
    re.IGNORECASE,
)

_POLL_SLEEP_CMD_RE = re.compile(
    r"(?:"
    r"\bsleep\s+\d+(?:\.\d+)?\b"
    r"|\bStart-Sleep\b"
    r"|time\.sleep\s*\("
    r")",
    re.IGNORECASE,
)

_POLL_CONTEXT_RE = re.compile(
    r"(?:进度|轮询|再查|poll|wait|查\s*\w+\s*进度)",
    re.IGNORECASE,
)


def _block(message: str) -> dict[str, str]:
    return {"action": "block", "message": message}


def _text_of(args: dict[str, Any]) -> str:
    """把工具参数摊平成一段可搜索的文本。"""
    try:
        return json.dumps(args, ensure_ascii=False, default=str)
    except Exception:
        return str(args)


def _norm_path(path: str) -> str:
    return path.replace("\\", "/").lower()


def _path_args(args: dict[str, Any]) -> list[str]:
    """收集常见文件工具参数里的路径字段。"""
    out: list[str] = []
    for key in (
        "path",
        "file_path",
        "filepath",
        "target_directory",
        "directory",
        "dir",
        "glob",
        "pattern",
        "query",
    ):
        raw = args.get(key)
        if isinstance(raw, str) and raw.strip():
            out.append(raw.strip())
    return out


def _check_invocation_label(tool_name: str, args: dict[str, Any]) -> dict | None:
    """高频工具必须带非空 label，逼模型给这次调用起名。"""
    if tool_name not in _LABEL_REQUIRED_RUNTIME:
        return None
    raw = args.get("label")
    if isinstance(raw, str) and raw.strip():
        return None
    return _block(
        f"缺少 label：`{tool_name}` 每次调用都必须带 3–8 字的 label（用户语言），"
        "说明这一次在做什么。例如：「写 in_progress 检查点」「检查 artifacts 目录」"
        "「轮询 reference_analysis 是否完成」。不要写「运行代码」或工具名。"
        "请补上 label 后重试同一工具。"
    )


def _check_long_wait(tool_name: str, args: dict[str, Any]) -> dict | None:
    """禁止超长空等，以及「等 90 秒查进度」这类假等待 label。"""
    label = args.get("label")
    label_s = label.strip() if isinstance(label, str) else ""

    if label_s and _FAKE_WAIT_LABEL_RE.search(label_s):
        return _block(
            "假等待拦截：禁止 label 写成「等 90 秒查 … 进度」（你贴的日志里这类调用只跑 0.1s）。"
            "不要用 sleep / 空转 label 演戏。反复调用 om_job(task_id=…)，"
            "label 写成「轮询 edit 进度」；看到 work_done / stop_polling 就停。"
        )
    if label_s and _LONG_WAIT_LABEL_RE.search(label_s):
        return _block(
            "轮询节奏拦截：禁止「Wait 10min / 等 10 分钟」这类超长空等。"
            "用 om_job 轮询，间隔约 15–60 秒；label 写成「轮询 research 进度」。"
        )
    if tool_name in ("terminal", "execute_code"):
        text = _text_of(args)
        if _LONG_SLEEP_CMD_RE.search(text) or _LONG_WAIT_LABEL_RE.search(text):
            return _block(
                "轮询节奏拦截：不要用 sleep/Start-Sleep 做分钟级空等。"
                "请改用 om_job，约每 15–60 秒查一次。"
            )
        # 进度语境下任何 sleep 都视为假轮询（含 time.sleep）。
        if _POLL_CONTEXT_RE.search(label_s or text) and _POLL_SLEEP_CMD_RE.search(text):
            return _block(
                "假等待拦截：不要用 sleep/time.sleep 假装轮询阶段进度。"
                "请改用 om_job(task_id=…)。"
            )
        if _FAKE_WAIT_LABEL_RE.search(text):
            return _block(
                "假等待拦截：命令/参数里不要写「等 Ns 查进度」。改用 om_job。"
            )
    return None


def _check_om_file_browse(tool_name: str, args: dict[str, Any]) -> dict | None:
    """有 om_* / skill_view 时，禁止用文件工具重建契约或手扒进度文件。"""
    if tool_name not in _FILE_BROWSE_TOOLS:
        return None

    paths = _path_args(args)
    if not paths:
        # search 无路径时看整段参数文本
        paths = [_text_of(args)]

    for raw in paths:
        if _LAYER3_SKILL_ALLOW_RE.search(raw):
            continue
        if _ARTIFACT_ALLOW_RE.search(raw) and tool_name == "read_file":
            continue

        lowered = _norm_path(raw)
        for mark in _OM_CONTRACT_PATH_MARKERS:
            if mark.replace("\\", "/") in lowered:
                return _block(
                    "OpenMontage 通道拦截：不要用 read_file/search_files 打开 "
                    "AGENT_GUIDE / skills/ / pipeline_defs / schema。"
                    "契约 → skill_view(\"openmontage:agent-guide\")；"
                    "元技能 → skill_view(\"openmontage:<name>\")；"
                    "导演 → om_director；流水线定义 → om_pipeline。"
                )
        for mark in _OM_SOURCE_PATH_MARKERS:
            if mark.replace("\\", "/") in lowered:
                return _block(
                    "OpenMontage 通道拦截：不要浏览插件源码来猜审批 / reset / 进度。"
                    "请用 om_project / om_job / om_state（看 diagnostics），"
                    "不要 read_file 插件 lib/backlot。"
                )
        if _PROJECT_META_PATH_RE.search(raw):
            return _block(
                "OpenMontage 通道拦截：不要直接读 meta.json / checkpoint / "
                "runs/*.json / .run.lock。"
                "进度与 orphan → om_project；轮询 → om_job；"
                "闭环 → om_state(complete_from_disk/approve)。"
            )
    return None


def pre_tool_call(tool_name: str = "", args: dict | None = None, **_kw: Any):
    """在工具执行前做契约检查。"""
    args = args if isinstance(args, dict) else {}
    session_id = str(_kw.get("session_id") or "").strip()

    from plugins.openmontage.capability_lock import (
        is_headless_stage,
        note_om_tool_use,
        pre_tool_capability_block,
    )

    if tool_name.startswith("om_"):
        note_om_tool_use(tool_name, session_id=session_id)

    # 无头：通用 shell/文件工具已不在 allowlist；幻觉调用直接拦并指向 stage tools
    if is_headless_stage() and tool_name in _HEADLESS_FORBIDDEN_GENERIC:
        return _block(_HEADLESS_GENERIC_BLOCK_MSG)

    verdict = pre_tool_capability_block(tool_name, session_id=session_id)
    if verdict:
        return verdict

    verdict = _check_invocation_label(tool_name, args)
    if verdict:
        return verdict

    verdict = _check_long_wait(tool_name, args)
    if verdict:
        return verdict

    verdict = _check_om_file_browse(tool_name, args)
    if verdict:
        return verdict

    if tool_name in ("terminal", "execute_code"):
        text = _text_of(args)
        verdict = _check_pipeline_bypass(text)
        if verdict:
            return verdict
        if tool_name == "execute_code":
            verdict = _check_execute_code_pipeline(text)
            if verdict:
                return verdict
        # terminal/execute_code 里 cat/type/Get-Content 扒契约路径
        verdict = _check_shell_contract_browse(text)
        if verdict:
            return verdict

    if tool_name == "om_run":
        verdict = _check_stage_order(args)
        if verdict:
            return verdict

    return None


def _check_shell_contract_browse(payload: str) -> dict | None:
    """terminal / execute_code 里用 shell 读契约或进度文件同样拦截。"""
    lowered = _norm_path(payload)
    # 明显的读文件命令 + 敏感路径
    readish = any(
        tok in lowered
        for tok in (
            "cat ",
            "type ",
            "get-content",
            "less ",
            "head ",
            "tail ",
            "open(",
            "read_text",
            "path(",
        )
    )
    if not readish and "search_files" not in lowered:
        # 仍拦截对敏感路径的 find/ls 深挖进度锁
        if ".run.lock" in lowered or "/runs/" in lowered or "/checkpoints/" in lowered:
            if any(tok in lowered for tok in ("ls ", "dir ", "find ", "get-childitem")):
                return _block(
                    "OpenMontage 通道拦截：不要用 terminal 列 runs/checkpoints/"
                    ".run.lock。请用 om_project / om_job。"
                )
        return None

    for mark in _OM_CONTRACT_PATH_MARKERS + _OM_SOURCE_PATH_MARKERS:
        if mark.replace("\\", "/") in lowered:
            return _block(
                "OpenMontage 通道拦截：不要用 terminal/execute_code 读取 "
                "AGENT_GUIDE / skills / 插件源码。改用 skill_view / om_*。"
            )
    if _PROJECT_META_PATH_RE.search(payload):
        return _block(
            "OpenMontage 通道拦截：不要用 terminal/execute_code 读 "
            "checkpoint/meta/runs。改用 om_project / om_job / om_state。"
        )
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


def _check_execute_code_pipeline(payload: str) -> dict | None:
    """不许用 execute_code import stage_runner / 手写跑阶段。"""
    lowered = payload.lower()
    for hint in _EXECUTE_PIPELINE_HINTS:
        if hint.lower() in lowered:
            return _block(
                "OpenMontage 拦截：不要用 execute_code 手写 import/"
                f"调用（检测到 {hint}）来跑阶段。"
                "请改用 om_run 启动，再用 om_job 轮询；"
                "每个工具调用都填 label 说明这一次在做什么。"
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
        from plugins.openmontage.capability_lock import note_om_tool_use

        note_om_tool_use(
            tool_name,
            session_id=str(_kw.get("session_id") or ""),
        )
        logger.debug("OpenMontage 工具执行完毕: %s", tool_name)
    return None
