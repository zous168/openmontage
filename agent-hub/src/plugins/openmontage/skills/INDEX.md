# OpenMontage — 技能索引

> 完整的 agent 上手指南见项目根目录的 [`AGENT_GUIDE.md`](../AGENT_GUIDE.md)。

本文件列出所有可用的 Layer 2 技能，并说明三层知识架构。

## 知识架构

```
Layer 1: tools/tool_registry.py          "有哪些工具、它们能做什么"
         tools/base_tool.py               每个工具声明：capabilities、tier、status、
                                          dependencies、cost 以及 agent_skills[]

         ↓ agent_skills[] 指向 ↓

Layer 2: skills/                          "OpenMontage 如何使用这些工具"
         项目专属约定：                    管线集成、artifact 映射、
         {core,creative,meta,pipelines}/   增强链顺序、质量检查清单

         ↓ 引用底层技术于 ↓

Layer 3: .agents/skills/                  "技术本身如何工作"
         来自 skills.sh 的通用 API 知识     正确的 import 路径、代码范式、
         （已安装 47 个技能）               约束、参数 — 与具体技术栈无关
```

**agent 如何使用这套架构：**
1. 编排器查询 Layer 1（`tool_registry.support_envelope()`）了解有哪些能力可用
2. 每个工具的 `agent_skills[]` 字段列出它依赖的 Layer 3 技能
3. Layer 2 技能（即本目录）教 agent OpenMontage 专属的约定
4. Layer 3 技能（`.agents/skills/`）提供通用 API 知识，按需加载

## 能力族与工具发现

每个工具都声明一个 `capability`（它做什么）和一个 `provider`（由谁/什么驱动）。注册表按 capability 对工具分组，便于 agent 发现某项任务的全部可选项。

### Selector / Provider 模式

对于存在多个 provider 的能力族（TTS、视频生成），架构采用：
- **Selector 工具**（`tts_selector`、`video_selector`、`image_selector`）—— 根据需求、API key 可用性和成本路由到最合适的 provider。Selector 会自动从注册表发现 provider。当用户未指定 provider 时，agent 应默认走 selector。
- **Provider 工具** —— 直接调用某个具体 provider。当用户明确点名某个 provider，或 selector 的路由结果不合适时，agent 使用这类工具。

### 能力族参考

**不要维护硬编码的工具清单。** 注册表是唯一事实来源。在运行时查询它：

```bash
python -c "from plugins.openmontage.tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.capability_catalog(), indent=2))"
```

在输出中重点关注这些能力族：

| Capability | Selector | 发现方式 |
|---|---|---|
| `tts` | `tts_selector` | 自动发现所有 `capability="tts"` 的工具 |
| `video_generation` | `video_selector` | 自动发现所有 `capability="video_generation"` 的工具 |
| `image_generation` | `image_selector` | 自动发现所有 `capability="image_generation"` 的工具 |
| `audio_processing` | — | 基于 FFmpeg 的本地工具 |
| `enhancement` | — | 混合 provider |
| `analysis` | — | 混合 provider |
| `character_animation` | — | 本地角色规格、SVG 骨骼、姿势库、动作时间线、预览与 QA |
| `graphics` | — | 本地渲染工具 |
| `music_generation` | — | 单一 provider |
| `subtitle` | — | 纯 Python |
| `avatar` | — | 本地 GPU 模型 |
| `video_post` | — | 基于 FFmpeg 的本地工具 |

### 新增工具

1. 把工具放进正确的 capability 目录（或在 `tools/` 下新建一个）
2. 在类定义中设置 `capability` 和 `provider`
3. 若加入的是多 provider 族，现有 selector 会自动发现它
4. 通过 `agent_skills[]` 挂上相关的 Layer 2 与 Layer 3 技能
5. 注册表自动发现工具 —— 无需手工注册
6. **不需要改动其他任何文件** —— selector、manifest、指令全部由注册表派生

## 核心技能（Core Skills）

