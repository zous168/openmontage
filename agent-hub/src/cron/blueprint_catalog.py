"""Automation Blueprints — parameterized automation blueprints with typed slots.

A *blueprint* is a one-place definition of an automation that every surface
renders natively:

  * Dashboard / GUI app  -> a form (one field per slot)
  * CLI / TUI / messenger -> a pre-filled ``/blueprint`` slash command
  * Agent                 -> a seed prompt; it asks for any blank/ambiguous slot
  * Docs catalog          -> a copy-paste command + a ``hermes://`` deep-link

The single source of truth is the slot schema below. ``blueprint_form_schema``
emits what a form renderer needs; ``blueprint_slash_command`` emits the flattened
one-line command; ``fill_blueprint`` validates user-supplied values and turns a
blueprint into a ``cron.jobs.create_job`` kwargs dict (so there is no second job
engine). The form-where-there's-a-screen / agent-fills-where-there's-a-chat
split both consume this same module.

Design choice: users never type raw cron. A blueprint carries a fixed recurrence
in ``schedule_template`` and parameterizes only the human-friendly parts
(time-of-day, weekday set). Blueprints needing full flexibility expose a ``text``
slot named ``schedule`` that passes through verbatim.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = [
    "BlueprintSlot",
    "AutomationBlueprint",
    "CATALOG",
    "get_blueprint",
    "blueprint_form_schema",
    "blueprint_slash_command",
    "blueprint_deeplink",
    "blueprint_catalog_entry",
    "fill_blueprint",
    "BlueprintFillError",
    "WEEKDAY_PRESETS",
]


class BlueprintFillError(ValueError):
    """Raised when supplied slot values fail validation."""


# Slot types the renderers understand.
_SLOT_TYPES = frozenset({"time", "enum", "text", "weekdays"})

# Named weekday recurrences -> cron day-of-week field.
WEEKDAY_PRESETS: Dict[str, str] = {
    "everyday": "*",
    "weekdays": "1-5",
    "weekends": "0,6",
}


@dataclass(frozen=True)
class BlueprintSlot:
    """A single fillable field on a blueprint."""

    name: str
    type: str
    label: str
    default: Any = None
    options: tuple = ()       # for type="enum": allowed values
    optional: bool = False
    help: str = ""
    # When False, ``options`` are suggestions rather than a closed set —
    # any value is accepted (e.g. the deliver slot, where the real set of
    # valid platforms depends on the user's configured gateways and is
    # validated downstream by the cron scheduler).
    strict: bool = True

    def __post_init__(self) -> None:
        if self.type not in _SLOT_TYPES:
            raise ValueError(f"unknown slot type {self.type!r} (slot {self.name})")


@dataclass(frozen=True)
class AutomationBlueprint:
    """A parameterized automation blueprint."""

    key: str
    title: str
    description: str
    category: str
    # Cron expression with ``{slot}`` placeholders, e.g. "{minute} {hour} * * {dow}".
    # Placeholders are filled from resolved slot values (time -> minute/hour,
    # weekdays -> dow). A literal cron string with no placeholders = fixed schedule.
    schedule_template: str
    # Seed instruction for the agent / the cron job prompt; may contain {slot}s.
    prompt_template: str
    slots: List[BlueprintSlot] = field(default_factory=list)
    deliver_default: str = "origin"
    skills: tuple = ()        # skills the job loads before running
    tags: tuple = ()


# ---------------------------------------------------------------------------
# Curated in-repo catalog
# ---------------------------------------------------------------------------

_TIME = lambda default="08:00": BlueprintSlot(  # noqa: E731 - concise factory
    name="time", type="time", label="几点执行？", default=default,
    help="24 小时制本地时间，例如 08:00",
)
_DELIVER = BlueprintSlot(
    name="deliver", type="enum", label="投递到哪里？",
    default="origin", options=("origin", "local", "telegram", "discord", "email"),
    optional=False, strict=False,
    help="origin = 创建时的会话（或工作台配置的主渠道）；local = 仅保存不发送；"
    "也可选任意已连接的平台名称",
)


CATALOG: List[AutomationBlueprint] = [
    AutomationBlueprint(
        key="morning-brief",
        title="晨间简报",
        description="每日简短简报：今日日程、天气，以及需要你关注的紧急事项。",
        category="daily",
        schedule_template="{minute} {hour} * * *",
        prompt_template=(
            "Produce a concise morning briefing for the user: today's calendar "
            "events, the local weather, and any urgent items. Keep it short and "
            "scannable. If no data sources are connected, give a brief "
            "good-morning with the date and offer to connect calendar/email."
        ),
        slots=[_TIME("08:00"), _DELIVER],
        tags=("每日", "简报"),
    ),
    AutomationBlueprint(
        key="important-mail",
        title="重要邮件监控",
        description="定期检查收件箱，仅在邮件确实需要处理时通知你。",
        category="email",
        schedule_template="*/{interval_min} * * * *",
        prompt_template=(
            "Check the user's inbox for new messages since the last run. Surface "
            "ONLY mail matching: {criteria}. Score candidates with the urgency "
            "classifier and deliver only what clears the bar; if nothing does, "
            "respond with [SILENT]. Requires a connected mail source; if none is "
            "configured, explain how to connect one and stop."
        ),
        slots=[
            BlueprintSlot(
                name="interval_min", type="enum", label="检查频率",
                default="30", options=("15", "30", "60"),
                help="两次检查之间的间隔（分钟）",
            ),
            BlueprintSlot(
                name="criteria", type="text",
                label="仅在以下情况通知我…",
                default="需要今天回复、来自上级或家人，或提到截止日期",
            ),
            _DELIVER,
        ],
        tags=("邮件", "监控"),
    ),
    AutomationBlueprint(
        key="weekly-review",
        title="每周回顾",
        description="每周总结：已完成事项、待办事项，以及下周安排。",
        category="weekly",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Produce a weekly review for the user: what was accomplished this "
            "week, still-open items, and next week's calendar. Pull from "
            "connected sources. Keep it tight."
        ),
        slots=[
            _TIME("18:00"),
            BlueprintSlot(
                name="day", type="enum", label="哪一天？",
                default="sunday",
                options=("sunday", "monday", "friday", "saturday"),
            ),
            _DELIVER,
        ],
        tags=("每周", "回顾"),
    ),
    AutomationBlueprint(
        key="workday-start",
        title="工作日开始提醒",
        description="工作日推送当日议程与优先事项，帮你专注开工。",
        category="daily",
        schedule_template="{minute} {hour} * * 1-5",
        prompt_template=(
            "Give the user a brief weekday start-of-day nudge: today's calendar "
            "and the 1-3 highest-priority things to focus on, inferred from "
            "recent context and any task tools. Encouraging, short, one message."
        ),
        slots=[_TIME("09:00"), _DELIVER],
        tags=("每日", "专注"),
    ),
    AutomationBlueprint(
        key="custom-reminder",
        title="自定义提醒",
        description="按你的日程，用你自己的话设置循环提醒。",
        category="general",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template="Remind the user: {what}",
        slots=[
            BlueprintSlot(name="what", type="text", label="提醒我…",
                       default="休息一下并活动活动"),
            _TIME("14:00"),
            BlueprintSlot(
                name="recurrence", type="weekdays", label="重复",
                default="everyday",
                options=tuple(WEEKDAY_PRESETS.keys()),
            ),
            _DELIVER,
        ],
        tags=("提醒",),
    ),
    AutomationBlueprint(
        key="evening-winddown",
        title="晚间收尾",
        description="每日结束时的简短回顾：明日日程一览，以及今晚需要准备的事项。",
        category="daily",
        schedule_template="{minute} {hour} * * *",
        prompt_template=(
            "Give the user a short evening wind-down: tomorrow's calendar, any "
            "early commitments to prep for, and one gentle nudge to wrap up "
            "loose ends from today. Keep it calm and brief — one message. If no "
            "calendar is connected, just offer a friendly sign-off and the "
            "weather for tomorrow."
        ),
        slots=[_TIME("21:00"), _DELIVER],
        tags=("每日", "晚间"),
    ),
    AutomationBlueprint(
        key="news-digest",
        title="主题资讯摘要",
        description="围绕你关心的话题定期推送摘要，自动去重，只发送真正的新内容。",
        category="general",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Search the web for new and noteworthy items about: {topic}. "
            "Dedupe against what you sent in previous runs — only include "
            "genuinely new developments. Deliver a tight digest of at most "
            "{count} bullets, each one line with a link. If nothing new since "
            "last run, respond with [SILENT]."
        ),
        slots=[
            BlueprintSlot(
                name="topic", type="text", label="关注什么主题？",
                default="人工智能与科技",
                help="主题、产品、人物或搜索词",
            ),
            _TIME("18:00"),
            BlueprintSlot(
                name="recurrence", type="weekdays", label="重复",
                default="weekdays",
                options=tuple(WEEKDAY_PRESETS.keys()),
            ),
            BlueprintSlot(
                name="count", type="enum", label="摘要条数？",
                default="5", options=("3", "5", "8"),
            ),
            _DELIVER,
        ],
        tags=("摘要", "调研"),
    ),
    AutomationBlueprint(
        key="bill-renewal-watch",
        title="账单与续费提醒",
        description="在定期付款、订阅续费或截止日期前提醒你，避免意外扣款。",
        category="general",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Remind the user about an upcoming payment or renewal: {what}. "
            "Phrase it as an actionable heads-up (e.g. 'review or cancel before "
            "it renews'), not just a notification. One short message."
        ),
        slots=[
            BlueprintSlot(
                name="what", type="text", label="什么即将到期？",
                default="流媒体订阅即将续费",
            ),
            _TIME("10:00"),
            BlueprintSlot(
                name="recurrence", type="weekdays", label="重复",
                default="everyday",
                options=tuple(WEEKDAY_PRESETS.keys()),
            ),
            _DELIVER,
        ],
        tags=("提醒", "财务"),
    ),
    AutomationBlueprint(
        key="habit-checkin",
        title="习惯打卡",
        description="定期提醒你坚持习惯，并反思今天是否完成。",
        category="general",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Nudge the user about their habit: {habit}. Ask whether they did it "
            "today, keep it warm and non-judgmental, and offer a one-line word "
            "of encouragement. One short message."
        ),
        slots=[
            BlueprintSlot(
                name="habit", type="text", label="哪个习惯？",
                default="阅读 20 分钟",
            ),
            _TIME("20:00"),
            BlueprintSlot(
                name="recurrence", type="weekdays", label="重复",
                default="everyday",
                options=tuple(WEEKDAY_PRESETS.keys()),
            ),
            _DELIVER,
        ],
        tags=("习惯", "健康"),
    ),
    AutomationBlueprint(
        key="hydration-move",
        title="补水与活动提醒",
        description="白天定期提醒喝水、起身活动、拉伸。",
        category="general",
        schedule_template="0 {start_hour}-{end_hour}/{interval_hours} * * 1-5",
        prompt_template=(
            "Send the user a brief, friendly nudge to drink some water, stand "
            "up, and stretch for a moment. Vary the wording each time so it "
            "doesn't feel robotic. One short line."
        ),
        slots=[
            BlueprintSlot(
                name="interval_hours", type="enum", label="提醒频率",
                default="1", options=("1", "2", "3"),
                help="两次提醒之间的间隔（小时）",
            ),
            BlueprintSlot(
                name="start_hour", type="enum", label="开始时间",
                default="9", options=("7", "8", "9", "10"),
                help="活跃时段的首个小时（24 小时制）",
            ),
            BlueprintSlot(
                name="end_hour", type="enum", label="结束时间",
                default="17", options=("16", "17", "18", "19"),
                help="活跃时段的最后一个小时（24 小时制）",
            ),
            _DELIVER,
        ],
        tags=("健康", "专注"),
    ),
    AutomationBlueprint(
        key="meal-plan",
        title="每周膳食计划",
        description="根据饮食偏好与烹饪时间，生成每周膳食计划及合并后的购物清单。",
        category="weekly",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Build the user a meal plan for the coming week: {meals} per day, "
            "suited to a {diet} diet and roughly {effort} cooking effort. "
            "Include a consolidated grocery list grouped by aisle. Keep blueprints "
            "simple and skimmable."
        ),
        slots=[
            BlueprintSlot(
                name="diet", type="enum", label="饮食偏好？",
                default="无限制",
                options=("无限制", "素食", "纯素", "高蛋白", "低碳水"),
            ),
            BlueprintSlot(
                name="meals", type="enum", label="每天几餐？",
                default="仅晚餐",
                options=("仅晚餐", "午餐和晚餐", "三餐"),
            ),
            BlueprintSlot(
                name="effort", type="enum", label="烹饪投入？",
                default="快手", options=("快手", "适中", "精致"),
            ),
            _TIME("17:00"),
            BlueprintSlot(
                name="day", type="enum", label="哪一天？",
                default="sunday",
                options=("sunday", "monday", "friday", "saturday"),
            ),
            _DELIVER,
        ],
        tags=("每周", "饮食"),
    ),
    AutomationBlueprint(
        key="learn-daily",
        title="每日学习点滴",
        description="每天一小节，循序渐进学习你感兴趣的主题。",
        category="daily",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Teach the user one bite-sized lesson about: {topic}. Build on "
            "earlier lessons so it progresses rather than repeating. Keep it to "
            "a couple of short paragraphs with one concrete example, and end "
            "with a single question to check understanding."
        ),
        slots=[
            BlueprintSlot(
                name="topic", type="text", label="学习主题…",
                default="西班牙语词汇",
            ),
            _TIME("08:30"),
            BlueprintSlot(
                name="recurrence", type="weekdays", label="重复",
                default="weekdays",
                options=tuple(WEEKDAY_PRESETS.keys()),
            ),
            _DELIVER,
        ],
        tags=("学习", "每日"),
    ),
    AutomationBlueprint(
        key="gratitude-journal",
        title="感恩与反思",
        description="温和的晚间提示，回顾今天并记录值得感恩的事。",
        category="general",
        schedule_template="{minute} {hour} * * {dow}",
        prompt_template=(
            "Send the user a short, warm reflection prompt for the end of the "
            "day — invite them to note one thing that went well, one thing they "
            "are grateful for, and one small win. If they reply, acknowledge it "
            "kindly. One message."
        ),
        slots=[
            _TIME("21:30"),
            BlueprintSlot(
                name="recurrence", type="weekdays", label="重复",
                default="everyday",
                options=tuple(WEEKDAY_PRESETS.keys()),
            ),
            _DELIVER,
        ],
        tags=("健康", "反思"),
    ),
    AutomationBlueprint(
        key="on-this-day",
        title="今日发现",
        description="每日一点好奇心：历史上的今天、冷知识或每日一词。",
        category="daily",
        schedule_template="{minute} {hour} * * *",
        prompt_template=(
            "Give the user one interesting '{flavor}' item for today — keep it "
            "short, surprising, and genuinely interesting. One or two sentences, "
            "no filler."
        ),
        slots=[
            BlueprintSlot(
                name="flavor", type="enum", label="什么类型？",
                default="历史上的今天",
                options=("历史上的今天", "每日一词", "科学冷知识", "每日名言"),
            ),
            _TIME("07:30"),
            _DELIVER,
        ],
        tags=("每日", "趣味"),
    ),
]

_CATALOG_BY_KEY = {r.key: r for r in CATALOG}


def get_blueprint(key: str) -> Optional[AutomationBlueprint]:
    return _CATALOG_BY_KEY.get(key)


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

def blueprint_form_schema(blueprint: AutomationBlueprint) -> Dict[str, Any]:
    """Emit the JSON a form renderer (dashboard / GUI) needs for this blueprint."""
    return {
        "key": blueprint.key,
        "title": blueprint.title,
        "description": blueprint.description,
        "category": blueprint.category,
        "tags": list(blueprint.tags),
        "fields": [
            {
                "name": s.name,
                "type": s.type,
                "label": s.label,
                "default": s.default,
                "options": list(s.options),
                "optional": s.optional,
                "strict": s.strict,
                "help": s.help,
            }
            for s in blueprint.slots
        ],
    }


def blueprint_slash_command(blueprint: AutomationBlueprint, values: Optional[Dict[str, Any]] = None) -> str:
    """Build the flattened ``/blueprint <key> slot=val …`` command string.

    Uses each slot's default when ``values`` is omitted, so the docs/dashboard
    can show a ready-to-paste command. Free-text slots are quoted.
    """
    values = values or {}
    parts = [f"/blueprint {blueprint.key}"]
    for s in blueprint.slots:
        val = values.get(s.name, s.default)
        if val is None or val == "":
            if s.optional:
                continue
            val = ""
        sval = str(val)
        if s.type == "text" or " " in sval:
            sval = '"' + sval.replace('"', '\\"') + '"'
        parts.append(f"{s.name}={sval}")
    return " ".join(parts)


def blueprint_deeplink(blueprint: AutomationBlueprint, values: Optional[Dict[str, Any]] = None) -> str:
    """Build the ``hermes://blueprint/<key>?slot=val`` deep-link URL."""
    from urllib.parse import quote, urlencode

    values = values or {}
    query = {}
    for s in blueprint.slots:
        val = values.get(s.name, s.default)
        if val not in (None, ""):
            query[s.name] = str(val)
    qs = ("?" + urlencode(query)) if query else ""
    return f"hermes://blueprint/{quote(blueprint.key)}{qs}"


