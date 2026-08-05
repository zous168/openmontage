"""Environment variable catalog and .env persistence for Backlot."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

from dotenv import load_dotenv

from backlot.bootstrap import BootstrapError
from lib.env_loader import load_env
from lib.paths import REPO_ROOT
from tools.tool_registry import registry

ENV_PATH = REPO_ROOT / ".env"
ENV_EXAMPLE_PATH = REPO_ROOT / ".env.example"

_SECTION_RE = re.compile(r"^#\s*---\s*(.+?)\s*---\s*$")
_KEY_RE = re.compile(r"^([A-Z][A-Z0-9_]*)=(.*)$")
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")

# 按用途分组的中文目录（UI 展示）；写入 .env 仍沿用 .env.example 的顺序。
ENV_PURPOSE_GROUPS: list[dict[str, Any]] = [
    {
        "id": "gateway",
        "label": "聚合网关",
        "description": "通过 fal.ai 等网关调用 FLUX 图像、Veo / Kling / MiniMax 视频与 Recraft 图像。",
        "vars": {
            "FAL_KEY": {
                "purpose": "fal.ai 主 API 密钥",
                "hint": "解锁 FLUX 图像、Google Veo、Kling、MiniMax 视频及 Recraft 等能力。",
            },
            "FAL_AI_API_KEY": {
                "purpose": "fal.ai 密钥别名",
                "hint": "与 FAL_KEY 等价，部分 SDK 使用此名称；二者配置其一即可。",
            },
        },
    },
    {
        "id": "replicate",
        "label": "Replicate 托管",
        "description": "在 Replicate 平台托管运行的视频模型（如 Seedance）。",
        "vars": {
            "REPLICATE_API_TOKEN": {
                "purpose": "Replicate 平台 API 令牌",
                "hint": "启用 Seedance 等 Replicate 托管视频路径，可与 fal.ai 并行使用。",
            },
        },
    },
    {
        "id": "higgsfield",
        "label": "Higgsfield 云端",
        "description": "Higgsfield 云端视频生成服务。",
        "vars": {
            "HIGGSFIELD_API_KEY": {
                "purpose": "Higgsfield 接口密钥",
                "hint": "与 HIGGSFIELD_API_SECRET 配对使用，用于 higgsfield_video 工具。",
            },
            "HIGGSFIELD_API_SECRET": {
                "purpose": "Higgsfield 接口私钥",
                "hint": "也可改用合并变量 HIGGSFIELD_KEY（格式：密钥:私钥）。",
            },
            "HIGGSFIELD_KEY": {
                "purpose": "Higgsfield 合并密钥",
                "hint": "格式为「密钥:私钥」；设置后无需再分别填写 KEY 与 SECRET。",
            },
        },
    },
    {
        "id": "kling",
        "label": "Kling 官方 API",
        "description": "可灵官方直连：视频、图像、TTS、数字人、口型同步。",
        "vars": {
            "KLING_API_KEY": {
                "purpose": "可灵官方 API 密钥",
                "hint": "启用 kling_official_video、kling_avatar、kling_tts 等工具。",
            },
            "KLING_API_BASE_URL": {
                "purpose": "可灵 API 端点（可选）",
                "hint": "留空默认新加坡节点；国内账号可用 https://api-beijing.klingai.com",
                "path_kind": "url",
            },
        },
    },
    {
        "id": "google",
        "label": "Google 云能力",
        "description": "同一套 Google 凭据可覆盖 Imagen 图像、Cloud TTS、Gemini Omni 视频等。",
        "vars": {
            "GOOGLE_API_KEY": {
                "purpose": "Google AI Studio API 密钥",
                "hint": "图像生成、700+ 语音 TTS、Gemini Omni 视频（付费档）。",
            },
            "GEMINI_API_KEY": {
                "purpose": "Gemini 密钥别名",
                "hint": "与 GOOGLE_API_KEY 等价；同时存在时优先使用此项。",
            },
            "GOOGLE_APPLICATION_CREDENTIALS": {
                "purpose": "GCP 服务账号 JSON 路径",
                "hint": "用于 Vertex AI Imagen 或服务账号鉴权；填本地文件绝对路径。",
                "path_kind": "file",
            },
            "GOOGLE_CLOUD_PROJECT": {
                "purpose": "GCP 项目 ID",
                "hint": "通过 Vertex AI 调用 Imagen 时必填。",
            },
            "GOOGLE_CLOUD_LOCATION": {
                "purpose": "Vertex AI 区域",
                "hint": "默认 us-central1，可按就近区域调整。",
            },
        },
    },
    {
        "id": "voice",
        "label": "语音与配音",
        "description": "旁白 TTS、克隆音色与 Grok 等多供应商语音能力。",
        "vars": {
            "ELEVENLABS_API_KEY": {
                "purpose": "ElevenLabs 密钥",
                "hint": "旁白 TTS、音乐生成、音效生成。",
            },
            "OPENAI_API_KEY": {
                "purpose": "OpenAI 密钥",
                "hint": "OpenAI TTS 备选与 GPT Image 图像生成。",
            },
            "XAI_API_KEY": {
                "purpose": "xAI Grok 密钥",
                "hint": "Grok 图像编辑与 Grok 视频生成。",
            },
            "DOUBAO_SPEECH_API_KEY": {
                "purpose": "火山豆包语音 API Key",
                "hint": "新版控制台 API Key，用于豆包 TTS。",
            },
            "DOUBAO_SPEECH_VOICE_TYPE": {
                "purpose": "豆包默认音色",
                "hint": "例如 zh_female_vv_uranus_bigtts；不填则使用工具默认音色。",
            },
        },
    },
    {
        "id": "dashscope",
        "label": "阿里云百炼",
        "description": "通义千问图像、TTS 与带词级时间戳的 ASR。",
        "vars": {
            "DASHSCOPE_API_KEY": {
                "purpose": "DashScope API 密钥",
                "hint": "Qwen 图像、qwen3-tts-flash、qwen3-asr 等。",
            },
        },
    },
    {
        "id": "music",
        "label": "AI 音乐",
        "description": "完整歌曲、纯伴奏与多风格音乐生成。",
        "vars": {
            "SUNO_API_KEY": {
                "purpose": "Suno API 密钥",
                "hint": "Suno 全曲/伴奏生成。",
            },
        },
    },
    {
        "id": "video_gen",
        "label": "视频生成",
        "description": "各云厂商与本地 GPU 视频模型开关。",
        "vars": {
            "HEYGEN_API_KEY": {
                "purpose": "HeyGen API 密钥",
                "hint": "经 HeyGen 路由 Veo、Sora、Runway、Kling、Seedance 等。",
            },
            "RUNWAY_API_KEY": {
                "purpose": "Runway 直连密钥",
                "hint": "Runway Gen-4 官方 API，可作为 fal.ai 的替代路径。",
            },
            "VOLC_ACCESSKEY": {
                "purpose": "火山引擎 Access Key",
                "hint": "即梦 AI 官方视频 API（与 VOLC_SECRETKEY 配对）。",
            },
            "VOLC_SECRETKEY": {
                "purpose": "火山引擎 Secret Key",
                "hint": "在火山 IAM 密钥管理页与 Access Key 一并获取。",
            },
            "VIDEO_GEN_LOCAL_ENABLED": {
                "purpose": "启用本地视频生成",
                "hint": "设为 true 时开启 Hunyuan / LTX / CogVideo 等本地 diffusers 路径（需 GPU）。",
            },
            "VIDEO_GEN_LOCAL_MODEL": {
                "purpose": "本地视频模型 ID",
                "hint": "如 hunyuan-1.5、ltx2-local、cogvideo-5b。",
            },
            "MODAL_LTX2_ENDPOINT_URL": {
                "purpose": "Modal 自托管 LTX-2 端点",
                "hint": "部署在 Modal 上的 LTX-2 HTTP 地址（可选）。",
                "path_kind": "url",
            },
        },
    },
    {
        "id": "stock",
        "label": "素材库",
        "description": "免费/低成本图库与视频库检索。",
        "vars": {
            "PEXELS_API_KEY": {
                "purpose": "Pexels API 密钥",
                "hint": "Pexels 免费图库与视频库。",
            },
            "PIXABAY_API_KEY": {
                "purpose": "Pixabay API 密钥",
                "hint": "Pixabay 免费图库与视频库。",
            },
            "UNSPLASH_ACCESS_KEY": {
                "purpose": "Unsplash 图库访问密钥",
                "hint": "Unsplash 免费图片检索（开发者密钥）。",
            },
        },
    },
    {
        "id": "analysis",
        "label": "分析与转写",
        "description": "语音识别、说话人分离与云端 STT 备选。",
        "vars": {
            "HF_TOKEN": {
                "purpose": "HuggingFace 令牌",
                "hint": "启用 transcriber 说话人分离（diarization）。",
            },
            "AZURE_SPEECH_KEY": {
                "purpose": "Azure 语音服务密钥",
                "hint": "云端 STT（azure_stt）；本地 faster-whisper 仍为默认离线路径。",
            },
            "AZURE_SPEECH_REGION": {
                "purpose": "Azure 语音资源区域",
                "hint": "例如 eastus，与 Speech 资源所在区域一致。",
            },
            "AZURE_SPEECH_ENDPOINT": {
                "purpose": "Azure 自定义端点（可选）",
                "hint": "完整 HTTPS 端点 URL；设置后覆盖区域拼接方式。",
                "path_kind": "url",
            },
        },
    },
    {
        "id": "avatar_local",
        "label": "本地数字人",
        "description": "克隆到本地的 Wav2Lip / SadTalker 仓库路径。",
        "vars": {
            "WAV2LIP_PATH": {
                "purpose": "Wav2Lip 仓库路径",
                "hint": "lip_sync 工具的本地安装目录。",
                "path_kind": "file",
            },
            "SADTALKER_PATH": {
                "purpose": "SadTalker 仓库路径",
                "hint": "talking_head 工具的本地安装目录。",
                "path_kind": "file",
            },
        },
    },
]

_VAR_META: dict[str, dict[str, Any]] = {}
_GROUP_ORDER: dict[str, int] = {}
for _idx, _group in enumerate(ENV_PURPOSE_GROUPS):
    _GROUP_ORDER[_group["id"]] = _idx
    for _name, _meta in (_group.get("vars") or {}).items():
        _VAR_META[_name] = {**_meta, "group_id": _group["id"]}


def _env_path(path: Optional[Path] = None) -> Path:
    return path or ENV_PATH


def _example_path(path: Optional[Path] = None) -> Path:
    return path or ENV_EXAMPLE_PATH


def _mask_secret(value: str) -> str:
    v = value.strip()
    if not v:
        return ""
    if len(v) <= 6:
        return "••••••"
    return f"{v[:3]}••••{v[-2:]}"


def _parse_env_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, raw = stripped.partition("=")
        key = key.strip()
        if not _ENV_NAME_RE.match(key):
            continue
        val = raw.split("#", 1)[0].strip().strip('"').strip("'")
        if val:
            values[key] = val
    return values


def _read_env_file(env_path: Optional[Path] = None) -> dict[str, str]:
    path = _env_path(env_path)
    if not path.is_file():
        return {}
    try:
        return _parse_env_values(path.read_text(encoding="utf-8"))
    except OSError:
        return {}


def _tool_env_refs() -> dict[str, list[str]]:
    registry.ensure_discovered()
    refs: dict[str, list[str]] = {}
    for tool in registry._tools.values():
        if tool.provider == "selector":
            continue
        for dep in tool.dependencies:
            if isinstance(dep, str) and dep.startswith("env:"):
                refs.setdefault(dep[4:], []).append(tool.name)
    for name in sorted(refs):
        refs[name] = sorted(set(refs[name]))
    return refs


def parse_env_example(example_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """Parse ``.env.example`` — used for persistence order and fallback keys."""
    path = _example_path(example_path)
    if not path.is_file():
        return []

    sections: list[dict[str, Any]] = []
    current: dict[str, Any] = {"id": "general", "label": "通用", "items": []}
    pending_comment: list[str] = []

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            pending_comment = []
            continue

        section_match = _SECTION_RE.match(stripped)
        if section_match:
            if current["items"]:
                sections.append(current)
            label = section_match.group(1).strip()
            slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "general"
            current = {"id": slug, "label": label, "items": []}
            pending_comment = []
            continue

        if stripped.startswith("#"):
            pending_comment.append(stripped.lstrip("#").strip())
            continue

        key_match = _KEY_RE.match(stripped)
        if not key_match:
            continue

        key = key_match.group(1)
        inline = key_match.group(2).split("#", 1)
        inline_comment = inline[1].strip() if len(inline) > 1 and inline[1].strip() else ""
        description_parts = [*pending_comment]
        if inline_comment:
            description_parts.append(inline_comment)
        current["items"].append({
            "name": key,
            "description": " ".join(description_parts).strip(),
        })
        pending_comment = []

    if current["items"]:
        sections.append(current)
    return sections


def _all_catalog_var_names(example_path: Optional[Path] = None) -> set[str]:
    names = set(_VAR_META)
    names.update(_tool_env_refs())
    for section in parse_env_example(example_path):
        for item in section.get("items") or []:
            names.add(item["name"])
    return names


def _allowed_env_keys(example_path: Optional[Path] = None) -> set[str]:
    return _all_catalog_var_names(example_path)


def _path_label(name: str, meta: dict[str, Any]) -> str:
    kind = meta.get("path_kind")
    if kind == "file":
        return f"文件路径 · {name}"
    if kind == "url":
        return f"URL / 端点 · {name}"
    return f"${name}"


def _enrich_item(
    name: str,
    *,
    file_values: dict[str, str],
    tool_refs: dict[str, list[str]],
) -> dict[str, Any]:
    meta = dict(_VAR_META.get(name) or {})
    file_val = file_values.get(name, "")
    proc_val = os.environ.get(name, "")
    configured = bool(file_val or proc_val)
    display_val = file_val or proc_val
    tools = tool_refs.get(name, [])

    purpose = meta.get("purpose") or "环境配置项"
    hint = meta.get("hint") or "请在项目文档或 .env.example 中查看详细说明。"
    if tools:
        tool_text = "、".join(tools[:4])
        if len(tools) > 4:
            tool_text += " 等"
        hint = f"{hint}关联工具：{tool_text}。" if hint else f"关联工具：{tool_text}。"

    source = "none"
    if file_val and proc_val:
        source = "both"
    elif file_val:
        source = "file"
    elif proc_val:
        source = "process"

    group_id = meta.get("group_id") or "other"

    return {
        "name": name,
        "purpose": purpose,
        "hint": hint.strip(),
        "tools": tools,
        "configured": configured,
        "masked_value": _mask_secret(display_val) if configured else "",
        "source": source,
        "path": _path_label(name, meta),
        "group_id": group_id,
    }


def _build_purpose_sections(
    *,
    file_values: dict[str, str],
    tool_refs: dict[str, list[str]],
    example_path: Optional[Path] = None,
) -> tuple[list[dict[str, Any]], int, int]:
    """Group catalog items by Chinese purpose sections."""
    all_names = sorted(_all_catalog_var_names(example_path))
    buckets: dict[str, list[dict[str, Any]]] = {g["id"]: [] for g in ENV_PURPOSE_GROUPS}
    buckets.setdefault("other", [])
    buckets.setdefault("tool_registry", [])

    configured_count = 0
    total_count = 0

    for name in all_names:
        enriched = _enrich_item(
            name,
            file_values=file_values,
            tool_refs=tool_refs,
        )
        total_count += 1
        if enriched["configured"]:
            configured_count += 1

        gid = enriched["group_id"]
        if gid in buckets:
            buckets[gid].append(enriched)
        elif name in _VAR_META:
            buckets[gid].append(enriched)
        elif tool_refs.get(name) and name not in _VAR_META:
            enriched["purpose"] = enriched["purpose"] or "工具声明的环境变量"
            enriched["group_id"] = "tool_registry"
            buckets["tool_registry"].append(enriched)
        else:
            enriched["group_id"] = "other"
            enriched["purpose"] = enriched["purpose"] or "其他配置"
            buckets["other"].append(enriched)

    sections: list[dict[str, Any]] = []
    for group in ENV_PURPOSE_GROUPS:
        items = buckets.get(group["id"]) or []
        if not items:
            continue
        sections.append({
            "id": group["id"],
            "label": group["label"],
            "description": group.get("description") or "",
            "items": sorted(items, key=lambda i: i["name"]),
        })

    if buckets.get("tool_registry"):
        sections.append({
            "id": "tool_registry",
            "label": "工具注册表",
            "description": "仅在工具 dependencies 中声明、尚未收录到上方用途分组的环境变量。",
            "items": sorted(buckets["tool_registry"], key=lambda i: i["name"]),
        })

    if buckets.get("other"):
        sections.append({
            "id": "other",
            "label": "其他",
            "description": "来自 .env.example 的其余配置项。",
            "items": sorted(buckets["other"], key=lambda i: i["name"]),
        })

    return sections, configured_count, total_count


def build_env_catalog(
    *,
    env_path: Optional[Path] = None,
    example_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Return env-var catalog grouped by Chinese purpose labels."""
    load_env(REPO_ROOT)
    file_values = _read_env_file(env_path)
    tool_refs = _tool_env_refs()
    sections, configured_count, total_count = _build_purpose_sections(
        file_values=file_values,
        tool_refs=tool_refs,
        example_path=example_path,
    )

    return {
        "env_path": str(_env_path(env_path).resolve()),
        "example_path": str(_example_path(example_path).resolve()),
        "configured_count": configured_count,
        "total_count": total_count,
        "sections": sections,
    }