| 技能 | 文件 | 触发场景 | Agent Skills（Layer 3） |
|-------|------|---------|----------------------|
| FFmpeg | `core/ffmpeg.md` | 视频编码、滤镜、合成 | `ffmpeg`、`video-toolkit` |
| Remotion | `core/remotion.md` | 基于 React 的合成，Phase 3+ | `remotion-best-practices`、`remotion` |
| HyperFrames | `core/hyperframes.md` | HTML/CSS/GSAP 合成运行时 —— 动态排版、音乐转视频、产品宣传片、网页捕获。已 vendor 至 v0.7.17（2026-06-27）。 | `hyperframes`（路由）→ `hyperframes-core`（契约）、`hyperframes-creative`（配色/字体/旁白）、`hyperframes-media`（TTS/BGM/SFX/字幕）、`hyperframes-animation`（全部运动）、`hyperframes-cli`、`hyperframes-registry`、`media-use`、`motion-graphics`、`music-to-video`（节拍驱动）、`website-to-video`、`remotion-to-hyperframes`（迁移）、`gsap-core`、`gsap-timeline` |
| WhisperX | `core/whisperx.md` | 带词级时间戳的转写 —— 默认 STT（离线、免费） | `speech-to-text` |
| Azure STT | （工具：`azure_stt`） | 可选的云端语音转文字，词级时间戳 —— 设置了 `AZURE_SPEECH_KEY` 时优先 | `azure-speech-to-text` |
| Subtitle Sync | `core/subtitle-sync.md` | 字幕时序与对齐 | `remotion-best-practices` |
| Color Grading | `core/color-grading.md` | FFmpeg 色彩配置、LUT 工作流、无障碍 | `ffmpeg` |

## 创意技能（Creative Skills）

| 技能 | 文件 | 触发场景 | Agent Skills（Layer 3） |
|-------|------|---------|----------------------|
| Video Editing | `creative/video-editing.md` | 剪辑决策、节奏、律动 | `ffmpeg`、`video-toolkit` |
| Enhancement Strategy | `creative/enhancement-strategy.md` | 叠加层的位置与密度 | `ffmpeg` |
| Data Visualization | `creative/data-visualization.md` | 图表类型选择、动画、标签摆放 | `d3-viz`、`remotion-best-practices` |
| Video Stitching | `creative/video-stitching.md` | 多片段拼接、AI 片段串联、空间构图 | `ffmpeg`、`video-toolkit` |
| Video Gen Prompting | `creative/video-gen-prompting.md` | 通用视频生成提示词词汇表；**规范的 5 要素规格**（Subject / Motion / Scene / Spatial / Camera）；约 200 个摄影语汇原语 | `ai-video-gen`、`ltx2`、`create-video` |
| ↳ Seedance Prompting | `creative/prompting/seedance-prompting.md` | **首选的高端默认项。** Seedance 2.0 八组件结构、多镜头、唇形同步、参考图转视频 | `seedance-2-0`、`ai-video-gen` |
| ↳ Grok Prompting | `creative/prompting/grok-prompting.md` | Grok 图像/视频提示词、编辑流程、参考图驱动的视频 | `grok-media` |
| ↳ Sora Prompting | `creative/prompting/sora-prompting.md` | Sora 2 结构化模板、进阶字段 | `ai-video-gen` |
| ↳ VEO Prompting | `creative/prompting/veo-prompting.md` | VEO 3.1 十四组件结构、艺术流派 | `ai-video-gen` |
| ↳ LTX Prompting | `creative/prompting/ltx-prompting.md` | LTX-2 六要素结构、音频提示词 | `ltx2` |
| ↳ HunyuanVideo Prompting | `creative/prompting/hunyuan-prompting.md` | HunyuanVideo 公式、I2V 最佳实践 | — |
| Storytelling | `creative/storytelling.md` | 叙事结构、钩子、节奏、Mayer 多媒体原则 | — |
| Sound Design | `creative/sound-design.md` | 音频闪避、LUFS 目标、音效时机、AI TTS 混音 | `elevenlabs` |
| Typography | `creative/typography.md` | 字体选择、文字尺寸、安全区、字幕样式 | — |
| ManimCE Usage | `creative/manim-usage.md` | 场景构图、动画时序、颜色使用 | `manimce-best-practices` |
| Image Gen Usage | `creative/image-gen-usage.md` | 提示词一致性、主参考图、批量策略 | `flux-best-practices`、`bfl-api` |
| Image Provider Usage | `creative/image-provider-usage.md` | Provider 选择（FLUX/Grok/OpenAI/Recraft/素材库）、成本与质量权衡 | `flux-best-practices`、`bfl-api`、`grok-media` |
| B-Roll Planning | `creative/broll-planning.md` | 素材库 vs 生成的取舍、检索式构造、素材评估 | — |
| Stock Sourcing Usage | `creative/stock-sourcing-usage.md` | Pexels/Pixabay 使用方式、参数、授权、集成 | — |
| Scene Detect Usage | `creative/scene-detect-usage.md` | 阈值调优、算法选择、内容预设 | — |
| Diagram Gen Usage | `creative/diagram-gen-usage.md` | 复杂度上限、渐进式构建、主题 | `beautiful-mermaid` |
| Music Gen Usage | `creative/music-gen-usage.md` | BPM 选择、提示词工程、时长匹配 | `music`、`elevenlabs` |
| Background Removal | `creative/bg-remove-usage.md` | 模型选择、alpha 抠图、合成工作流 | — |
| Upscaling | `creative/upscale-usage.md` | 放大倍数、模型选择、面部感知放大 | — |
| Face Restoration | `creative/face-restore-usage.md` | CodeFormer/GFPGAN 选择、保真度调节、与 face_enhance 的对比 | — |
| Lip Sync | `creative/lip-sync-usage.md` | Wav2Lip 模型选择、配音工作流、输入要求 | `faceswap` |
| Talking Head Gen | `creative/talking-head-gen-usage.md` | SadTalker/MuseTalk、照片转视频、表情调节 | `avatar-video` |
| Video Understanding | `creative/video-understand-usage.md` | 视觉问答、质量门禁、场景分类 | `video-understand` |

