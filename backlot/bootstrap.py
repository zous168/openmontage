"""Backlot library bootstrap — empty project workspace creation only.

The project board remains a read-only observer of ``projects/<id>/``. This
module is the *only* server-side write path: it calls ``init_project`` to lay
down the canonical directory tree and ``project.json`` marker so the board can
render the correct pipeline rail before the agent runs.

It does NOT run pipelines, write checkpoints, or mutate in-progress productions.
Collected ``production_inputs`` land in ``meta.json`` for the Cursor agent.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml

from lib.checkpoint import PROJECTS_DIR, init_project
from lib.paths import REPO_ROOT
from lib.pipeline_loader import PIPELINE_DEFS_DIR, list_pipelines, load_pipeline_readonly
from lib.source_media_review import detect_media_type

# Internal / test manifests — hidden from the library picker by default.
# reference-driven is a first-class pipeline; other pipelines may optionally attach
# reference_url / reference_media_path and invoke meta/video-reference-analyst as a skill.
_HIDDEN_PIPELINES = frozenset({"framework-smoke"})

_PROJECT_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_MEDIA_URL_RE = re.compile(
    r"https?://[^\s<>\"'，。；、）\]】]+",
    re.IGNORECASE,
)


def normalize_media_url(raw: Any) -> str:
    """Extract the first http(s) URL from pasted share text (e.g. Douyin copy string)."""
    text = str(raw or "").strip()
    if not text:
        return ""
    match = _MEDIA_URL_RE.search(text)
    if match:
        return match.group(0).rstrip(".,;)]}」")
    return text

MEDIA_STAGING_DIR = REPO_ROOT / ".backlot" / "media-staging"
MAX_STAGED_MEDIA_BYTES = 2 * 1024 * 1024 * 1024  # 2 GiB
_STAGING_VIDEO_EXT = frozenset({".mp4", ".mov", ".webm", ".avi", ".mkv", ".m4v"})
_STAGING_AUDIO_EXT = frozenset({".mp3", ".wav", ".aac", ".flac", ".ogg", ".m4a", ".opus"})
_STAGING_MEDIA_EXT = _STAGING_VIDEO_EXT | _STAGING_AUDIO_EXT

# id -> (中文名, 一句话说明)
PIPELINE_LABELS_ZH: dict[str, tuple[str, str]] = {
    "reference-driven": (
        "参考视频反推",
        "分析参考片的节奏、结构与风格，产出差异化方案后再进入制作（非 1:1 克隆）",
    ),
    "animated-explainer": ("动画解说", "从主题全自动生成解说视频（调研 → 方案 → 脚本 → 资产）"),
    "avatar-spokesperson": ("数字人主播", "数字人出镜口播：带货、产品介绍、短讲解"),
    "animation": ("动画 / 动效", "动态图形、Manim、Remotion 或 AI 混合动画"),
    "cinematic": ("电影级短片", "品牌预告、情绪短片、分层剪辑与调色"),
    "screen-demo": ("屏幕演示", "软件教程、产品 Demo、操作录屏"),
    "hybrid": ("混合制作", "实拍/口播为主，叠加 AI 或素材辅助"),
    "talking-head": ("真人口播剪辑", "已有真人出镜素材：转写、剪辑、字幕、混音"),
    "documentary-montage": ("纪录片蒙太奇", "真实素材检索拼贴，主题蒙太奇"),
    "clip-factory": ("短视频切片", "从长视频切多条社交短视频"),
    "podcast-repurpose": ("播客再利用", "长播客 → 高光片段、引用卡、章节视频"),
    "localization-dub": ("多语言配音", "翻译、配音、字幕，可选口型同步"),
    "character-animation": ("角色动画", "本地 SVG 卡通角色：绑骨、姿势库、时间线"),
}

PLATFORM_OPTIONS: list[dict[str, str]] = [
    {"value": "douyin", "label_zh": "抖音"},
    {"value": "weixin_channels", "label_zh": "微信视频号"},
    {"value": "bilibili", "label_zh": "B站"},
    {"value": "xiaohongshu", "label_zh": "小红书"},
    {"value": "youtube", "label_zh": "YouTube"},
    {"value": "tiktok", "label_zh": "TikTok"},
    {"value": "instagram", "label_zh": "Instagram"},
    {"value": "linkedin", "label_zh": "LinkedIn"},
    {"value": "generic", "label_zh": "通用 / 多平台"},
]

LANGUAGE_OPTIONS: list[dict[str, str]] = [
    {"value": "zh", "label_zh": "中文"},
    {"value": "en", "label_zh": "英语"},
    {"value": "ja", "label_zh": "日语"},
    {"value": "ko", "label_zh": "韩语"},
    {"value": "es", "label_zh": "西班牙语"},
    {"value": "fr", "label_zh": "法语"},
    {"value": "de", "label_zh": "德语"},
    {"value": "other", "label_zh": "其他"},
]

DOCUMENTARY_TONE_OPTIONS: list[dict[str, str]] = [
    {"value": "contemplative", "label_zh": "沉思 / 诗意"},
    {"value": "urgent", "label_zh": "紧迫 / 新闻感"},
    {"value": "melancholic", "label_zh": "忧郁 / 怀旧"},
    {"value": "hopeful", "label_zh": "希望 / 向上"},
    {"value": "ironic", "label_zh": "反讽 / 疏离"},
]

PODCAST_OUTPUT_OPTIONS: list[dict[str, str]] = [
    {"value": "audiogram_clips", "label_zh": "波形 audiogram 短视频"},
    {"value": "quote_clips", "label_zh": "金句引用卡短视频"},
    {"value": "companion_video", "label_zh": "完整播客伴生视频"},
    {"value": "mixed", "label_zh": "混合多种输出"},
]

DUB_MODE_OPTIONS: list[dict[str, str]] = [
    {"value": "subtitles_only", "label_zh": "仅字幕翻译"},
    {"value": "dub_audio", "label_zh": "配音（无口型）"},
    {"value": "dub_lipsync", "label_zh": "配音 + 口型同步"},
]

SCREEN_DEMO_MODE_OPTIONS: list[dict[str, str]] = [
    {"value": "real_capture", "label_zh": "实拍录屏（真实界面操作）"},
    {"value": "synthetic_terminal", "label_zh": "合成终端动画（CLI / 安装演示）"},
]


def _f(
    key: str,
    ftype: str,
    label_zh: str,
    *,
    required: bool = True,
    hint_zh: str = "",
    **extra: Any,
) -> dict[str, Any]:
    field: dict[str, Any] = {
        "key": key,
        "type": ftype,
        "label_zh": label_zh,
        "required": required,
    }
    if hint_zh:
        field["hint_zh"] = hint_zh
    field.update(extra)
    return field


_PLATFORM = _f("target_platform", "select", "发布平台", options=PLATFORM_OPTIONS)
_DURATION = _f(
    "target_duration_seconds",
    "number",
    "目标时长（秒）",
    required=False,
    hint_zh="可选；留空则由 Agent 或素材时长决定",
    min=1,
    max=7200,
)
_TOPIC = _f("topic", "text", "视频主题", hint_zh="要讲什么、为谁做、核心信息")
_SOURCE = _f(
    "source_media_path",
    "path",
    "源素材",
    hint_zh="选择本地视频/音频，或粘贴完整路径；创建时复制进项目",
)
_SOURCE_OPTIONAL = _f(
    "source_media_path",
    "path",
    "源素材（可选）",
    required=False,
    hint_zh="选择文件或粘贴路径；有实拍/现有素材时填写",
)
_REFERENCE_URL = _f(
    "reference_url",
    "url",
    "参考视频链接（可选）",
    required=False,
    hint_zh="YouTube / Short 等；填写后 Agent 先运行 video-reference-analyst，再按本流水线制作",
)
_REFERENCE_PATH = _f(
    "reference_media_path",
    "path",
    "参考视频（可选）",
    required=False,
    hint_zh="选择本地视频或粘贴路径；与参考链接二选一",
)

# Per-pipeline bootstrap form schemas (shown in Backlot library create modal).
PIPELINE_BOOTSTRAP_FIELDS: dict[str, list[dict[str, Any]]] = {
    "talking-head": [
        _SOURCE,
        _PLATFORM,
        _DURATION,
    ],
    "clip-factory": [
        _SOURCE,
        _f("clip_count", "number", "目标切片数量", hint_zh="计划输出的短视频条数", min=1, max=30, required=True),
        _PLATFORM,
        _f(
            "clip_duration_seconds",
            "number",
            "单条目标时长（秒）",
            required=False,
            hint_zh="可选；如 30–60 秒竖屏切片",
            min=5,
            max=600,
        ),
    ],
    "podcast-repurpose": [
        _SOURCE,
        _f("output_mode", "select", "输出类型", options=PODCAST_OUTPUT_OPTIONS),
        _f("clip_count", "number", "目标切片数量", hint_zh="audiogram / 金句类输出", min=1, max=30, required=True),
        _PLATFORM,
    ],
    "localization-dub": [
        _SOURCE,
        _f("source_language", "select", "源语言", options=LANGUAGE_OPTIONS),
        _f(
            "target_languages",
            "text",
            "目标语言",
            hint_zh="逗号分隔，如：en,ja 或 英语,日语",
        ),
        _f("dub_mode", "select", "本地化方式", options=DUB_MODE_OPTIONS),
        _PLATFORM,
    ],
    "hybrid": [
        _SOURCE,
        _TOPIC,
        _PLATFORM,
        _DURATION,
    ],
    "screen-demo": [
        _f("production_mode", "select", "演示模式", options=SCREEN_DEMO_MODE_OPTIONS),
        _f("demo_brief", "text", "演示内容说明", hint_zh="要展示的产品、功能或终端操作流程"),
        _f(
            "source_media_path",
            "path",
            "录屏素材",
            required=False,
            hint_zh="实拍录屏模式：选择文件或粘贴路径",
        ),
        _PLATFORM,
        _DURATION,
    ],
    "animated-explainer": [
        _TOPIC,
        _PLATFORM,
        _f("target_duration_seconds", "number", "目标时长（秒）", hint_zh="建议 60–180 秒", min=15, max=7200),
        _REFERENCE_URL,
        _REFERENCE_PATH,
    ],
    "cinematic": [
        _TOPIC,
        _PLATFORM,
        _DURATION,
        _SOURCE_OPTIONAL,
        _REFERENCE_URL,
        _REFERENCE_PATH,
    ],
    "animation": [
        _TOPIC,
        _PLATFORM,
        _f("target_duration_seconds", "number", "目标时长（秒）", hint_zh="动效解说通常 30–120 秒", min=15, max=7200),
        _REFERENCE_URL,
        _REFERENCE_PATH,
    ],
    "avatar-spokesperson": [
        _TOPIC,
        _f(
            "script_or_offer",
            "text",
            "口播文案 / 带货要点",
            hint_zh="要讲的核心话术、产品卖点、CTA；可稍后细化",
        ),
        _PLATFORM,
        _DURATION,
    ],
    "character-animation": [
        _TOPIC,
        _PLATFORM,
        _f("target_duration_seconds", "number", "目标时长（秒）", hint_zh="角色动画通常 30–90 秒", min=15, max=7200),
        _REFERENCE_URL,
        _REFERENCE_PATH,
    ],
    "documentary-montage": [
        _f(
            "thematic_question",
            "text",
            "主题问题",
            hint_zh="一句话核心命题，如「技术乐观主义为何失效？」",
        ),
        _f("tone_register", "select", "情绪基调", options=DOCUMENTARY_TONE_OPTIONS),
        _PLATFORM,
        _f("target_duration_seconds", "number", "目标时长（秒）", hint_zh="蒙太奇通常 90–300 秒", min=30, max=7200),
        _REFERENCE_URL,
        _REFERENCE_PATH,
    ],
    "reference-driven": [
        _f(
            "reference_url",
            "url",
            "参考视频链接",
            required=False,
            hint_zh="可直接粘贴抖音分享文案，系统会自动提取链接并通过 VidDown 下载；与本地参考视频二选一",
        ),
        _f(
            "reference_media_path",
            "path",
            "参考视频（本地）",
            required=False,
            hint_zh="选择本地视频或粘贴路径；与参考链接二选一",
        ),
        _f(
            "topic",
            "text",
            "差异化方向（可选）",
            required=False,
            hint_zh="希望借鉴参考片哪方面、但要做出什么不同；留空则由 Agent 提案",
        ),
        _PLATFORM,
        _DURATION,
    ],
    "framework-smoke": [],
}


def pipeline_label_zh(pipeline_id: Optional[str]) -> str:
    """Chinese display name for a pipeline id (falls back to id or「未知」)."""
    pid = (pipeline_id or "").strip()
    if not pid or pid == "unknown":
        return "未知"
    label, _ = PIPELINE_LABELS_ZH.get(pid, (pid, ""))
    return label


def bootstrap_fields_for_pipeline(pipeline_id: str) -> list[dict[str, Any]]:
    """Form fields the library UI should collect for this pipeline."""
    from lib.deliverable_spec import deliverable_bootstrap_fields
    from lib.publish_intake import cover_bootstrap_fields

    if pipeline_id in PIPELINE_BOOTSTRAP_FIELDS:
        fields = list(PIPELINE_BOOTSTRAP_FIELDS[pipeline_id])
    else:
        fields = []
    if any(f.get("key") == "target_platform" for f in fields):
        fields.extend(deliverable_bootstrap_fields())
        fields.extend(cover_bootstrap_fields())
    return fields


class BootstrapError(ValueError):
    """Invalid bootstrap request."""


def _read_manifest_raw(name: str) -> dict[str, Any]:
    path = PIPELINE_DEFS_DIR / f"{name}.yaml"
    if not path.is_file():
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data if isinstance(data, dict) else {}
    except (yaml.YAMLError, OSError):
        return {}


def pipeline_ui_from_manifest(pipeline_id: str, manifest: dict[str, Any]) -> dict[str, Any]:
    """Resolve display metadata: manifest ``ui`` block overrides bootstrap defaults."""
    ui = manifest.get("ui") if isinstance(manifest.get("ui"), dict) else {}
    default_label, default_summary = PIPELINE_LABELS_ZH.get(pipeline_id, (pipeline_id, ""))
    hidden = bool(ui.get("hidden")) if "hidden" in ui else pipeline_id in _HIDDEN_PIPELINES
    return {
        "label_zh": (ui.get("label_zh") or default_label or pipeline_id).strip(),
        "summary_zh": (ui.get("summary_zh") or default_summary or "").strip(),
        "hidden": hidden,
        "skill_dir": (ui.get("skill_dir") or "").strip() or None,
    }


def _pipeline_catalog_entry(name: str) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    try:
        manifest = load_pipeline_readonly(name)
    except Exception:
        manifest = _read_manifest_raw(name)
    if not manifest:
        raise BootstrapError(f"未知流水线: {name}")

    ui = pipeline_ui_from_manifest(name, manifest)
    desc = manifest.get("description") or ""
    if isinstance(desc, str):
        desc = " ".join(desc.split())
    stability = manifest.get("stability", "unknown")
    category = manifest.get("category", "unknown")
    return {
        "id": name,
        "label_zh": ui["label_zh"],
        "summary_zh": ui["summary_zh"],
        "description": desc[:280],
        "stability": stability,
        "category": category,
        "hidden": ui["hidden"],
        "bootstrap_fields": bootstrap_fields_for_pipeline(name),
    }


def list_pipeline_catalog(*, include_hidden: bool = False) -> list[dict[str, Any]]:
    """Manifest-backed pipeline list for the library create form."""
    names = sorted(list_pipelines(PIPELINE_DEFS_DIR))
    entries = [_pipeline_catalog_entry(n) for n in names]
    if not include_hidden:
        entries = [e for e in entries if not e["hidden"]]
    entries.sort(key=lambda e: e["label_zh"])
    return entries


def validate_project_id(project_id: str) -> str:
    pid = (project_id or "").strip().lower()
    if not pid or len(pid) > 64:
        raise BootstrapError("项目 ID 长度须为 1–64 个字符。")
    if not _PROJECT_ID_RE.fullmatch(pid):
        raise BootstrapError("项目 ID 仅允许小写字母、数字和连字符（如 my-promo-video）。")
    return pid


def _parse_number(raw: Any, field: dict[str, Any]) -> int:
    label = field.get("label_zh", "数值")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        raise BootstrapError(f"{label}须为数字。") from None
    lo = field.get("min")
    hi = field.get("max")
    if lo is not None and value < int(lo):
        raise BootstrapError(f"{label}不能小于 {lo}。")
    if hi is not None and value > int(hi):
        raise BootstrapError(f"{label}不能大于 {hi}。")
    return value


def _parse_text(raw: Any, field: dict[str, Any]) -> str:
    text = str(raw).strip()
    label = field.get("label_zh", "字段")
    min_len = int(field.get("min_length", 2))
    max_len = int(field.get("max_length", 2000))
    if len(text) < min_len:
        raise BootstrapError(f"{label}至少 {min_len} 个字符。")
    if len(text) > max_len:
        raise BootstrapError(f"{label}不能超过 {max_len} 个字符。")
    return text


def _parse_select(raw: Any, field: dict[str, Any]) -> str:
    value = str(raw).strip()
    options = field.get("options") or []
    allowed = {o["value"] for o in options}
    label = field.get("label_zh", "选项")
    if value not in allowed:
        raise BootstrapError(f"{label}无效，请重新选择。")
    return value


def _apply_pipeline_rules(pipeline_type: str, normalized: dict[str, Any], raw: dict[str, Any]) -> None:
    """Cross-field validation after scalar parsing."""
    if pipeline_type == "screen-demo":
        mode = normalized.get("production_mode")
        src = str(raw.get("source_media_path") or "").strip()
        if mode == "real_capture" and not src:
            raise BootstrapError("实拍录屏模式须填写录屏素材路径。")

    if pipeline_type == "localization-dub":
        langs = normalized.get("target_languages", "")
        parts = [p.strip() for p in re.split(r"[,，、\s]+", langs) if p.strip()]
        if not parts:
            raise BootstrapError("请填写至少一种目标语言。")
        normalized["target_languages"] = parts

    if pipeline_type == "documentary-montage":
        # Alias for downstream brief metadata
        normalized.setdefault("topic", normalized.get("thematic_question"))

    if pipeline_type == "reference-driven":
        url = str(raw.get("reference_url") or normalized.get("reference_url") or "").strip()
        path = str(raw.get("reference_media_path") or normalized.get("reference_media_path") or "").strip()
        if not url and not path:
            raise BootstrapError("请填写参考视频链接或本地参考视频。")

def validate_production_inputs(
    pipeline_type: str,
    inputs: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Validate and normalize bootstrap form values for *pipeline_type*."""
    fields = bootstrap_fields_for_pipeline(pipeline_type)
    if not fields:
        return {}

    raw = dict(inputs or {})
    normalized: dict[str, Any] = {}

    for field in fields:
        key = field["key"]
        ftype = field["type"]
        required = bool(field.get("required"))
        value = raw.get(key)

        if required and (value is None or str(value).strip() == ""):
            raise BootstrapError(f"请填写{field['label_zh']}。")
        if value is None or str(value).strip() == "":
            continue

        if ftype == "select":
            normalized[key] = _parse_select(value, field)
        elif ftype == "number":
            normalized[key] = _parse_number(value, field)
        elif ftype == "path":
            normalized[key] = str(value).strip().strip('"').strip("'")
        elif ftype == "url":
            normalized[key] = normalize_media_url(value)[:2000]
        else:
            normalized[key] = _parse_text(value, field)

    _apply_pipeline_rules(pipeline_type, normalized, raw)
    return normalized


