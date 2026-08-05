"""Chinese labels and descriptions for external dependency packages."""

from __future__ import annotations

from typing import Any, Optional

from plugins.openmontage.backlot.env_config import ENV_PURPOSE_GROUPS

# kind:name -> metadata shown in the Environment Dependencies UI
DEPENDENCY_CATALOG: dict[str, dict[str, str]] = {
    "cmd:ffmpeg": {
        "label_zh": "FFmpeg",
        "description_zh": "音视频转码、剪辑、合成、抽帧与滤镜处理的核心命令行工具",
        "install_hint_zh": "安装 FFmpeg 并加入系统 PATH（Windows 可用 winget install ffmpeg）",
    },
    "cmd:ffprobe": {
        "label_zh": "FFprobe",
        "description_zh": "读取音视频元数据、时长、编码与流信息（FFmpeg 套件组件）",
        "install_hint_zh": "随 FFmpeg 一并安装；确保 ffprobe 在 PATH 中可用",
    },
    "cmd:manim": {
        "label_zh": "Manim",
        "description_zh": "ManimCE 数学/科普动画引擎，将 Python 场景代码渲染为动画视频",
        "install_hint_zh": "pip install manim，然后运行 manim checkhealth；需 FFmpeg，公式渲染可选 LaTeX",
    },
    "cmd:mmdc": {
        "label_zh": "Mermaid CLI",
        "description_zh": "Mermaid 图表命令行渲染器（@mermaid-js/mermaid-cli）",
        "install_hint_zh": "npm install -g @mermaid-js/mermaid-cli",
    },
    "cmd:npx": {
        "label_zh": "npx",
        "description_zh": "Node.js 包执行器，用于运行 HyperFrames 等前端合成 CLI",
        "install_hint_zh": "安装 Node.js（自带 npm/npx）并加入 PATH",
    },
    "cmd:piper": {
        "label_zh": "Piper CLI",
        "description_zh": "Piper 命令行（可选，用于下载语音模型）",
        "install_hint_zh": "可选：从 Piper 发布页下载 CLI；合成必需 pip install piper-tts",
    },
    "python:piper": {
        "label_zh": "piper-tts",
        "description_zh": "Piper Python 包，本地神经语音合成（from piper import PiperVoice）",
        "install_hint_zh": "pip install piper-tts",
    },
    "python:PIL": {
        "label_zh": "Pillow",
        "description_zh": "Python 图像读写与处理库（import 名为 PIL）",
        "install_hint_zh": "pip install pillow",
    },
    "python:cv2": {
        "label_zh": "OpenCV",
        "description_zh": "OpenCV 计算机视觉库，用于素材索引与画面分析（import 名为 cv2）",
        "install_hint_zh": "pip install opencv-python",
    },
    "python:diffusers": {
        "label_zh": "Diffusers",
        "description_zh": "HuggingFace 本地 Stable Diffusion 推理库",
        "install_hint_zh": "pip install diffusers transformers accelerate torch",
    },
    "python:faster_whisper": {
        "label_zh": "faster-whisper",
        "description_zh": "本地 Whisper 语音识别，离线转写与字幕时间轴",
        "install_hint_zh": "pip install faster-whisper",
    },
    "python:gfpgan": {
        "label_zh": "GFPGAN",
        "description_zh": "人脸修复与清晰度增强模型",
        "install_hint_zh": "pip install gfpgan（通常需配合 PyTorch）",
    },
    "python:manim": {
        "label_zh": "ManimCE",
        "description_zh": "Manim 社区版 Python 包（数学/科普动画）",
        "install_hint_zh": "pip install manim；可用 manim 或 python -m manim 调用",
    },
    "python:numpy": {
        "label_zh": "NumPy",
        "description_zh": "数值计算基础库，用于向量检索与图像矩阵运算",
        "install_hint_zh": "pip install numpy",
    },
    "python:pygments": {
        "label_zh": "Pygments",
        "description_zh": "代码语法高亮，用于生成代码片段配图",
        "install_hint_zh": "pip install pygments",
    },
    "python:realesrgan": {
        "label_zh": "Real-ESRGAN",
        "description_zh": "AI 超分辨率放大，提升画面清晰度",
        "install_hint_zh": "pip install realesrgan（需 GPU 与 PyTorch）",
    },
    "python:rembg": {
        "label_zh": "rembg",
        "description_zh": "AI 背景移除（抠图）",
        "install_hint_zh": "pip install rembg",
    },
    "python:requests": {
        "label_zh": "requests",
        "description_zh": "HTTP 客户端，用于检索与下载在线素材",
        "install_hint_zh": "pip install requests",
    },
    "python:torch": {
        "label_zh": "PyTorch",
        "description_zh": "深度学习运行时，驱动本地 AI 模型（口型、检索、超分等）",
        "install_hint_zh": "按官网指引安装与 CUDA 匹配的 torch 版本",
    },
    "python:transformers": {
        "label_zh": "Transformers",
        "description_zh": "HuggingFace 模型库，用于 CLIP 语义检索与视频理解",
        "install_hint_zh": "pip install transformers",
    },
    "python:youtube_transcript_api": {
        "label_zh": "youtube-transcript-api",
        "description_zh": "抓取 YouTube 视频自带字幕/transcript",
        "install_hint_zh": "pip install youtube-transcript-api",
    },
    "python:yt_dlp": {
        "label_zh": "yt-dlp",
        "description_zh": "下载 YouTube 等平台的视频与音频",
        "install_hint_zh": "pip install yt-dlp",
    },
}