## 管线类型技能（Pipeline Type Skills）

管线类型技能针对特定视频形态提供制作指导，与 animated-explainer 或 talking-head 管线相互独立。

| 技能 | 文件 | 何时使用 |
|-------|------|-------------|
| Short-Form | `creative/short-form.md` | TikTok、Reels、Shorts —— 竖屏 9:16，60 秒以内 |
| Long-Form | `creative/long-form.md` | YouTube 10 分钟以上 —— 章节、留存、片尾卡 |
| Screen Recording | `creative/screen-recording.md` | 代码讲解、教程、软件演示 |
| Animation Pipeline | `creative/animation-pipeline.md` | 动态图形、缓动、转场、构图 |
| Character Animation Pipeline | `pipelines/character-animation/` | 本地绑定骨骼的卡通角色、姿势库、动作时间线、SVG/Canvas/Remotion/HyperFrames 渲染 |
| Cinematic | `creative/cinematic.md` | 黑边遮幅、电影节奏、分层音频、调色 |

## 管线阶段导演技能（Pipeline Stage Director Skills）

阶段导演技能教 agent 如何执行每一个管线阶段。每个技能都是一份详细的 markdown 文件，包含流程步骤、质量评分标准和自评准则。

### Animated Explainer 管线（`pipelines/explainer/`）—— v2.0

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/explainer/executive-producer.md` | `all` | **8 阶段串行编排、质量门禁、跨阶段检查、打回重做** |
| **Research Director** | `pipelines/explainer/research-director.md` | `research` | **网络调研方法论、5 组检索批次、行业格局/趋势/数据/受众/专家分析** |
| **Proposal Director** | `pipelines/explainer/proposal-director.md` | `proposal` | **由调研产出的概念选项、制作计划、成本估算、审批门禁** |
| Script Director | `pipelines/explainer/script-director.md` | `script` | 叙事架构、时序、增强提示、调研成果整合 |
| Scene Director | `pipelines/explainer/scene-director.md` | `scene_plan` | 视觉规划、技法库、可行性 |
| Asset Director | `pipelines/explainer/asset-director.md` | `assets` | TTS、图像生成、图表生成、音乐、预算 |
| Edit Director | `pipelines/explainer/edit-director.md` | `edit` | 时间线装配、字幕、音频闪避 |
| Compose Director | `pipelines/explainer/compose-director.md` | `compose` | FFmpeg/Remotion 渲染、音频混音 |
| Publish Director | `pipelines/explainer/publish-director.md` | `publish` | SEO 元数据、章节、导出打包 |

> **注意：** 旧的 `idea-director.md` 仍保留供参考，但在 v2.0 中已被 research + proposal 两阶段流程取代。talking-head 管线继续使用它自己的 `idea-director`。

### Talking Head 管线（`pipelines/talking-head/`）

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| Idea Director | `pipelines/talking-head/idea-director.md` | `idea` | 素材检查、内容评估 |
| Script Director | `pipelines/talking-head/script-director.md` | `script` | 转写、段落切分 |
| Scene Director | `pipelines/talking-head/scene-director.md` | `scene_plan` | 增强规划、叠加层摆放 |
| Asset Director | `pipelines/talking-head/asset-director.md` | `assets` | 字幕生成、音频提取 |
| Edit Director | `pipelines/talking-head/edit-director.md` | `edit` | 剪辑装配、字幕配置 |
| Compose Director | `pipelines/talking-head/compose-director.md` | `compose` | 增强链、渲染 |
| Publish Director | `pipelines/talking-head/publish-director.md` | `publish` | 元数据、导出打包 |

### Screen Demo 管线（`pipelines/screen-demo/`）—— v2.0

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/screen-demo/executive-producer.md` | `all` | **7 阶段串行编排、可读性门禁、音频清晰度、节奏检查** |
| Idea Director | `pipelines/screen-demo/idea-director.md` | `idea` | 工作流定界、UI 密度评估、产出形态选择 |
| Script Director | `pipelines/screen-demo/script-director.md` | `script` | 操作映射、流程化旁白、倍速规划 |
| Scene Director | `pipelines/screen-demo/scene-director.md` | `scene_plan` | 裁剪规划、标注克制、画幅比可行性 |
| Asset Director | `pipelines/screen-demo/asset-director.md` | `assets` | 字幕优先的素材包、音频清理、可复用叠加层 |
| Edit Director | `pipelines/screen-demo/edit-director.md` | `edit` | 紧凑时间线规划、倍速说明、字幕区域控制 |
| Compose Director | `pipelines/screen-demo/compose-director.md` | `compose` | 可读性优先的渲染、锐利的屏幕输出、验证 |
| Publish Director | `pipelines/screen-demo/publish-director.md` | `publish` | 可检索的元数据、章节打包、封面概念 |