def _safe_upload_name(filename: str) -> str:
    raw = (filename or "upload.bin").replace("\\", "/").split("/")[-1].strip()
    safe = re.sub(r"[^\w.\- ()\u4e00-\u9fff]", "_", raw).strip("._")
    return safe[:180] or "upload.bin"


def stage_uploaded_media(
    *,
    filename: str,
    stream,
    max_bytes: int = MAX_STAGED_MEDIA_BYTES,
    staging_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Save an uploaded file to staging; return absolute path for bootstrap ingest."""
    safe = _safe_upload_name(filename)
    ext = Path(safe).suffix.lower()
    if ext not in _STAGING_MEDIA_EXT:
        raise BootstrapError(
            "不支持的文件格式。请使用常见视频（.mp4、.mov、.webm）或音频（.mp3、.wav、.m4a）。"
        )

    base = staging_dir or MEDIA_STAGING_DIR
    dest_dir = base / uuid.uuid4().hex
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe

    size = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = stream.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise BootstrapError("文件过大（上限 2 GB）。")
                out.write(chunk)
    except Exception:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise

    if size == 0:
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise BootstrapError("上传文件为空。")

    media_type = detect_media_type(dest)
    if media_type not in ("video", "audio"):
        shutil.rmtree(dest_dir, ignore_errors=True)
        raise BootstrapError("无法识别为视频或音频文件。")

    return {
        "path": str(dest.resolve()),
        "filename": safe,
        "media_type": media_type,
        "size_bytes": size,
    }


def _probe_video_codec(path: Path) -> Optional[str]:
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=codec_name", "-of", "csv=p=0",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if proc.returncode == 0:
            return (proc.stdout or "").strip().lower() or None
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def _needs_browser_preview(codec: Optional[str], ext: str) -> bool:
    if ext not in {".mp4", ".webm", ".mov", ".m4v"}:
        return True
    if not codec:
        return False
    return codec in {"hevc", "h265", "mpeg4", "msmpeg4v3", "wmv3", "vc1", "prores"}


def _write_browser_preview(project_dir: Path, src: Path) -> None:
    """Transcode to H.264 MP4 so Backlot can play source in-browser immediately."""
    dest = project_dir / "assets" / "video" / "source_preview.mp4"
    if dest.is_file():
        return
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error", "-i", str(src),
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
            str(dest),
        ],
        check=True,
        timeout=600,
    )


def _ingest_source_media(project_dir: Path, source_path: str) -> tuple[str, str]:
    """Copy source file into project assets. Returns (project_rel_path, original_path)."""
    raw = (source_path or "").strip().strip('"').strip("'")
    if not raw:
        raise BootstrapError("请填写源素材路径。")
    src = Path(raw).expanduser()
    if not src.is_file():
        raise BootstrapError(f"找不到源文件：{raw}")
    media_type = detect_media_type(src)
    if media_type == "video":
        dest_dir = project_dir / "assets" / "video"
    elif media_type == "audio":
        dest_dir = project_dir / "assets" / "audio"
    else:
        raise BootstrapError("源文件须为常见视频或音频格式（如 .mp4、.mov、.mp3）。")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"source{src.suffix.lower()}"
    shutil.copy2(src, dest)
    if media_type == "video":
        codec = _probe_video_codec(dest)
        if _needs_browser_preview(codec, dest.suffix.lower()):
            try:
                _write_browser_preview(project_dir, dest)
            except (OSError, subprocess.SubprocessError):
                pass
    rel = dest.relative_to(project_dir).as_posix()
    return rel, str(src.resolve())


def _ingest_reference_media(project_dir: Path, source_path: str) -> tuple[str, str]:
    """Copy local reference video into project assets. Returns (project_rel_path, original_path)."""
    raw = (source_path or "").strip().strip('"').strip("'")
    if not raw:
        raise BootstrapError("请填写参考视频本地路径。")
    src = Path(raw).expanduser()
    if not src.is_file():
        raise BootstrapError(f"找不到参考视频文件：{raw}")
    media_type = detect_media_type(src)
    if media_type != "video":
        raise BootstrapError("参考文件须为常见视频格式（如 .mp4、.mov、.webm）。")
    dest_dir = project_dir / "assets" / "video"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"reference{src.suffix.lower()}"
    shutil.copy2(src, dest)
    rel = dest.relative_to(project_dir).as_posix()
    return rel, str(src.resolve())


def create_project_workspace(
    *,
    project_id: str,
    title: str,
    pipeline_type: str,
    style_playbook: Optional[str] = None,
    notes: Optional[str] = None,
    inputs: Optional[dict[str, Any]] = None,
    projects_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Initialize an empty project workspace. Does not start pipeline execution."""
    pid = validate_project_id(project_id)
    clean_title = (title or "").strip()
    if not clean_title:
        raise BootstrapError("请填写项目标题。")
    if len(clean_title) > 120:
        raise BootstrapError("项目标题不能超过 120 个字符。")

    pipeline = (pipeline_type or "").strip()
    if not pipeline:
        raise BootstrapError("请选择流水线。")
    catalog = {e["id"] for e in list_pipeline_catalog(include_hidden=True)}
    if pipeline not in catalog:
        raise BootstrapError(f"未知流水线: {pipeline}")

    path = PIPELINE_DEFS_DIR / f"{pipeline}.yaml"
    if not path.is_file():
        raise BootstrapError(f"未知流水线: {pipeline}")

    production_inputs = validate_production_inputs(pipeline, inputs)

    base = projects_dir or PROJECTS_DIR
    target = base / pid
    if target.exists() and any(target.iterdir()):
        raise BootstrapError(f"项目「{pid}」已存在。请换一个 ID 或删除旧目录。")

    project_dir = init_project(
        pid,
        title=clean_title,
        pipeline_type=pipeline,
        pipeline_dir=base,
        style_playbook=(style_playbook or None),
    )

    if production_inputs.get("source_media_path"):
        rel, original = _ingest_source_media(project_dir, production_inputs["source_media_path"])
        production_inputs["source_media_path"] = rel
        production_inputs["source_media_original_path"] = original

    if production_inputs.get("reference_media_path"):
        rel, original = _ingest_reference_media(project_dir, production_inputs["reference_media_path"])
        production_inputs["reference_media_path"] = rel
        production_inputs["reference_media_original_path"] = original

    meta: dict[str, Any] = {
        "version": "1.0",
        "created_via": "backlot_library",
    }
    has_reference = pipeline == "reference-driven" or bool(
        str(production_inputs.get("reference_url") or "").strip()
        or str(production_inputs.get("reference_media_path") or "").strip()
    )
    if has_reference:
        meta["intake_mode"] = "reference"
        meta["required_meta_skills"] = ["meta/video-reference-analyst"]
    if notes and notes.strip():
        meta["bootstrap_notes"] = notes.strip()[:2000]
    if production_inputs:
        meta["production_inputs"] = production_inputs

    meta_path = project_dir / "meta.json"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    return {
        "project_id": pid,
        "title": clean_title,
        "pipeline_type": pipeline,
        "project_dir": str(project_dir),
        "production_inputs": production_inputs,
    }


def list_style_playbook_options() -> list[dict[str, str]]:
    """Style playbook ids from ``styles/*.yaml`` for library create/settings."""
    styles_dir = REPO_ROOT / "styles"
    options: list[dict[str, str]] = [{"value": "", "label_zh": "默认（不指定）", "hint_zh": "由 Agent 按流水线自行决定视觉风格"}]
    if not styles_dir.is_dir():
        return options
    for path in sorted(styles_dir.glob("*.yaml")):
        playbook_id = path.stem
        label = playbook_id.replace("-", " ").title()
        hint = ""
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                identity = data.get("identity") or {}
                if isinstance(identity, dict):
                    label = str(identity.get("name_zh") or identity.get("name") or label)
                    hint = str(
                        identity.get("summary_zh")
                        or identity.get("best_for")
                        or ""
                    ).strip()
        except (yaml.YAMLError, OSError):
            pass
        entry: dict[str, str] = {"value": playbook_id, "label_zh": label}
        if hint:
            entry["hint_zh"] = hint[:120]
        options.append(entry)
    return options


_STYLE_PLAYBOOK_LABELS: Optional[dict[str, str]] = None


def style_playbook_label_zh(playbook_id: Optional[str]) -> str:
    """Resolve a style playbook id to its Chinese display label."""
    if not playbook_id:
        return ""
    global _STYLE_PLAYBOOK_LABELS
    if _STYLE_PLAYBOOK_LABELS is None:
        _STYLE_PLAYBOOK_LABELS = {
            o["value"]: o["label_zh"]
            for o in list_style_playbook_options()
            if o.get("value")
        }
    return _STYLE_PLAYBOOK_LABELS.get(playbook_id, playbook_id)


_SETTINGS_LOCKED_PATH_KEYS = frozenset({"source_media_path", "reference_media_path"})


def _read_project_marker(project_dir: Path) -> tuple[dict[str, Any], bool]:
    """Return ``(marker, synthesized)`` — legacy dirs may lack project.json."""
    marker_path = project_dir / "project.json"
    if marker_path.is_file():
        try:
            marker = json.loads(marker_path.read_text(encoding="utf-8"))
            if isinstance(marker, dict):
                return marker, False
        except (json.JSONDecodeError, OSError):
            pass

    project_id = project_dir.name
    title = project_id.replace("-", " ").title()

    meta_path = project_dir / "meta.json"
    if meta_path.is_file():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if isinstance(meta, dict):
                title = str(meta.get("name") or meta.get("title") or title).strip() or title
        except (json.JSONDecodeError, OSError):
            pass

    script_path = project_dir / "artifacts" / "script.json"
    if script_path.is_file():
        try:
            script = json.loads(script_path.read_text(encoding="utf-8"))
            if isinstance(script, dict):
                script_title = str(script.get("title") or "").strip()
                if script_title:
                    title = script_title
        except (json.JSONDecodeError, OSError):
            pass

    pipeline_type = "unknown"
    for cp_path in sorted(project_dir.glob("checkpoint_*.json")):
        try:
            cp = json.loads(cp_path.read_text(encoding="utf-8"))
            if not isinstance(cp, dict):
                continue
            pt = str(cp.get("pipeline_type") or "").strip()
            if pt and pt != "unknown":
                pipeline_type = pt
                break
        except (json.JSONDecodeError, OSError):
            continue

    return {
        "project_id": project_id,
        "title": title,
        "pipeline_type": pipeline_type,
    }, True


def _has_pipeline_state(project_dir: Path) -> bool:
    return any(project_dir.glob("checkpoint_*.json"))


def _parse_field_value(raw: Any, field: dict[str, Any]) -> Any:
    ftype = field["type"]
    if ftype == "select":
        return _parse_select(raw, field)
    if ftype == "number":
        return _parse_number(raw, field)
    if ftype in ("path", "url"):
        return str(raw).strip().strip('"').strip("'")
    return _parse_text(raw, field)


def validate_production_inputs_partial(
    pipeline_type: str,
    inputs: dict[str, Any],
    *,
    existing: dict[str, Any],
    allow_media_replace: bool = False,
) -> dict[str, Any]:
    """Validate only keys present in *inputs* (settings update, not create)."""
    if not inputs:
        return {}
    fields = bootstrap_fields_for_pipeline(pipeline_type)
    field_by_key = {f["key"]: f for f in fields}
    normalized: dict[str, Any] = {}
    raw = dict(inputs)

    from lib.deliverable_spec import DELIVERABLE_KEYS, normalize_deliverable_field
    from lib.publish_intake import COVER_KEYS, normalize_cover_field

    for key, value in inputs.items():
        if key in DELIVERABLE_KEYS:
            if value is None or str(value).strip() == "":
                continue
            try:
                normalized[key] = normalize_deliverable_field(key, value)
            except ValueError as exc:
                if str(exc) != "empty":
                    raise BootstrapError(str(exc)) from exc
            continue
        if key in COVER_KEYS:
            if value is None or str(value).strip() == "":
                continue
            try:
                normalized[key] = normalize_cover_field(key, value)
            except ValueError as exc:
                if str(exc) != "empty":
                    raise BootstrapError(str(exc)) from exc
            continue
        field = field_by_key.get(key)
        if field is None:
            continue
        if value is None or str(value).strip() == "":
            continue
        if field.get("type") == "path" and key in _SETTINGS_LOCKED_PATH_KEYS and not allow_media_replace:
            raise BootstrapError(
                f"流水线已开始，无法更换{field['label_zh']}。"
                "如需更换请勾选「允许更换素材」或联系 Agent。"
            )
        normalized[key] = _parse_field_value(value, field)

    merged = dict(existing)
    merged.update(normalized)
    _apply_pipeline_rules(pipeline_type, merged, {**existing, **raw})
    return normalized


def load_project_settings(project_dir: Path) -> dict[str, Any]:
    """Read editable project settings for the library UI."""
    marker, _synthesized = _read_project_marker(project_dir)
    meta_path = project_dir / "meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    pipeline_type = str(marker.get("pipeline_type") or "unknown")
    has_state = _has_pipeline_state(project_dir)
    production_inputs = dict(meta.get("production_inputs") or {})

    bootstrap_fields: list[dict[str, Any]] = []
    for field in bootstrap_fields_for_pipeline(pipeline_type):
        f = dict(field)
        key = f["key"]
        if has_state and f.get("type") == "path" and key in _SETTINGS_LOCKED_PATH_KEYS:
            f["locked"] = True
            f["required"] = False
            current = production_inputs.get(key)
            if current:
                f["current_value"] = current
        else:
            f["locked"] = False
            if has_state:
                f["required"] = False
        bootstrap_fields.append(f)

    from backlot.state import source_media_summary
    from lib.deliverable_spec import resolve_deliverable
    from lib.publish_intake import resolve_cover_brief

    deliverable = resolve_deliverable(production_inputs)
    cover_brief = resolve_cover_brief(production_inputs)

    return {
        "project_id": marker.get("project_id") or project_dir.name,
        "title": marker.get("title") or project_dir.name,
        "pipeline_type": pipeline_type,
        "pipeline_label_zh": pipeline_label_zh(pipeline_type),
        "style_playbook": marker.get("style_playbook") or "",
        "style_playbook_options": list_style_playbook_options(),
        "bootstrap_notes": meta.get("bootstrap_notes") or "",
        "production_inputs": production_inputs,
        "deliverable": deliverable,
        "cover_brief": cover_brief,
        "has_pipeline_state": has_state,
        "bootstrap_fields": bootstrap_fields,
        "created_at": marker.get("created_at"),
        "source_media": source_media_summary(project_dir),
        "legacy_marker": _synthesized,
    }


def update_project_settings(
    *,
    project_id: str,
    title: Optional[str] = None,
    style_playbook: Optional[str] = None,
    notes: Optional[str] = None,
    inputs: Optional[dict[str, Any]] = None,
    replace_media: bool = False,
    projects_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Update project marker and meta production inputs."""
    pid = validate_project_id(project_id)
    base = projects_dir or PROJECTS_DIR
    project_dir = base / pid
    if not project_dir.is_dir():
        raise BootstrapError(f"找不到项目「{pid}」。")

    current = load_project_settings(project_dir)
    pipeline_type = current["pipeline_type"]
    has_state = current["has_pipeline_state"]

    marker_path = project_dir / "project.json"
    marker, synthesized = _read_project_marker(project_dir)

    if title is not None:
        clean_title = title.strip()
        if not clean_title:
            raise BootstrapError("请填写项目标题。")
        if len(clean_title) > 120:
            raise BootstrapError("项目标题不能超过 120 个字符。")
        marker["title"] = clean_title

    if style_playbook is not None:
        sp = style_playbook.strip()
        if sp:
            allowed = {o["value"] for o in list_style_playbook_options() if o["value"]}
            if sp not in allowed:
                raise BootstrapError("无效的风格 playbook。")
            marker["style_playbook"] = sp
        else:
            marker.pop("style_playbook", None)

    if synthesized:
        marker.setdefault("version", "1.0")
        marker.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        marker.setdefault("project_id", pid)

    marker_path.write_text(json.dumps(marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    meta_path = project_dir / "meta.json"
    meta: dict[str, Any] = {}
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("version", "1.0")

    if notes is not None:
        note_text = notes.strip()
        if note_text:
            meta["bootstrap_notes"] = note_text[:2000]
        else:
            meta.pop("bootstrap_notes", None)

    existing_inputs = dict(meta.get("production_inputs") or {})
    if inputs:
        normalized = validate_production_inputs_partial(
            pipeline_type,
            inputs,
            existing=existing_inputs,
            allow_media_replace=replace_media or not has_state,
        )
        for key, val in normalized.items():
            field = next((f for f in bootstrap_fields_for_pipeline(pipeline_type) if f["key"] == key), None)
            if field and field.get("type") == "path":
                if key == "source_media_path":
                    rel, original = _ingest_source_media(project_dir, str(val))
                    existing_inputs["source_media_path"] = rel
                    existing_inputs["source_media_original_path"] = original
                elif key == "reference_media_path":
                    rel, original = _ingest_reference_media(project_dir, str(val))
                    existing_inputs["reference_media_path"] = rel
                    existing_inputs["reference_media_original_path"] = original
            else:
                existing_inputs[key] = val

        if normalized.get("reference_url") or normalized.get("reference_media_path"):
            meta["intake_mode"] = "reference"
            meta["required_meta_skills"] = ["meta/video-reference-analyst"]

        meta["production_inputs"] = existing_inputs

    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return load_project_settings(project_dir)


def delete_project_workspace(
    *,
    project_id: str,
    projects_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Remove a project workspace directory from disk."""
    pid = validate_project_id(project_id)
    base = projects_dir or PROJECTS_DIR
    target = (base / pid).resolve()
    try:
        target.relative_to(base.resolve())
    except ValueError:
        raise BootstrapError("无效的项目 ID。") from None
    if not target.is_dir():
        raise BootstrapError(f"找不到项目「{pid}」。")
    shutil.rmtree(target)
    return {"project_id": pid, "deleted": True}