_DAY_ZH = {
    "sunday": "周日", "monday": "周一", "tuesday": "周二", "wednesday": "周三",
    "thursday": "周四", "friday": "周五", "saturday": "周六",
}
_RECURRENCE_ZH = {
    "everyday": "每天", "weekdays": "工作日", "weekends": "周末",
}


def _scope_zh(scope: str) -> str:
    if not scope:
        return ""
    return _RECURRENCE_ZH.get(scope, _DAY_ZH.get(scope, scope))


def _humanize_schedule(blueprint: AutomationBlueprint) -> str:
    """A short human-readable description of when a blueprint runs (defaults)."""
    sched = blueprint.schedule_template
    if sched.startswith("*/"):
        iv = next((s for s in blueprint.slots if s.name == "interval_min"), None)
        every = (iv.default if iv else None) or sched.split("/")[1].split()[0]
        return f"每 {every} 分钟"
    if "{interval_hours}" in sched:
        iv = next((s for s in blueprint.slots if s.name == "interval_hours"), None)
        every = str((iv.default if iv else None) or "1")
        scope = "工作日，" if "* * 1-5" in sched else ""
        if every == "1":
            return f"{scope}每小时"
        return f"{scope}每 {every} 小时"
    time_slot = next((s for s in blueprint.slots if s.type == "time"), None)
    when = time_slot.default if time_slot else None
    if "* * 1-5" in sched:
        return f"工作日 {when}" if when else "每个工作日"
    if "{dow}" in sched:
        day_slot = next((s for s in blueprint.slots if s.name in ("day", "recurrence")), None)
        scope = _scope_zh(str((day_slot.default if day_slot else "") or ""))
        if scope and when:
            return f"{scope} {when}"
        return f"{when}" if when else "按计划执行"
    if when:
        return f"每天 {when}"
    return "按计划执行"