### Clip Factory 管线（`pipelines/clip-factory/`）—— v2.0

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/clip-factory/executive-producer.md` | `all` | **7 阶段串行编排、片段筛选门禁、批次一致性、钩子位置** |
| Idea Director | `pipelines/clip-factory/idea-director.md` | `idea` | 批量策略、片段族、产出量规划 |
| Script Director | `pipelines/clip-factory/script-director.md` | `script` | 转写稿挖掘、排序、独立成立性校验 |
| Scene Director | `pipelines/clip-factory/scene-director.md` | `scene_plan` | 平台构图、安全区、裁剪可行性规划 |
| Asset Director | `pipelines/clip-factory/asset-director.md` | `assets` | 共享品牌套件、重定基准的字幕、批次音频一致性 |
| Edit Director | `pipelines/clip-factory/edit-director.md` | `edit` | 钩子优先的迷你剪辑、系列一致性 |
| Compose Director | `pipelines/clip-factory/compose-director.md` | `compose` | 多任务渲染、批处理容错、逐输出验证 |
| Publish Director | `pipelines/clip-factory/publish-director.md` | `publish` | 发布顺序、平台文案、批次编目 |

### Podcast Repurpose 管线（`pipelines/podcast-repurpose/`）—— v2.0

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/podcast-repurpose/executive-producer.md` | `all` | **7 阶段串行编排、音频保真门禁、片段质量、多交付物** |
| Idea Director | `pipelines/podcast-repurpose/idea-director.md` | `idea` | 按素材形态配比交付物、现实的长视频规划 |
| Script Director | `pipelines/podcast-repurpose/script-director.md` | `script` | 以说话人分离转写稿为准、亮点排序、章节映射 |
| Scene Director | `pipelines/podcast-repurpose/scene-director.md` | `scene_plan` | 忠于源素材的处理方式、音频波形图 vs 语录卡 vs 配套内容的规划 |
| Asset Director | `pipelines/podcast-repurpose/asset-director.md` | `assets` | 字幕优先的打包、说话人素材、可选的话题配图 |
| Edit Director | `pipelines/podcast-repurpose/edit-director.md` | `edit` | 钩子引导的播客片段、语录停留时长、配套内容的简洁性 |
| Compose Director | `pipelines/podcast-repurpose/compose-director.md` | `compose` | 音频优先的渲染、交付物优先级 |
| Publish Director | `pipelines/podcast-repurpose/publish-director.md` | `publish` | 单集互链、嘉宾署名、错峰发布逻辑 |

