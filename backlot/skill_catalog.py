"""Chinese labels and descriptions for the Backlot skill catalog UI.

Mappings live here only — skill markdown under ``skills/`` and ``.agents/skills/``
is never modified.
"""

from __future__ import annotations

from typing import Any, Optional

# Pipeline stage directors (skills/pipelines/*/*-director.md)
_STAGE_CATALOG: dict[str, dict[str, str]] = {
    "executive-producer": {
        "label_zh": "总制片",
        "description_zh": "统筹整条流水线的阶段顺序、质量门与跨阶段回退策略",
    },
    "research-director": {
        "label_zh": "调研导演",
        "description_zh": "网络调研、受众与数据收集，产出调研简报",
    },
    "proposal-director": {
        "label_zh": "方案导演",
        "description_zh": "基于调研生成创意方案、成本估算与审批材料",
    },
    "idea-director": {
        "label_zh": "创意导演",
        "description_zh": "从主题发散创意方向、钩子与叙事结构，产出创意简报",
    },
    "reference-director": {
        "label_zh": "参考分析导演",
        "description_zh": "分析参考视频的 pacing、结构与风格，提炼可复用要点",
    },
    "script-director": {
        "label_zh": "脚本导演",
        "description_zh": "撰写旁白脚本、段落节奏与 TTS 表达提示",
    },
    "scene-director": {
        "label_zh": "分镜导演",
        "description_zh": "规划镜头、画面手法与可视化可行性",
    },
    "character-design-director": {
        "label_zh": "角色设计导演",
        "description_zh": "定义角色外观、风格约束与一致性规范",
    },
    "rig-plan-director": {
        "label_zh": "绑骨方案导演",
        "description_zh": "规划角色绑骨结构、姿势库与动画实现路径",
    },
    "asset-director": {
        "label_zh": "资产导演",
        "description_zh": "生成/收集 TTS、图像、音乐、图表等阶段资产",
    },
    "edit-director": {
        "label_zh": "剪辑导演",
        "description_zh": "时间线组装、转场、字幕与音频 ducking",
    },
    "compose-director": {
        "label_zh": "合成导演",
        "description_zh": "FFmpeg / Remotion / HyperFrames 最终渲染与混音",
    },
    "publish-director": {
        "label_zh": "发布导演",
        "description_zh": "SEO 元数据、章节标记与多平台导出打包",
    },
}