def blueprint_catalog_entry(blueprint: AutomationBlueprint) -> Dict[str, Any]:
    """Unified serializable shape for a blueprint — used by the docs generator
    and the dashboard API. Combines the form schema, the ready-to-paste slash
    command, the deep-link URL, and a human-readable schedule.
    """
    return {
        **blueprint_form_schema(blueprint),
        "schedule": blueprint.schedule_template,
        "scheduleHuman": _humanize_schedule(blueprint),
        "command": blueprint_slash_command(blueprint),
        "appUrl": blueprint_deeplink(blueprint),
    }


# ---------------------------------------------------------------------------
# Fill + validate + translate to a create_job spec
# ---------------------------------------------------------------------------

_TIME_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")
_DAY_TO_DOW = {
    "sunday": "0", "monday": "1", "tuesday": "2", "wednesday": "3",
    "thursday": "4", "friday": "5", "saturday": "6",
}


def _resolve_schedule(blueprint: AutomationBlueprint, values: Dict[str, Any]) -> str:
    """Fill the schedule_template placeholders from resolved slot values."""
    sched = blueprint.schedule_template

    # A free-text `schedule` slot passes through verbatim (full flexibility).
    if "schedule" in values and values["schedule"]:
        return str(values["schedule"])

    repl: Dict[str, str] = {}

    # time -> minute/hour
    time_val = values.get("time")
    if "{minute}" in sched or "{hour}" in sched:
        if not time_val:
            raise BlueprintFillError("请填写执行时间")
        m = _TIME_RE.match(str(time_val).strip())
        if not m:
            raise BlueprintFillError(f"时间格式无效 {time_val!r} — 请使用 HH:MM（24 小时制）")
        repl["hour"] = str(int(m.group(1)))
        repl["minute"] = str(int(m.group(2)))

    # weekday set -> dow
    if "{dow}" in sched:
        if "recurrence" in values:
            preset = str(values.get("recurrence", "everyday")).lower()
            if preset not in WEEKDAY_PRESETS:
                raise BlueprintFillError(
                    f"未知的重复规则 {preset!r} — 可选：{', '.join(WEEKDAY_PRESETS)}"
                )
            repl["dow"] = WEEKDAY_PRESETS[preset]
        elif "day" in values:
            day = str(values.get("day", "")).lower()
            if day not in _DAY_TO_DOW:
                raise BlueprintFillError(f"未知的星期 {day!r}")
            repl["dow"] = _DAY_TO_DOW[day]
        else:
            repl["dow"] = "*"

    # interval (minutes) for */N schedules
    if "{interval_min}" in sched:
        iv = str(values.get("interval_min", "")).strip()
        if not iv.isdigit() or int(iv) <= 0:
            raise BlueprintFillError(f"间隔无效 {iv!r} — 请输入正整数（分钟）")
        repl["interval_min"] = iv

    # Any remaining {slot} placeholders are filled verbatim from validated
    # enum/text slot values (e.g. an hour-range window). Enum options have
    # already been checked in fill_blueprint, so these are safe to interpolate.
    for name in re.findall(r"\{(\w+)\}", sched):
        if name not in repl and name in values:
            repl[name] = str(values[name])

    try:
        return sched.format(**repl)
    except KeyError as e:  # pragma: no cover - template/slot mismatch is a dev error
        raise BlueprintFillError(f"schedule template missing value for {e}") from e