### Cinematic 管线（`pipelines/cinematic/`）—— v2.0

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/cinematic/executive-producer.md` | `all` | **7 阶段串行编排、情绪节奏门禁、色彩一致性、音频动态** |
| Idea Director | `pipelines/cinematic/idea-director.md` | `idea` | 情绪弧线选择、源素材事实、交付形态规划 |
| Script Director | `pipelines/cinematic/script-director.md` | `script` | 节拍映射、对白精选、字幕卡克制 |
| Scene Director | `pipelines/cinematic/scene-director.md` | `scene_plan` | 主画面规划、揭示结构、转场数量限制 |
| Asset Director | `pipelines/cinematic/asset-director.md` | `assets` | 源素材精选、补充插入镜头的纪律、音乐/环境声规划 |
| Edit Director | `pipelines/cinematic/edit-director.md` | `edit` | 情绪优先的节奏、揭示时机、音频驱动的律动 |
| Compose Director | `pipelines/cinematic/compose-director.md` | `compose` | 调色与混音收尾、画面处理判断 |
| Publish Director | `pipelines/cinematic/publish-director.md` | `publish` | 正片 vs 预告的打包、海报定帧概念 |

### Animation 管线（`pipelines/animation/`）—— v2.0

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/animation/executive-producer.md` | `all` | **8 阶段串行编排、质量门禁、运动一致性、数学准确性检查** |
| **Research Director** | `pipelines/animation/research-director.md` | `research` | **主题 + 动画技法调研、视觉参考扫描、结合模式的切入角度** |
| **Proposal Director** | `pipelines/animation/proposal-director.md` | `proposal` | **动画模式选择（Manim/Remotion/AI/图表）、复用策略、成本估算、审批门禁** |
| Script Director | `pipelines/animation/script-director.md` | `script` | 适配动画的节拍、文字克制、调研成果整合、感知模式的写作 |
| Scene Director | `pipelines/animation/scene-director.md` | `scene_plan` | 动态分镜规划、转场体系、工具路径映射 |
| Asset Director | `pipelines/animation/asset-director.md` | `assets` | 确定性的素材选择、可复用母题、可行性事实 |
| Edit Director | `pipelines/animation/edit-director.md` | `edit` | 停留时长、错峰规则、可读的运动规划 |
| Compose Director | `pipelines/animation/compose-director.md` | `compose` | 锐利的渲染输出、时序完整性、安全区检查 |
| Publish Director | `pipelines/animation/publish-director.md` | `publish` | 按动画模式打包、与封面体系对齐 |

> **注意：** 旧的 `idea-director.md` 仍保留供参考，但在 v2.0 中已被 research + proposal 两阶段流程取代。