# Layer 2 skills keyed by id (skills/... path without .md)
_LAYER2_CATALOG: dict[str, dict[str, str]] = {
    # core
    "skills/core/ffmpeg": {
        "name_zh": "FFmpeg 集成",
        "description_zh": "音视频编码、滤镜、合成与素材预处理的项目内用法",
    },
    "skills/core/remotion": {
        "name_zh": "Remotion 集成",
        "description_zh": "React 程序化视频合成、场景组件与渲染流程",
    },
    "skills/core/hyperframes": {
        "name_zh": "HyperFrames 集成",
        "description_zh": "HTML/CSS/GSAP 动效合成—— kinetic 字效、音乐驱动、产品片与网页录制",
    },
    "skills/core/whisperx": {
        "name_zh": "WhisperX 转写",
        "description_zh": "离线语音转文字与词级时间戳，默认 STT 方案",
    },
    "skills/core/subtitle-sync": {
        "name_zh": "字幕同步",
        "description_zh": "字幕时间轴对齐、断句与可读性优化",
    },
    "skills/core/color-grading": {
        "name_zh": "调色",
        "description_zh": "FFmpeg 色彩配置、LUT 工作流与无障碍对比度",
    },
    # creative — format pipelines
    "skills/creative/short-form": {
        "name_zh": "短视频",
        "description_zh": "TikTok / Reels / Shorts：竖屏 9:16、60 秒内节奏与钩子",
    },
    "skills/creative/long-form": {
        "name_zh": "长视频",
        "description_zh": "YouTube 10 分钟+：章节结构、留存与片尾引导",
    },
    "skills/creative/screen-recording": {
        "name_zh": "屏幕录制",
        "description_zh": "代码讲解、教程与软件演示的录屏制作规范",
    },
    "skills/creative/animation-pipeline": {
        "name_zh": "动画 / 动效流水线",
        "description_zh": "动效图形、easing、转场与合成节奏",
    },
    "skills/creative/cinematic": {
        "name_zh": "电影感",
        "description_zh": "宽银幕、胶片节奏、分层音频与电影级调色",
    },
    "skills/creative/ink-theater": {
        "name_zh": "水墨剧场",
        "description_zh": "手绘/水墨风格「会动的插画」创意与实现指引",
    },
    "skills/creative/animated-drawing": {
        "name_zh": "动画手绘",
        "description_zh": "将用户提供的手绘或照片动画化为视频画面",
    },
    # creative — craft
    "skills/creative/video-editing": {
        "name_zh": "视频剪辑",
        "description_zh": "切点、节奏、留白与叙事剪辑决策",
    },
    "skills/creative/enhancement-strategy": {
        "name_zh": "画面增强策略",
        "description_zh": "叠加层 placement、密度与增强链顺序",
    },
    "skills/creative/data-visualization": {
        "name_zh": "数据可视化",
        "description_zh": "图表选型、动画、标注与信息层次",
    },
    "skills/creative/video-stitching": {
        "name_zh": "视频拼接",
        "description_zh": "多片段组装、AI 镜头衔接与空间构图",
    },
    "skills/creative/video-gen-prompting": {
        "name_zh": "视频生成 Prompt（通用）",
        "description_zh": "跨模型通用的五维 Prompt 规范：主体 / 运动 / 场景 / 空间 / 镜头",
    },
    "skills/creative/prompting/seedance-prompting": {
        "name_zh": "Seedance Prompt",
        "description_zh": "Seedance 2.0 八段式结构、多镜头与参考图生视频",
    },
    "skills/creative/prompting/grok-prompting": {
        "name_zh": "Grok Prompt",
        "description_zh": "Grok 图像/视频 Prompt、编辑流与参考图视频",
    },
    "skills/creative/prompting/sora-prompting": {
        "name_zh": "Sora Prompt",
        "description_zh": "Sora 2 结构化模板与高级字段",
    },
    "skills/creative/prompting/veo-prompting": {
        "name_zh": "VEO Prompt",
        "description_zh": "VEO 3.1 十四组件结构与艺术风格",
    },
    "skills/creative/prompting/ltx-prompting": {
        "name_zh": "LTX Prompt",
        "description_zh": "LTX-2 六要素结构与音频 Prompt",
    },
    "skills/creative/prompting/hunyuan-prompting": {
        "name_zh": "HunyuanVideo Prompt",
        "description_zh": "HunyuanVideo 1.5 公式与图生视频最佳实践",
    },
    "skills/creative/storytelling": {
        "name_zh": "叙事结构",
        "description_zh": "钩子、节奏、Mayer 认知原则与解说类叙事",
    },
    "skills/creative/sound-design": {
        "name_zh": "声音设计",
        "description_zh": "音频 ducking、LUFS 目标、SFX 时机与 TTS 混音",
    },
    "skills/creative/typography": {
        "name_zh": "字幕与排版",
        "description_zh": "字体选择、安全区、字号层级与字幕样式",
    },
    "skills/creative/manim-usage": {
        "name_zh": "Manim 用法",
        "description_zh": "ManimCE 场景构图、动画时序与配色",
    },
    "skills/creative/image-gen-usage": {
        "name_zh": "图像生成用法",
        "description_zh": "Prompt 一致性、主视觉参考与批量策略",
    },
    "skills/creative/image-provider-usage": {
        "name_zh": "图像供应商选择",
        "description_zh": "FLUX / Grok / OpenAI / Recraft / 图库的成本与质量权衡",
    },
    "skills/creative/broll-planning": {
        "name_zh": "B-Roll 规划",
        "description_zh": "图库 vs 生成素材决策、检索词与素材评估",
    },
    "skills/creative/stock-sourcing-usage": {
        "name_zh": "图库素材",
        "description_zh": "Pexels / Pixabay 参数、授权与项目集成",
    },
    "skills/creative/scene-detect-usage": {
        "name_zh": "场景检测",
        "description_zh": "阈值、算法与内容预设的调参",
    },
    "skills/creative/diagram-gen-usage": {
        "name_zh": "图表生成",
        "description_zh": "复杂度上限、渐进展示与主题风格",
    },
    "skills/creative/music-gen-usage": {
        "name_zh": "音乐生成",
        "description_zh": "BPM 选择、Prompt 工程与时长匹配",
    },
    "skills/creative/bg-remove-usage": {
        "name_zh": "背景移除",
        "description_zh": "模型选择、alpha 抠图与合成工作流",
    },
    "skills/creative/upscale-usage": {
        "name_zh": "超分辨率",
        "description_zh": "放大倍数、模型选择与面部增强",
    },
    "skills/creative/face-restore-usage": {
        "name_zh": "面部修复",
        "description_zh": "CodeFormer / GFPGAN 选择与保真度调参",
    },
    "skills/creative/lip-sync-usage": {
        "name_zh": "口型同步",
        "description_zh": "Wav2Lip 模型、配音流程与输入要求",
    },
    "skills/creative/talking-head-gen-usage": {
        "name_zh": "说话人像生成",
        "description_zh": "SadTalker / MuseTalk 照片驱动与表情调参",
    },
    "skills/creative/video-understand-usage": {
        "name_zh": "视频理解",
        "description_zh": "视觉 QA、质量门控与场景分类",
    },
    # meta
    "skills/meta/onboarding": {
        "name_zh": "新用户引导",
        "description_zh": "首次对话发现能力、分类用户场景并给出可复制的起步 Prompt",
    },
    "skills/meta/video-reference-analyst": {
        "name_zh": "参考视频分析",
        "description_zh": "分析用户提供的参考片：结构、节奏、风格与可借鉴要点",
    },
    "skills/meta/reviewer": {
        "name_zh": "审阅",
        "description_zh": "阶段产出自检清单、质量 rubric 与改进建议",
    },
    "skills/meta/checkpoint-protocol": {
        "name_zh": "检查点协议",
        "description_zh": "人工审批检查点的读写规范与 Agent 行为约束",
    },
    "skills/meta/capability-extension": {
        "name_zh": "能力扩展",
        "description_zh": "注册新工具/供应商时的清单与集成步骤",
    },
    "skills/meta/creative-intake": {
        "name_zh": "创意 intake",
        "description_zh": "从模糊需求提炼可执行的 brief 与约束",
    },
    "skills/meta/bespoke-composition": {
        "name_zh": "定制合成（Atelier）",
        "description_zh": "高度定制、非模板化的合成与视觉实验模式",
    },
    "skills/meta/taste-direction": {
        "name_zh": "审美方向",
        "description_zh": "统一视觉调性、避免 generic AI 审美",
    },
    "skills/meta/voice-performance-director": {
        "name_zh": "配音表演指导",
        "description_zh": "结构化 TTS  delivery 提示，让旁白更自然有表现",
    },
    "skills/meta/animation-runtime-selector": {
        "name_zh": "动画运行时选择",
        "description_zh": "在 Remotion / HyperFrames / Manim 等合成引擎间选型",
    },
    "skills/meta/skill-creator": {
        "name_zh": "技能创作",
        "description_zh": "为本仓库撰写 Layer 2/3 技能文档的结构与规范",
    },
}