def fill_blueprint(
    blueprint: AutomationBlueprint,
    values: Dict[str, Any],
    *,
    origin: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Validate ``values`` and return ``cron.jobs.create_job`` kwargs.

    Missing required (non-optional) slots raise BlueprintFillError naming the
    slot, so a form can show field errors and the agent knows what to ask.
    Unknown slot names are rejected (a typo'd ``tiem=07:15`` must not silently
    create a job with the default time). Enum values are checked against their
    options. The result is passed straight to ``create_job`` — no second schema.
    """
    known = {s.name for s in blueprint.slots}
    unknown = sorted(set(values) - known)
    if unknown:
        raise BlueprintFillError(
            f"unknown slot{'s' if len(unknown) > 1 else ''}: "
            f"{', '.join(unknown)} — valid: {', '.join(s.name for s in blueprint.slots)}"
        )
    resolved: Dict[str, Any] = {}
    for s in blueprint.slots:
        raw = values.get(s.name, s.default)
        if raw in (None, ""):
            if s.optional:
                continue
            raise BlueprintFillError(f"缺少必填项：{s.name}（{s.label}）")
        if s.type == "enum" and s.strict and s.options and str(raw) not in {str(o) for o in s.options}:
            raise BlueprintFillError(
                f"{s.name}={raw!r} 不在允许范围内 — 可选：{', '.join(map(str, s.options))}"
            )
        resolved[s.name] = raw

    schedule = _resolve_schedule(blueprint, resolved)

    # Render the prompt with whatever slots it references.
    try:
        prompt = blueprint.prompt_template.format(**resolved)
    except KeyError as e:
        raise BlueprintFillError(f"blueprint prompt missing value for {e}") from e

    spec: Dict[str, Any] = {
        "prompt": prompt,
        "schedule": schedule,
        "name": blueprint.title,
        "deliver": resolved.get("deliver", blueprint.deliver_default),
    }
    if blueprint.skills:
        spec["skills"] = list(blueprint.skills)
    if origin is not None:
        spec["origin"] = origin
    return spec