def _write_env_file(
    updates: dict[str, str],
    *,
    env_path: Optional[Path] = None,
    example_path: Optional[Path] = None,
) -> None:
    path = _env_path(env_path)
    existing = _read_env_file(path)
    for key, value in updates.items():
        if value.strip():
            existing[key] = value.strip()
        else:
            existing.pop(key, None)

    lines: list[str] = [
        "# OpenMontage environment",
        "# 由 Backlot → 全局设置 → 环境变量 管理",
        "",
    ]
    written: set[str] = set()

    for section in parse_env_example(example_path):
        lines.append(f"# --- {section['label']} ---")
        for item in section.get("items") or []:
            key = item["name"]
            written.add(key)
            lines.append(f"{key}={existing[key]}" if key in existing else f"{key}=")
        lines.append("")

    for key in sorted(set(existing) - written):
        lines.append(f"{key}={existing[key]}")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def update_env_vars(
    values: dict[str, str],
    *,
    env_path: Optional[Path] = None,
    example_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Persist env-var updates to ``.env`` and reload the process environment."""
    if not values:
        raise BootstrapError("未提供任何环境变量。")

    allowed = _allowed_env_keys(example_path)
    cleaned: dict[str, str] = {}
    for key, value in values.items():
        name = str(key).strip()
        if not _ENV_NAME_RE.match(name):
            raise BootstrapError(f"无效的环境变量名：{name!r}")
        if name not in allowed:
            raise BootstrapError(f"不支持的环境变量：{name}")
        cleaned[name] = str(value)

    _write_env_file(cleaned, env_path=env_path, example_path=example_path)
    load_dotenv(_env_path(env_path), override=True)
    return build_env_catalog(env_path=env_path, example_path=example_path)
