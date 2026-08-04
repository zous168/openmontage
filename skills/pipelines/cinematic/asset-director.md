# 素材导演 —— Cinematic 管线

## 何时使用

本阶段为最终的电影感剪辑准备可用媒体：源素材精选、标题卡资源、可选的辅助插入镜头、音乐、环境声，以及需要时的字幕资源。

## 电影感标题与叠加层的动画编写

在编写标题卡、姓名条或 SVG 叠加层之前，读 **`skills/meta/animation-runtime-selector.md`** 了解运行时路由。电影感作品依赖的是少数几种高手艺的运动范式：

| 电影感需求 | 推荐做法 |
|---|---|
| 带细腻揭示的主标题 | Remotion 的 `HeroTitle` 组件（已存在） |
| SVG 上的 Logo 构建 / 电影感音效动画 | GSAP DrawSVG + MotionPath —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 在宽幅静图或叠加层上做曲线镜头运动 | GSAP MotionPath —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 逐字符的标题揭示（高端/预告片风格） | GSAP SplitText —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 电影感缓动（虚幻引擎式、顿挫、带重量） | GSAP CustomEase / EasePack —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 带弹性归位的下三分之一姓名条 | Remotion 的 `spring()` 通常就够；需要顿挫感时用 GSAP CustomEase |
| 胶片颗粒 / 粒子叠加 | Remotion `ParticleOverlay`（已存在） |
| 调色 / LUT | `tools/enhancement/color_grade.py`（不属于动画范畴） |