TOOL_LABELS_ZH: dict[str, str] = {
    "action_timeline_compiler": "动作时间轴编译",
    "audio_energy": "音频能量分析",
    "audio_enhance": "音频增强",
    "audio_mixer": "音频混音",
    "audio_probe": "音频探测",
    "auto_reframe": "智能裁切重构",
    "azure_stt": "Azure 语音转写",
    "bg_remove": "背景移除",
    "cap_recorder": "Cap 屏幕录制",
    "character_animation_reviewer": "角色动画审阅",
    "character_rig_renderer": "角色骨骼渲染",
    "character_spec_generator": "角色规格生成",
    "clip_search": "CLIP 片段检索",
    "cogvideo_video": "CogVideo 视频生成",
    "code_snippet": "代码片段配图",
    "color_grade": "调色",
    "comfyui_image": "ComfyUI 图像生成",
    "comfyui_video": "ComfyUI 视频生成",
    "composition_validator": "合成校验",
    "corpus_builder": "素材语料库构建",
    "dashscope_asr": "通义语音识别",
    "dashscope_image": "通义图像生成",
    "dashscope_tts": "通义语音合成",
    "diagram_gen": "图表生成",
    "direct_clip_search": "多源素材直搜",
    "doubao_tts": "豆包语音合成",
    "elevenlabs_tts": "ElevenLabs 语音合成",
    "export_bundle": "导出打包",
    "eye_enhance": "眼部增强",
    "face_enhance": "人脸增强",
    "face_restore": "人脸修复",
    "face_tracker": "人脸跟踪",
    "flux_image": "FLUX 图像生成",
    "frame_sampler": "视频抽帧",
    "freesound_music": "Freesound 音乐素材",
    "gemini_omni_video": "Gemini 全能视频",
    "google_imagen": "Google Imagen 图像",
    "google_music": "Google 音乐生成",
    "google_tts": "Google 语音合成",
    "green_screen_composite": "绿幕合成",
    "green_screen_processor": "绿幕处理",
    "grok_image": "Grok 图像生成",
    "grok_video": "Grok 视频生成",
    "heygen_video": "HeyGen 数字人视频",
    "higgsfield_video": "Higgsfield 视频生成",
    "hunyuan_video": "混元视频生成",
    "hyperframes_compose": "HyperFrames 合成",
    "image_gen": "图像生成",
    "image_selector": "图像选择器",
    "jimeng_video": "即梦视频",
    "kling_avatar": "可灵数字人",
    "kling_lip_sync": "可灵口型同步",
    "kling_official_image": "可灵官方图像",
    "kling_official_video": "可灵官方视频",
    "kling_tts": "可灵 TTS",
    "kling_video": "可灵视频生成",
    "lip_sync": "本地口型同步",
    "local_diffusion": "本地扩散模型",
    "ltx_video_local": "LTX 本地视频",
    "ltx_video_modal": "LTX Modal 视频",
    "math_animate": "数学动画",
    "minimax_video": "MiniMax 视频生成",
    "music_gen": "音乐生成",
    "music_library": "音乐素材库",
    "openai_image": "OpenAI 图像生成",
    "openai_tts": "OpenAI 语音合成",
    "pexels_image": "Pexels 图像素材",
    "pexels_video": "Pexels 视频素材",
    "piper_tts": "Piper 本地 TTS",
    "pixabay_image": "Pixabay 图像素材",
    "pixabay_music": "Pixabay 音乐素材",
    "pixabay_video": "Pixabay 视频素材",
    "pose_library_builder": "姿势库构建",
    "recraft_image": "Recraft 图像生成",
    "remotion_caption_burn": "Remotion 字幕烧录",
    "runway_video": "Runway 视频生成",
    "scene_detect": "场景切点检测",
    "screen_capture_selector": "屏幕采集方式选择",
    "screen_recorder": "屏幕录制",
    "seedance_replicate": "Seedance Replicate 视频",
    "seedance_video": "Seedance 视频生成",
    "showcase_card": "展示卡片生成",
    "silence_cutter": "静音裁剪",
    "sora_video": "Sora 视频生成",
    "subtitle_gen": "字幕生成",
    "suno_music": "Suno 音乐生成",
    "svg_rig_builder": "SVG 骨骼构建",
    "talking_head": "数字人口播",
    "transcriber": "本地语音转写",
    "transcript_fetcher": "YouTube 字幕抓取",
    "tts_selector": "TTS 选择器",
    "upscale": "AI 超分辨率",
    "veo_video": "Veo 视频生成",
    "video_analyzer": "视频分析",
    "video_compose": "视频合成",
    "video_downloader": "视频下载",
    "video_selector": "视频选择器",
    "video_stitch": "视频拼接",
    "video_trimmer": "视频裁剪",
    "video_understand": "视频内容理解",
    "visual_qa": "画面质量检测",
}

