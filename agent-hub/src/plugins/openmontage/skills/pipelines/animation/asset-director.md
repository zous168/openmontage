# 素材导演 —— Animation 管线

## 何时使用

本阶段准备真正的动画原料：旁白、图解、数学渲染、运动背景、代码视觉，以及可复用的字体或版式体系。

## 动画编写 —— 选哪个运行时

在编写动态图形组件之前，读 **`skills/meta/animation-runtime-selector.md`** 了解运行时路由。Animation 是最有可能用得上 GSAP 插件的管线 —— Logo 形变、曲线镜头路径、动态排版、FLIP 过渡。

Animation 管线常见需求的快速路由：

| 运动类型 | 推荐做法 |
|---|---|
| 两个形状之间的 SVG Logo 形变 | GSAP MorphSVG —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| SVG 上的线条绘制 / 描边显现 | GSAP DrawSVG —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 物体沿曲线路径运动 | GSAP MotionPath —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 逐字符 / 逐词的标题揭示 | GSAP SplitText —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 自定义贝塞尔或弹性缓动 | GSAP CustomEase —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 元素在版式之间飞行（FLIP） | GSAP Flip —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 跨多个元素的多步序列 | GSAP timeline —— 读 `.agents/skills/gsap-timeline/SKILL.md` |
| 粒子叠加 / 背景运动 | Remotion 的 `ParticleOverlay` 组件（已存在） |
| 数学动画（函数图像、方程） | Manim —— 读 `.agents/skills/manim-composer`、`.agents/skills/manimce-best-practices` |
| 吉卜力 / 动画风格的静图驱动场景 | Remotion 的 `AnimeScene` 组件 + FLUX 图像生成 |

**Remotion 确定性规则：** 在 Remotion 组件内每一次使用 GSAP，都必须由 `useCurrentFrame()` 驱动时间线进度 —— 绝不用 `requestAnimationFrame`。范式示例见 `.agents/skills/gsap-react/SKILL.md`。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["proposal"]["proposal_packet"]` | 工具路径与节拍图 |
| 工具 | `tts_selector`、`image_selector`、`video_selector`、`math_animate`、`diagram_gen`、`code_snippet`、`music_gen` —— selector 会自动从注册表发现所有可用 provider | 素材生产选项 |
| Playbook | 当前生效的风格 playbook | 视觉一致性 |

## 流程

### 1. 从确定性素材开始

优先选择方差最低而又有用的路径：

- 结构化图解优先用 `diagram_gen`，而非通用图像生成，
- 代码场景用 `code_snippet`，
- 真正的数学运动用 `math_animate`，
- 已提供的美术素材优先于重新生成。

### 1b. 样片预览（避免浪费花费）

批量生成素材之前，每种昂贵类型先出一个样本给用户看：

1. **TTS 样本**（若以旁白为主）：若存在 `script.voice_performance.sample_section_id` 就生成它；否则挑情绪或节奏变化最强的那一段。在批量之前确认音色、语速、停顿、重音和调性。
2. **视觉样本**：生成一个有代表性的场景视觉（图解、插画或运动背景）。在批量生成其余部分之前确认风格与质量。

若被否决，调整参数重试（最多 3 轮）。未获批准之前不要批量生成。

### 1c. 基于图像的动画（方式 A）的多图生成

当 `animation_mode == "image_animation"` 时，每个场景需要 **2-3 张图**来做交叉淡化动画。这正是让静图看起来在动的原因。

**图像生成工作流：**

1. **定义一套视觉体系** —— 一组在整个项目所有图像中复用的锚点。它保证视觉连贯，同时不会把每个镜头压平成同一条提示词。把它存为可复用的元数据。
   ```
   示例："Hand-painted nature fantasy, warm moss-and-amber palette,
   soft diffused light, painterly foliage textures, gentle wonder."
   ```
   然后逐场景适配：
   - 场景 1：开阔的森林山谷定场，雾气，日出
   - 场景 2：角色近景节拍，灯笼光晕，飘散的孢子
   - 场景 3：抽象的魔法能量揭示，更亮的强调色对比

2. **管理 seed** —— 每个场景的 A/B 变体使用相邻的 seed 值（例如 seed 100 和 101）。同一条提示词 + 不同 seed = 相同构图带细微差异 = 自然的交叉淡化运动。

3. **先生成一张测试图** —— 先渲染一个场景，确认这套视觉体系在 1920×1080 下效果不错，再批量生成全部图像。

4. **批量生成** —— 生成所有场景图像。磁盘上已存在的跳过（幂等）。

5. **Composition JSON** —— 每个场景 `type: "anime_scene"`，带 `images: ["path/a.png", "path/b.png"]`，外加镜头运动、粒子类型和光照配置。

**成本估算：** 每场景 2-3 张 × 每张 $0.03-0.13，视 provider 而定。

**参考：** 已验证的批量生成范式见 `projects/mori-no-seishin/generate_images.py`。

6. **复制到 Remotion 的 public 目录** —— 生成全部图像之后，把它们复制到 `remotion-composer/public/<project-name>/`，好让 Remotion 能通过 `staticFile()` 访问。composition JSON 中的图像路径是相对于这个目录的：
   ```
   remotion-composer/public/<project-name>/scene1-a.png   ← Remotion 从这里读
   remotion-composer/public/<project-name>/ambient-music.mp3  ← 音乐也一样
   ```
   **若跳过这一步，渲染会因文件缺失而失败。** 这是新项目渲染失败的头号原因。

### 2. 构建可复用体系

只做一次：

- 排版处理，
- 下三分之一条或标签样式，
- 反复出现的母题素材，
- 背景容器。

### 3. 旁白是可选的，但方案必须写明

若项目以旁白为主，就生成或取得旁白。先读
`skills/meta/voice-performance-director.md`，然后在构建 TTS 请求时应用 `script.voice_performance`
和每一段的 `delivery_cues`。若存在 `provider_text` 就使用它，把提示映射到 provider 的控制项上，
并把实际应用的设置记录在每个旁白素材上。若项目是以文字为主或以音乐为主，就在元数据中
清楚说明。

### 4. 用元数据表达可行性事实

推荐的元数据键：

- `tool_path_map`
- `reusable_assets`
- `narration_assets`
- `voice_performance`：样本获批路径、provider 设置，以及演绎提示是否被应用
- `scene_asset_index`
- `blocked_assets`

### 5. 质量门

- 每个场景的素材路径都明确，
- 可复用素材确实被复用了，
- 缺失的能力被如实呈现，
- 每个被引用的文件都真实存在，
- 以旁白为主的素材应用了已获批的配音表演设置。

### 生产中途的事实核验

若你在素材生成过程中遇到不确定之处：
- 用 `web_search` 核实对象的视觉准确性（例如：这栋建筑实际上长什么样？）
- 在生成插画之前用 `web_search` 找参考图
- 在 decision log 中记录核验：`category="visual_accuracy_check"`

视觉准确性很重要。若脚本提到某个具体的地点、人物或物件，
先核实它实际长什么样，再去生成图像。不要依赖
AI 模型的训练数据 —— 它可能是错的或过时的。

## 常见陷阱

- 在确定性素材更合适的地方使用高方差的生成。
- 反复重建同一套标题或标签体系。
- 隐瞒失败的素材路径而不报告。
- 把 TTS 当成裸的文字转音频。以旁白为主的动画需要把停顿、
  重音和语速提示从脚本一路带进生成的音频里。
- 把"一致性"理解成"每次都用同一条提示词"。好的动画既保持一个可辨识的世界，又让每个节拍显得新鲜。


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