# Layer 3 agent skills keyed by folder slug
_LAYER3_CATALOG: dict[str, dict[str, str]] = {
    "ffmpeg": {"name_zh": "FFmpeg", "description_zh": "音视频转码、缩放、抽轨、压缩与 Remotion 兼容预处理"},
    "video-toolkit": {"name_zh": "视频工具包", "description_zh": "端到端视频制作 CLI 工作流与常见任务编排"},
    "video-edit": {"name_zh": "视频编辑", "description_zh": "本地 ffmpeg 裁剪、拼接、转场等编辑操作"},
    "video-download": {"name_zh": "视频下载", "description_zh": "从 YouTube 等平台下载音视频素材"},
    "video-translate": {"name_zh": "视频翻译", "description_zh": "多语言配音与翻译工作流"},
    "video-understand": {"name_zh": "视频理解", "description_zh": "本地抽帧与内容理解辅助 QA"},
    "remotion": {"name_zh": "Remotion", "description_zh": "Remotion 项目结构、Composition 与渲染参数"},
    "remotion-best-practices": {"name_zh": "Remotion 最佳实践", "description_zh": "Remotion 动画、序列、音频与性能优化"},
    "remotion-to-hyperframes": {"name_zh": "Remotion → HyperFrames", "description_zh": "将现有 Remotion 合成迁移到 HyperFrames"},
    "hyperframes": {"name_zh": "HyperFrames", "description_zh": "HyperFrames 技能路由与总览"},
    "hyperframes-core": {"name_zh": "HyperFrames 核心", "description_zh": "HyperFrames 合成契约、build 与导出"},
    "hyperframes-creative": {"name_zh": "HyperFrames 创意", "description_zh": "配色、字体、旁白与视觉方向"},
    "hyperframes-media": {"name_zh": "HyperFrames 媒体", "description_zh": "TTS、BGM、SFX 与字幕资产"},
    "hyperframes-animation": {"name_zh": "HyperFrames 动画", "description_zh": "原子动效、时间轴与转场模式"},
    "hyperframes-cli": {"name_zh": "HyperFrames CLI", "description_zh": "npx hy 开发循环与预览"},
    "hyperframes-registry": {"name_zh": "HyperFrames 组件库", "description_zh": "注册表 blocks 安装与接线"},
    "media-use": {"name_zh": "Media OS", "description_zh": "统一解析 BGM、SFX、旁白等媒体需求"},
    "motion-graphics": {"name_zh": "Motion Graphics", "description_zh": "短动效、标题卡与设计导向 motion 片段"},
    "music-to-video": {"name_zh": "音乐驱动视频", "description_zh": "按节拍切镜与音乐同步可视化"},
    "website-to-video": {"name_zh": "网页转视频", "description_zh": "抓取网页并转为宣传/演示视频"},
    "flux-best-practices": {"name_zh": "FLUX 最佳实践", "description_zh": "BFL FLUX 全系列 Prompt 与模型选型"},
    "bfl-api": {"name_zh": "BFL API", "description_zh": "Black Forest Labs API 端点、参数与计费"},
    "grok-media": {"name_zh": "Grok 媒体", "description_zh": "xAI Grok 图像/视频生成与编辑"},
    "ai-video-gen": {"name_zh": "AI 视频生成", "description_zh": "多供应商文生视频/图生视频通用指南"},
    "ltx2": {"name_zh": "LTX-2", "description_zh": "LTX-2.3 22B 文生视频与参数"},
    "seedance-2-0": {"name_zh": "Seedance 2.0", "description_zh": "字节 Seedance 电影级片段生成"},
    "create-video": {"name_zh": "HeyGen 视频", "description_zh": "HeyGen Prompt 驱动视频创建"},
    "elevenlabs": {"name_zh": "ElevenLabs", "description_zh": "语音、音效与音乐 API"},
    "text-to-speech": {"name_zh": "HeyGen TTS", "description_zh": "HeyGen 语音合成与参数"},
    "speech-to-text": {"name_zh": "语音转文字", "description_zh": "ElevenLabs Scribe 转写"},
    "sound-effects": {"name_zh": "音效生成", "description_zh": "文本描述生成 SFX"},
    "music": {"name_zh": "音乐生成", "description_zh": "ElevenLabs Music API"},
    "doubao-tts": {"name_zh": "豆包 TTS", "description_zh": "火山/豆包中文与多语言旁白"},
    "azure-speech-to-text": {"name_zh": "Azure 语音转写", "description_zh": "Azure Speech 词级时间戳 STT"},
    "kling-official": {"name_zh": "可灵官方 API", "description_zh": "可灵图像、视频、数字人与 TTS 调用"},
    "dashscope": {"name_zh": "DashScope", "description_zh": "阿里云灵积模型 API"},
    "gemini-omni": {"name_zh": "Gemini Omni", "description_zh": "Google Gemini 多模态 API"},
    "comfyui": {"name_zh": "ComfyUI", "description_zh": "ComfyUI 工作流与节点集成"},
    "faceswap": {"name_zh": "换脸", "description_zh": "HeyGen 视频换脸 API"},
    "avatar-video": {"name_zh": "数字人视频", "description_zh": "可控数字人视频生成"},
    "heygen": {"name_zh": "HeyGen（旧）", "description_zh": "已弃用，请用 create-video / text-to-speech"},
    "acestep": {"name_zh": "ACE-Step", "description_zh": "ACE-Step 1.5 AI 背景音乐生成"},
    "lyria": {"name_zh": "Lyria", "description_zh": "Google Lyria 音乐生成"},
    "beautiful-mermaid": {"name_zh": "Mermaid 图表", "description_zh": "Mermaid 转 SVG/PNG 渲染"},
    "d3-viz": {"name_zh": "D3 可视化", "description_zh": "D3 交互式数据可视化"},
    "manimce-best-practices": {"name_zh": "ManimCE", "description_zh": "Manim Community Edition 场景与动画"},
    "manimgl-best-practices": {"name_zh": "ManimGL", "description_zh": "3b1b ManimGL 用法"},
    "manim-composer": {"name_zh": "Manim 作曲", "description_zh": "教育动画场景编排辅助"},
    "gsap-core": {"name_zh": "GSAP 核心", "description_zh": "gsap.to / timeline 基础 API"},
    "gsap-timeline": {"name_zh": "GSAP 时间轴", "description_zh": "复杂时间轴编排与 sequencing"},
    "gsap-scrolltrigger": {"name_zh": "GSAP ScrollTrigger", "description_zh": "滚动驱动动画"},
    "gsap-react": {"name_zh": "GSAP + React", "description_zh": "useGSAP 与 React 集成"},
    "gsap-plugins": {"name_zh": "GSAP 插件", "description_zh": "插件注册与常用扩展"},
    "gsap-performance": {"name_zh": "GSAP 性能", "description_zh": "优先 transform、减少 layout thrashing 等性能实践"},
    "gsap-frameworks": {"name_zh": "GSAP 框架集成", "description_zh": "Vue / Svelte 等非 React 框架"},
    "gsap-utils": {"name_zh": "GSAP 工具", "description_zh": "clamp、mapRange 等工具函数"},
    "framer-motion": {"name_zh": "Framer Motion", "description_zh": "React 动效与 Disney 12 原则"},
    "lottie-bodymovin": {"name_zh": "Lottie", "description_zh": "Bodymovin / Lottie 动画导出与播放"},
    "threejs-fundamentals": {"name_zh": "Three.js 基础", "description_zh": "场景、相机、渲染器与 Object3D"},
    "threejs-geometry": {"name_zh": "Three.js 几何", "description_zh": "内置几何与 BufferGeometry"},
    "threejs-materials": {"name_zh": "Three.js 材质", "description_zh": "PBR、Basic、Shader 材质"},
    "threejs-textures": {"name_zh": "Three.js 纹理", "description_zh": "纹理类型与 UV 映射"},
    "threejs-lighting": {"name_zh": "Three.js 光照", "description_zh": "光源类型、阴影与环境光"},
    "threejs-animation": {"name_zh": "Three.js 动画", "description_zh": "关键帧与骨骼动画"},
    "threejs-loaders": {"name_zh": "Three.js 加载器", "description_zh": "GLTF、纹理与资源加载"},
    "threejs-interaction": {"name_zh": "Three.js 交互", "description_zh": "射线检测、控制器与鼠标事件"},
    "threejs-shaders": {"name_zh": "Three.js Shader", "description_zh": "GLSL 与 ShaderMaterial"},
    "threejs-postprocessing": {"name_zh": "Three.js 后期", "description_zh": "EffectComposer 与 bloom 等"},
    "character-rigging": {"name_zh": "角色绑骨", "description_zh": "2D 角色 rig 结构与姿势约束"},
    "pose-library-design": {"name_zh": "姿势库设计", "description_zh": "可复用 2D 姿势与动作库设计"},
    "svg-character-animation": {"name_zh": "SVG 角色动画", "description_zh": "GSAP/CSS 驱动 SVG 角色"},
    "character-animation-qa": {"name_zh": "角色动画 QA", "description_zh": "本地角色动画 schema 与预览检查"},
    "canvas-procedural-animation": {"name_zh": "Canvas 程序化动画", "description_zh": "Canvas  procedural 动效模式"},
    "synthetic-screen-recording": {"name_zh": "合成录屏", "description_zh": "终端/界面风格合成录屏视觉"},
    "playwright-recording": {"name_zh": "Playwright 录制", "description_zh": "浏览器交互录制成视频"},
    "visual-style": {"name_zh": "视觉风格", "description_zh": "可移植视觉设计系统提取与应用"},
    "tailwind-design-system": {"name_zh": "Tailwind 设计系统", "description_zh": "Tailwind v4 可扩展设计 token"},
    "web-design-guidelines": {"name_zh": "Web 界面规范", "description_zh": "UI 代码可访问性与界面规范审查"},
    "vercel-react-best-practices": {"name_zh": "React 性能", "description_zh": "Vercel React/Next.js 性能优化"},
    "vercel-composition-patterns": {"name_zh": "React 组合模式", "description_zh": "Compound components 与可维护组合"},
    "agents": {"name_zh": "ElevenLabs Agents", "description_zh": "语音 AI Agent 构建"},
    "setup-api-key": {"name_zh": "API 密钥配置", "description_zh": "ElevenLabs 等供应商密钥 onboarding"},
}