TOOL_INSTALL_HINTS_ZH: dict[str, str] = {
    "kling_avatar": (
        "在「环境变量」标签配置 KLING_API_KEY（可灵官方 API 密钥）。"
        "需提供人像图片，以及 audio_id 或 sound_file / audio_path 之一作为驱动音频。"
    ),
    "kling_lip_sync": (
        "在「环境变量」标签配置 KLING_API_KEY。"
        "多人视频请先调用 identify_face，再传入 face_choose 或 face_id 指定口型对象。"
    ),
    "kling_official_image": (
        "在「环境变量」标签配置 KLING_API_KEY。"
        "可选配置 KLING_API_BASE_URL 覆盖默认新加坡节点（国内账号可用北京节点）。"
    ),
    "kling_official_video": (
        "在「环境变量」标签配置 KLING_API_KEY。"
        "可选配置 KLING_API_BASE_URL 覆盖默认可灵 API 端点。"
    ),
    "kling_tts": "在「环境变量」标签配置 KLING_API_KEY，启用可灵官方 TTS。",
    "jimeng_video": (
        "在「环境变量」标签配置 VOLC_ACCESSKEY 与 VOLC_SECRETKEY（火山引擎即梦 API）。"
    ),
}

CORE_BINARY_LABELS_ZH: dict[str, dict[str, str]] = {
    "ffmpeg": {
        "label_zh": "FFmpeg",
        "description_zh": "OpenMontage 核心音视频处理引擎",
    },
    "ffprobe": {
        "label_zh": "FFprobe",
        "description_zh": "读取媒体文件元数据",
    },
    "node": {
        "label_zh": "Node.js",
        "description_zh": "Remotion / HyperFrames 等 JS 合成运行时",
    },
    "npm": {
        "label_zh": "npm",
        "description_zh": "Node.js 包管理器，安装合成项目依赖",
    },
    "python": {
        "label_zh": "Python",
        "description_zh": "OpenMontage 主运行时",
    },
}

COMPOSITION_RUNTIME_LABELS_ZH: dict[str, str] = {
    "ffmpeg": "FFmpeg 直出合成",
    "remotion": "Remotion 合成",
    "hyperframes": "HyperFrames 合成",
}