### Hybrid 管线（`pipelines/hybrid/`）—— v2.0

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/hybrid/executive-producer.md` | `all` | **7 阶段串行编排、源素材/补充素材配比门禁、叠加层密度、连贯性** |
| Idea Director | `pipelines/hybrid/idea-director.md` | `idea` | 主导媒介选择、补充层规划、降级路径透明化 |
| Script Director | `pipelines/hybrid/script-director.md` | `script` | 源素材 vs 补充素材的节拍映射、对白保留、补充素材的必要性论证 |
| Scene Director | `pipelines/hybrid/scene-director.md` | `scene_plan` | 源素材为主的版式规则、叠加层密度控制、变体安全的规划 |
| Asset Director | `pipelines/hybrid/asset-director.md` | `assets` | 共享补充素材包、源素材 vs 生成素材的追踪 |
| Edit Director | `pipelines/hybrid/edit-director.md` | `edit` | 主线剪辑优先的工作流、分层补充素材的时机、可读的变体 |
| Compose Director | `pipelines/hybrid/compose-director.md` | `compose` | 源素材/补充素材配比检查、变体验证、连贯的混音 |
| Publish Director | `pipelines/hybrid/publish-director.md` | `publish` | 母版 vs 衍生版的打包、素材混合的元数据 |

### Avatar Spokesperson 管线（`pipelines/avatar-spokesperson/`）—— v2.0

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/avatar-spokesperson/executive-producer.md` | `all` | **7 阶段串行编排、唇形同步质量门禁、出镜人构图、CTA 落点** |
| Idea Director | `pipelines/avatar-spokesperson/idea-director.md` | `idea` | 数字人路径分类、CTA 定界、能力事实 |
| Script Director | `pipelines/avatar-spokesperson/script-director.md` | `script` | 口播文案打磨、适配场景的节奏、文字克制 |
| Scene Director | `pipelines/avatar-spokesperson/scene-director.md` | `scene_plan` | 出镜人版式、背景纪律、变体的现实性 |
| Asset Director | `pipelines/avatar-spokesperson/asset-director.md` | `assets` | 锁定数字人路径、旁白落地、精简的补充素材包 |
| Edit Director | `pipelines/avatar-spokesperson/edit-director.md` | `edit` | 出镜人优先的剪辑规划、叠加层时机、CTA 落点 |
| Compose Director | `pipelines/avatar-spokesperson/compose-director.md` | `compose` | 唇形同步验证、字幕安全构图、干净的渲染检查 |
| Publish Director | `pipelines/avatar-spokesperson/publish-director.md` | `publish` | 受众导向的打包、出镜人优先的封面概念 |

### Localization Dub 管线（`pipelines/localization-dub/`）—— v2.0

| 技能 | 文件 | 阶段 | 关键能力 |
|-------|------|-------|-----------------|
| **Executive Producer** | `pipelines/localization-dub/executive-producer.md` | `all` | **7 阶段串行编排、翻译准确性门禁、时序保持、逐语种 QA** |
| Idea Director | `pipelines/localization-dub/idea-director.md` | `idea` | 范围定义、语种规划、术语表与审校记录 |
| Script Director | `pipelines/localization-dub/script-director.md` | `script` | 以转写稿为准、译制脚本打包、术语保留 |
| Scene Director | `pipelines/localization-dub/scene-director.md` | `scene_plan` | 配音模式选择、时序风险映射、屏幕文字规划 |
| Asset Director | `pipelines/localization-dub/asset-director.md` | `assets` | 字幕优先的本地化套件、配音音频生成、可选的唇形同步 |
| Edit Director | `pipelines/localization-dub/edit-director.md` | `edit` | 逐语种时间线、覆盖度规划、时序调整 |
| Compose Director | `pipelines/localization-dub/compose-director.md` | `compose` | 逐语种渲染、字幕适配检查、输出标注 |
| Publish Director | `pipelines/localization-dub/publish-director.md` | `publish` | 语种打包、元数据精确性、QA 备注保留 |

## 元技能（Meta Skills）

适用于所有管线的横切技能：

| 技能 | 文件 | 用途 |
|-------|------|---------|
| Onboarding | `meta/onboarding.md` | 首次交互问候、能力发现、启动提示词 |
| Reviewer | `meta/reviewer.md` | 每个阶段之后的自评协议 |
| Checkpoint Protocol | `meta/checkpoint-protocol.md` | 何时/如何写检查点并请求人工审批 |
| Skill Creator | `meta/skill-creator.md` | 在管线运行过程中动态创建新技能 |
| Animation Runtime Selector | `meta/animation-runtime-selector.md` | 逐场景选择渲染运行时 + 动画库 |
| Taste Direction | `meta/taste-direction.md` | 把 brief 转换成审美旋钮、反模式和参考策略，供 proposal/playbook/atelier 使用 |
| Bespoke Composition (Atelier) | `meta/bespoke-composition.md` | 从零手工编写合成（旗舰作品）—— 不用现成场景类型；串联 艺术指导 → 运动原则 → 引擎机制 → atelier 渲染 |

## 风格剧本（Style Playbooks）

风格剧本（`styles/*.yaml`）定义视觉语言、排版、运动、音频以及素材生成约束。它们会按 `schemas/styles/playbook.schema.json` 做校验。