def _pipeline_director_meta(item: dict[str, Any]) -> dict[str, str]:
    pipeline = item.get("pipeline") or item.get("pipeline_id") or ""
    stage = item.get("stage") or ""
    stage_meta = _STAGE_CATALOG.get(stage, {})
    stage_label = stage_meta.get("label_zh") or stage.replace("-", " ")
    name_zh = f"{pipeline} · {stage_label}" if pipeline else stage_label
    desc = stage_meta.get("description_zh") or "指导 Agent 在本流水线阶段执行流程、自检与产出工件"
    if pipeline:
        desc = f"「{pipeline}」流水线：{desc}"
    return {"name_zh": name_zh, "description_zh": desc}


def skill_name_zh(item: dict[str, Any]) -> str:
    skill_id = item.get("id") or ""
    layer = item.get("layer")
    if layer == 3:
        slug = skill_id.split("/")[-1] if "/" in skill_id else skill_id
        meta = _LAYER3_CATALOG.get(slug, {})
        return meta.get("name_zh") or item.get("name") or slug
    if skill_id in _LAYER2_CATALOG:
        return _LAYER2_CATALOG[skill_id]["name_zh"]
    if item.get("category") == "pipelines" and item.get("stage"):
        return _pipeline_director_meta(item)["name_zh"]
    return item.get("name") or skill_id