**电影感是 GSAP 最常物有所值的地方** —— 这个类型奖励精心打磨的缓动和精确的曲线运动，而原语 `interpolate()` 很难干净地表达它们。但也别滥用：做一个淡入标题时，Remotion 的 `spring()` 仍然胜过引入整个 GSAP 依赖。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["proposal"]["proposal_packet"]` | 场景意图与节拍方案 |
| 工具 | `subtitle_gen`、`audio_enhance`、`image_selector`、`video_selector`、`pixabay_music`（免费，默认）、`freesound_music`（免费）、`music_gen`（ElevenLabs，付费）—— selector 会自动从注册表发现所有可用 provider。**在动用 `music_gen` 之前先默认用 `pixabay_music`。** | 可选的辅助素材制作 |
| Playbook | 当前生效的风格 playbook | 品牌与排版一致性 |

## 流程

### 1. 优先处理源素材精选

从这些开始：

- 源素材精选片段，
- 静图，
- 标题卡背景，
- 任何已获批的、用户提供的音乐或环境声铺底。

它们是主要材料。其余一切都是辅助。

若 `proposal_packet.metadata.motion_required = true`，那么真正的运动素材或生成的视频片段是**必需**的。在这种情况下：

- 静图只能作为参考材料，或作为更大运动合成中的衬底元素，
- 静图不得替代计划中的运动镜头，
- 除非用户明确批准做成动态分镜，否则静图先导片不是可接受的兜底。

### 1b. 样片预览（避免浪费花费）

批量生成辅助素材之前，每种昂贵的生成类型先出一个样本给用户看：

1. **生成插入镜头样本**（若使用 `image_selector` 或 `video_selector`）：生成一个有代表性的视觉。在批量之前确认它与源素材相衬。
2. **音乐样本**（先试 `pixabay_music` —— 免费、可按情绪/BPM 检索；提示音和环境声退回到 `freesound_music`；只有当检索类工具满足不了 brief 时才动用 `music_gen`）：取样或获取一小段。确认情绪与能量与节拍方案吻合。

若 `motion_required = true`，那个有代表性的视觉必须是**视频片段**样本，而不是静图样本。

若被否决，调整参数重试（最多 3 轮）。未获批准之前不要批量生成。

在生成样片之前，明确告诉用户将使用哪条生成路径：

- 工具，
- provider，
- 模型或变体，
- 生成模式，
- 为什么选它。

若那条路径失败了，先停下来问，再去尝试另一个 provider、模型或生成模式。

### 2. 只在必要处生成辅助素材

可选的生成素材应当填补明确的空缺：

- 缺失的过渡 b-roll，
- 概念驱动的插入镜头，
- 质感或氛围卡，
- 简单的质感运动背景。

对要求有运动的任务，生成镜头优先用 `video_selector`。`image_selector` 可以支撑外观开发、概念画面或内嵌的设计层，但它本身满足不了运动要求。

### 3. 准备一份真正的音频方案

存下：

- 选定的音乐曲目或提示词，
- 环境声层，
- 冲击音或转场音，
- 若有对白或旁白，还要有字幕资源。

### 4. 用元数据记录授权与意图

推荐的元数据键：

- `source_selects`
- `music_plan`
- `ambience_plan`
- `title_assets`
- `generated_support_assets`
- `rights_notes`

### 生成提示词的前后自评

> 在把提示词发给任何图像或视频生成工具之前，跑一遍仿照 CHAI 监督循环（《Building a Precise Video Language with Human-AI Oversight》，arXiv 2604.21718v2）的三步自评。成本很小（不额外调用工具）；收益很大（避免白白生成）。对电影感而言，这在**主画面提示词**上最重要 —— 一帧糟糕的主画面会毁掉整件作品，而主画面又是重新生成代价最高的镜头。
>
> **第 1 步 —— 预写。** 按你今天的写法把提示词写出来。不要过度打磨；目标是一份完整的初稿。
>
> **第 2 步 —— 批判。** 用五要素检查清单（Subject / Subject Motion / Scene / Spatial Framing / Camera）给初稿打分。对每个要素：
> - 它写明了吗？若没有，这个省略是刻意的（例如"无主体 —— 风景镜头"）还是疏漏？
> - 易混淆的术语是否已消歧？（dolly vs zoom、pan vs truck、bird's-eye vs aerial、fisheye vs barrel、full shot vs close-up）
> - 情绪形容词（"epic"、"moody"、"cinematic"）是否已被其视觉成因替换（低调光、缓慢推近、变形镜头光晕、深重阴影）？
> - 对多镜头提示词和身份锚定的主画面：身份是否在各镜头间逐字锚定？
>
> **第 3 步 —— 改写。** 补齐缺失的要素、修正易混淆术语、替换主观措辞后重写。改写后的版本才是发给生成工具的那一版。
>
> 把（初稿、批判、改写）三元组记入素材元数据以便追溯。这与 CHAI 的工作流一致，并留下可供 reviewer 审计的记录。

### 5. 质量门

- 源素材与辅助素材被清晰区分，
- 生成的插入镜头数量有限且有目的，
- 音频方案与节拍图吻合，
- 每个被引用的文件都真实存在，
- 若要求有运动，素材集中确实包含了以运动为主的那些节拍所需的视频片段。

### 生产中途的事实核验

若你在素材生成过程中遇到不确定之处：
- 用 `web_search` 核实对象的视觉准确性（例如：这栋建筑实际上长什么样？）
- 在生成插画之前用 `web_search` 找参考图
- 在 decision log 中记录核验：`category="visual_accuracy_check"`

视觉准确性很重要。若脚本提到某个具体的地点、人物或物件，
先核实它实际长什么样，再去生成图像。不要依赖
AI 模型的训练数据 —— 它可能是错的或过时的。

## 常见陷阱

- 在证明源素材剪辑成立之前就先去生成额外镜头。
- 把音乐当成单一循环，而不是一个感知节拍的元素。
- 忘了给用户提供的素材写授权或来源备注。
- 因为某个 provider 或渲染器失败了，就悄悄从视频片段降级到静图。
- 用户已经批准了某条生成路径之后，又悄悄更换 provider 或模型。


## 当你不知道该怎么做时

若你遇到一种拿不准的生成技法、provider 行为或提示词范式：

1. **上网检索**当前最佳实践 —— 模型和 API 变动频繁，agent 的训练数据可能已经过时
2. **查 `.agents/skills/`** 中已有的 Layer 3 知识（provider 专属提示词指南、API 范式）
3. **若两者都无济于事**，在 `projects/<project-name>/skills/<name>.md` 写一份项目作用域的技能，记录你学到的东西
4. 在技能中**引用来源 URL**，让知识可追溯
5. 在 decision log 中**记录它**：`category: "capability_extension"`、`subject: "learned technique: <name>"`

这对以下情况尤其重要：
- **视频生成提示词** —— 模型响应的是随版本变化的特定词汇
- **图像模型参数** —— FLUX、GPT Image、Imagen 的最优设置各不相同且在演进
- **音频 provider 的怪癖** —— 音色克隆、音乐生成和 TTS 各有其模型专属的最佳实践
- **Remotion 组件范式** —— 随框架演进会出现新的合成技法

不要依赖过时的知识。拿不准就先检索。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