| 剧本 | 类别 | 调性 | 适用于 |
|----------|----------|------|----------|
| `clean-professional` | motion-graphics | 精致、可信 | 企业、教育、SaaS |
| `premium-minimalist` | minimalist | 沉静、编辑风 | 投资人更新、专家讲解、产品叙事 |
| `flat-motion-graphics` | motion-graphics | 有活力、张扬 | 社交媒体、TikTok、创业公司 |
| `minimalist-diagram` | whiteboard | 聚焦、技术向 | 技术深度解析、架构 |

通过 `styles/playbook_loader.py` 加载：`load_playbook("clean-professional")`

## 已安装的 Agent Skills（Layer 3）

所有 agent skills 都位于 `.agents/skills/`，通过 `npx skills add` 管理。
Claude Code 经由 `.claude/skills/` 中的符号链接访问它们。

| 类别 | 已安装技能 | 来源 |
|----------|-----------------|--------|
| **视频合成** | `remotion-best-practices`、`remotion`、`hyperframes`（路由）、`hyperframes-core`、`hyperframes-creative`、`hyperframes-media`、`hyperframes-animation`、`hyperframes-cli`、`hyperframes-registry`、`media-use`、`motion-graphics`、`music-to-video`、`remotion-to-hyperframes`、`website-to-video` | `remotion-dev/skills`、`digitalsamba/claude-code-video-toolkit`、`heygen-com/hyperframes`（已 vendor v0.7.17，见 `.agents/skills/hyperframes/PROVENANCE.md`） |
| **视频处理** | `ffmpeg`、`video-toolkit` | `digitalsamba/claude-code-video-toolkit` |
| **TTS 与音频** | `text-to-speech`、`speech-to-text`（whisper，默认 STT）、`azure-speech-to-text`（可选云端 STT）、`music`、`sound-effects`、`elevenlabs`、`agents`、`setup-api-key` | `elevenlabs/skills`、`digitalsamba/claude-code-video-toolkit` |
| **图像生成** | `flux-best-practices`、`bfl-api`、`grok-media` | `black-forest-labs/skills`、OpenMontage 本地技能 |
| **数学动画** | `manimce-best-practices`、`manimgl-best-practices`、`manim-composer` | `adithya-s-k/manim_skill` |
| **3D 图形** | `threejs-animation`、`threejs-fundamentals`、`threejs-geometry`、`threejs-interaction`、`threejs-lighting`、`threejs-loaders`、`threejs-materials`、`threejs-postprocessing`、`threejs-shaders`、`threejs-textures` | `cloudai-x/threejs-skills` |
| **图表** | `beautiful-mermaid`、`d3-viz` | `intellectronica/agent-skills`、`davila7/claude-code-templates` |
| **动画** | `framer-motion`、`lottie-bodymovin` | `pproenca/dot-skills`、`dylantarre/animation-principles` |
| **设计** | `tailwind-design-system`、`web-design-guidelines`、`vercel-react-best-practices`、`vercel-composition-patterns` | `wshobson/agents`、`vercel-labs/agent-skills` |
| **AI 视频（HeyGen）** | `heygen`、`avatar-video`、`create-video`、`faceswap`、`ai-video-gen`、`video-download`、`video-edit`、`video-translate`、`video-understand`、`visual-style` | `heygen-com/skills` |
| **AI 视频/图像/TTS/数字人（Kling 官方）** | `kling-official` —— 官方直连 API 鉴权、Classic/Turbo/Omni 任务协议、多参考图 Omni 语法、内部 Elements/Account Usage 辅助接口、回调说明、TTS 音色参数、数字人/唇形同步的人脸选择、错误处理，以及 `kling_official_video` / `kling_official_image` / `kling_tts` / `kling_avatar` / `kling_lip_sync` 的成本治理 | OpenMontage 本地技能 |
| **AI 视频（高端）** | `seedance-2-0` —— 首选的高端默认项（电影感、预告片、多镜头、唇形同步、同步音频）；通过 `seedance_video`（fal.ai）或 `heygen_video` Avatar Shots 访问 | OpenMontage 本地技能 |
| **基础设施** | `acestep`、`ltx2`、`playwright-recording` | `digitalsamba/claude-code-video-toolkit` |