def skill_description_zh(item: dict[str, Any]) -> str:
    skill_id = item.get("id") or ""
    layer = item.get("layer")
    if layer == 3:
        slug = skill_id if "/" not in skill_id else skill_id.split("/")[-1]
        meta = _LAYER3_CATALOG.get(slug, {})
        if meta.get("description_zh"):
            return meta["description_zh"]
        return "底层 API / 框架技术知识，供工具调用时按需加载"
    if skill_id in _LAYER2_CATALOG:
        return _LAYER2_CATALOG[skill_id]["description_zh"]
    if item.get("category") == "pipelines" and item.get("stage"):
        return _pipeline_director_meta(item)["description_zh"]
    category = item.get("category") or ""
    fallbacks = {
        "core": "OpenMontage 核心集成技能，定义项目内如何使用底层工具",
        "creative": "创意与制作规范，指导 Agent 在特定场景下的决策与 Prompt",
        "meta": "编排、审阅、引导 onboarding 等元技能，跨流水线通用",
    }
    return fallbacks.get(category, "项目流程技能，教 Agent 在本仓库中何时、如何制作")


def stage_label_zh(stage: Optional[str]) -> str:
    if not stage:
        return ""
    return _STAGE_CATALOG.get(stage, {}).get("label_zh") or stage.replace("-", " ")


def enrich_skill_item(item: dict[str, Any]) -> dict[str, Any]:
    """Add ``name_zh`` and ``description_zh`` for Backlot catalog UI."""
    item["name_zh"] = skill_name_zh(item)
    item["description_zh"] = skill_description_zh(item)
    if item.get("stage"):
        item["stage_label_zh"] = stage_label_zh(item["stage"])
    return item