_ENV_VAR_META: dict[str, dict[str, Any]] = {}
for _group in ENV_PURPOSE_GROUPS:
    for _name, _meta in (_group.get("vars") or {}).items():
        _ENV_VAR_META[_name] = {**_meta, "group_label": _group.get("label") or ""}


def _catalog_key(kind: str, name: str) -> str:
    if kind in ("binary", "cmd"):
        return f"cmd:{name}"
    if kind == "python" and name == "PIL":
        return "python:PIL"
    return f"{kind}:{name}"


def lookup_dependency(kind: str, name: str) -> dict[str, str]:
    """Return Chinese metadata for a dependency; falls back to generic text."""
    key = _catalog_key(kind, name)
    entry = DEPENDENCY_CATALOG.get(key, {})
    norm_kind = "cmd" if kind in ("binary", "cmd") else kind

    if norm_kind == "env":
        env_meta = _ENV_VAR_META.get(name, {})
        purpose = env_meta.get("purpose") or f"环境变量 {name}"
        hint = env_meta.get("hint") or ""
        group = env_meta.get("group_label") or ""
        description = purpose
        if hint:
            description = f"{purpose}。{hint}"
        if group:
            description = f"「{group}」{description}"
        return {
            "label_zh": name,
            "description_zh": description,
            "install_hint_zh": f"在「环境变量」标签配置 {name}",
        }

    label = entry.get("label_zh") or name
    description = entry.get("description_zh") or _generic_description(norm_kind, name)
    install_hint = entry.get("install_hint_zh") or _generic_install_hint(norm_kind, name)
    return {
        "label_zh": label,
        "description_zh": description,
        "install_hint_zh": install_hint,
    }


def _generic_description(kind: str, name: str) -> str:
    if kind == "cmd":
        return f"系统命令 {name}"
    if kind == "python":
        return f"Python 包 {name}"
    if kind == "env":
        return f"环境变量 {name}"
    return name


def _generic_install_hint(kind: str, name: str) -> str:
    if kind == "python":
        pkg = "pillow" if name == "PIL" else name.replace("_", "-")
        return f"pip install {pkg}"
    if kind == "env":
        return f"在「环境变量」标签设置 {name}"
    return f"安装 {name} 并加入 PATH"


def tool_label_zh(tool_name: str) -> str:
    return TOOL_LABELS_ZH.get(tool_name, _humanize_tool_name(tool_name))


def tool_install_hint_zh(tool_name: str, install_instructions: str = "", env_vars: Optional[list[str]] = None) -> str:
    """Chinese setup guidance for the tool checklist / setup offers UI."""
    if tool_name in TOOL_INSTALL_HINTS_ZH:
        return TOOL_INSTALL_HINTS_ZH[tool_name]
    if env_vars:
        parts: list[str] = []
        for name in env_vars:
            meta = lookup_dependency("env", name)
            short = meta["description_zh"].split("。")[0]
            parts.append(f"{name}（{short}）")
        return f"在「环境变量」标签配置：{'、'.join(parts)}。"
    lowered = (install_instructions or "").lower()
    if "kling_api_key" in lowered:
        return "在「环境变量」标签配置 KLING_API_KEY（可灵官方 API 密钥）。"
    if "fal_key" in lowered or "fal.ai" in lowered:
        return "在「环境变量」标签配置 FAL_KEY（fal.ai 聚合网关密钥）。"
    if "openai_api_key" in lowered:
        return "在「环境变量」标签配置 OPENAI_API_KEY。"
    if "elevenlabs" in lowered:
        return "在「环境变量」标签配置 ELEVENLABS_API_KEY。"
    if install_instructions.strip():
        return f"按工具说明安装或配置：{install_instructions.strip()[:200]}"
    return "请查看工具说明并完成安装或配置。"


def _humanize_tool_name(name: str) -> str:
    return name.replace("_", " ")


def enrich_core_binary(name: str, purpose: str) -> dict[str, str]:
    meta = CORE_BINARY_LABELS_ZH.get(name, {})
    return {
        "label_zh": meta.get("label_zh") or name,
        "purpose": meta.get("description_zh") or purpose,
    }
