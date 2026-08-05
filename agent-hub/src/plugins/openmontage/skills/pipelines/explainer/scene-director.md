# 场景导演 —— Explainer 管线

## 何时使用

你是一支生成式讲解视频的场景规划者。你手上有一份带时间戳段落和增强提示的 `script` artifact。你的工作是把脚本转化成一份视觉方案：观众在每一刻看到什么、需要创作哪些素材、场景之间如何转场。

正是在这里，文字变成画面。好脚本配上糟糕的场景方案，产出的是一支让人困惑的视频。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["script"]["script"]`、`state.artifacts["proposal"]["proposal_packet"]` | 脚本段落与提案包 |
| Playbook | 当前生效的风格 playbook | 视觉语言、转场、运动规则 |
| Layer 3 | `.agents/skills/flux-best-practices/`、`.agents/skills/beautiful-mermaid/`、`.agents/skills/manim-composer/` | 图像生成、图表、动画知识 |

## 流程

### 第 1 步：分析脚本

读每一段。对每一段记下：
- 正在解释什么概念？
- 脚本作者埋了哪些增强提示？
- 情绪节拍是什么？（好奇、揭示、强调、幽默、收束）
- 有多少时间可用？（end_seconds - start_seconds）

### 第 2 步：调研视觉路数

**用网络检索**为这个题材找视觉技法：

1. **顶尖创作者是怎么可视化它的？** 检索 YouTube 封面、博客图解、大会幻灯片。
2. **哪些视觉隐喻有效？** 有些概念有广为人知的视觉表示（例如神经网络画成节点图、加密画成锁/钥匙）。用它们 —— 观众一眼就认得。
3. **什么是新鲜的？** 有没有还没人试过的视觉路数？一个新鲜的可视化能让讲解视频令人难忘。
4. **什么是可行的？** 把你的野心与可用工具对齐：`image_selector`（静态图像）、`diagram_gen`（Mermaid 流程图/时序图）、`code_snippet`（语法高亮代码）、Remotion（动态图形、文字动画）、Manim（数学动画）。

若你遇到现有技能都覆盖不了的可视化需求，就用 **Skill Creator**（`skills/meta/skill-creator.md`）创建一个新技能。

### 第 3 步：拆解成场景

**视频生成单元（对使用 `video_selector` 的 `generated` / `broll` 而言是强制的）：**

读 `meta.json` → `production_inputs.video_gen_clip_duration_seconds`（Backlot 项目设置「单次生视频时长」）。未设置时默认 **10 秒**；典型区间 **10–15 秒**。

- **一个分镜场景 = 一次视频生成 API 调用**，按这个设置来定尺寸 —— **不是**一个脚本段落一个场景，也**不是**参考视频里一个快切节拍一个场景。
- 用 `lib/video_gen_units.py` 切分时间线：`总时长 ÷ 片段时长` → N 个约为片段长度的场景（最后一个可以更短）。
- 把多个脚本段落和内部参考节拍打包放进每个场景的 `description` / `metadata.edit_internal_beats` **里面**。字幕时序在 edit 阶段仍然遵循 `script.json` 的段落。
- 每个场景的 `required_assets` 应当请求 **`type: "video"`**，提示词要覆盖整个片段时长。

**Reference-driven 项目（存在 `video_analysis_brief.json`）：**

当 `state.artifacts["reference_analysis"]["video_analysis_brief"]` 存在（或磁盘上有 `artifacts/video_analysis_brief.json`）时，**不要另行发明泛泛的英文视频提示词**。逆向推导出的提示词就是事实来源。

对每一个生成单元 `[start_seconds, end_seconds)`：

1. 调用 `lib.generation_spec.prompt_for_time_range(brief, start_seconds, end_seconds, establish_dna=(start_seconds == 0))`。
2. 把返回的 UGC 六段式字符串写进每个 `type: "video"`、`source: "generate"` 素材的 `required_assets[].description`。
3. 场景中给剪辑人看的 `description` 保持中文；**交给 provider 的提示词放在 `required_assets[].description`**。
4. 设置 `metadata.reference_prompt_source`，记录提示词是由 `video_analysis_brief.generation` + 过滤后的 `beats[]` 拼装而来。
5. 第一个片段（`start_seconds == 0`）：`establish_dna=True` —— 完整 DNA 锁 + 环境。
6. 后续片段（`start_seconds > 0`）：`establish_dna=False` —— 提示词必须以 `[INHERIT DNA LOCK]` 开头并附上延续说明。

**不要**把逆向提示词只推给 asset-director —— scene_plan 就必须携带它们，这样人工复看分镜时才能看到真实的生成规格。

同一规则适用于图片：I2V keyframe 之外的生成图片，其最终提示词同样以 `required_assets[].description` 为准；keyframe 图片提示词由 `lib.reference_scene_plan.sync_asset_manifest_prompts` 从场景可执行 video prompt 同步。

把每一个**生成单元**转换成一个视觉场景（不是每个脚本段落一个）。

```json
{
  "id": "scene-3",
  "type": "diagram",
  "description": "Mermaid flowchart showing query → encode → vector search → rank → return results. Nodes appear one by one as narrator describes each step.",
  "start_seconds": 15,
  "end_seconds": 22,
  "script_section_id": "s3",
  "framing": "full-screen diagram, centered",
  "movement": "progressive reveal left-to-right",
  "transition_in": "fade",
  "transition_out": "dissolve",
  "overlay_notes": "Label each node as it appears",
  "required_assets": [
    {
      "type": "diagram",
      "description": "Mermaid flowchart: query → encode embedding → vector search (ANN) → rank by cosine similarity → return top-k results",
      "source": "generate"
    }
  ]
}
```

#### 场景类型及其适用场合

| 类型 | 最适合 | 可用工具 | 时长指引 |
|------|----------|-----------------|-------------------|
| `hero_title` | 开场标题、戏剧化揭示 | Remotion HeroTitle（由主题驱动的标题处理） | 3-5 秒 |
| `stat_card` | 有冲击力的大数字、关键指标 | Remotion StatCard（大数字 + 副标题） | 4-6 秒 |
| `bar_chart` | 类别对比、排名 | Remotion BarChart（生长/滑入/弹出动画） | 5-7 秒 |
| `line_chart` | 趋势、时间序列、增长曲线 | Remotion LineChart（绘制/淡入动画，多序列） | 5-7 秒 |
| `pie_chart` | 占比、构成拆解、分布 | Remotion PieChart（环形模式、中心标签、旋转/展开） | 5-7 秒 |
| `kpi_grid` | 仪表盘、增长指标、一览式数据 | Remotion KPIGrid（2-4 列，滚动/弹出/级联） | 5-7 秒 |
| `comparison` | 前后对比、A/B、对决 | Remotion ComparisonCard（带分隔线的双值） | 4-6 秒 |
| `callout` | 专家引语、提示、警告、重要说明 | Remotion CalloutBox（info/warning/tip/quote 类型） | 4-6 秒 |
| `progress_bar` | 历程可视化、完成度、堆叠指标 | Remotion ProgressBar（填充/脉冲/分步动画） | 4-6 秒 |
| `text_card` | 陈述句、收尾语、关键术语 | Remotion TextCard（居中，弹簧动画） | 3-5 秒 |
| `animation` | 需要运动才能理解的概念（数据流、数学） | Remotion、Manim | 4-10 秒 |
| `diagram` | 流程、架构、关系 | `diagram_gen`（Mermaid）、`image_selector` | 4-8 秒 |
| `generated` | 插画、隐喻、真实世界意象 | `image_selector`（FLUX/GPT Image） | 3-6 秒 |
| `talking_head` | AI 数字人说话（若 HeyGen 可用） | HeyGen 工具 | 5-15 秒 |
| `broll` | 语境、真实案例 | 素材库或生成的画面 | 3-6 秒 |
| `screen_recording` | 代码演示、UI 走查 | 实录或合成 | 5-15 秒 |

**零 key 场景选择：** 当没有图像/视频生成能力时，优先用 `hero_title`、`stat_card`、`bar_chart`、`line_chart`、`pie_chart`、`kpi_grid`、`comparison`、`callout`、`progress_bar` 和 `text_card`。它们完全由 Remotion 组件渲染、零外部依赖；只要你从题材出发去推导颜色、排版和节奏，而不是默认套一套通用仪表盘美学，它们依然可以显得与众不同。

### 第 4 步：应用视觉技法库

以下是讲解视觉中经过验证的范式。在场景描述里直接按名字引用它们：

**图解渐显（Diagram Reveal）**
渐进式搭建一张图解 —— 从空白开始，随着旁白讲到每个部分再加上组件和标签。非常适合架构、流程和系统。
- 工具：Mermaid + Remotion 动画，或 FLUX 生成的图解
- 示例："展示向量数据库架构。旁白说到 'embeddings' 时加上编码器节点。说到 'search' 时加上索引。"

**类比可视化（Analogy Visualization）**
把抽象概念与它的现实类比并排展示。分屏或左右并列。
- 工具：两侧都用 `image_selector`
- 示例："左：带圆点的真实向量空间。右：按主题排列的图书馆书架。"

**数据卡冲击（Stat Card Punch）**
全屏数字配冲击动画（放大、轻微回弹）。使用 `stat_card` 类型，背景和强调色按本片的识别系统来选。停留 4-5 秒。
- 工具：Remotion StatCard 组件
- 示例：stat="1ms"，subtitle="vs 500ms with traditional search"，accentColor="<theme_accent>"

**数据仪表盘序列（Data Dashboard Sequence）**
一系列数据可视化场景，用数字讲一个故事。先给 KPI 总览，再下钻到具体图表。用 section_title 叠加层把相关数据分组。这个范式零外部工具即可实现。
- 工具：Remotion 图表组件（bar_chart、line_chart、pie_chart、kpi_grid）
- 示例：kpi_grid（4 个关键数字）→ bar_chart（拆解）→ line_chart（趋势）→ pie_chart（分布）
- 背景处理从视觉识别中选：戏剧化/技术类题材用深色，亲和/教育类用浅色，题材需要时用带质感或暖调的。

**前后分屏（Before/After Split）**
用 `comparison` 类型先展示问题再展示解法。对比卡把双值并排展示，并带入场动画。
- 工具：Remotion ComparisonCard 组件
- 示例：leftLabel="Before"、leftValue="500ms"、rightLabel="After"、rightValue="1ms"

**时间线推进（Timeline Progression）**
从左到右或自上而下的序列，展示演进或流程步骤。旁白讲到哪一步，哪一步就出现。
- 工具：带动画元素的 Remotion，或 Mermaid 时间线
- 示例："1990：关键词检索 → 2010：语义检索 → 2020：向量数据库 → 2024：多模态检索"

**推近与聚焦（Zoom and Focus）**
先给系统的全景，再推进到某个具体组件做细讲。营造空间语境。
- 工具：在生成图像上做缩放动画的 Remotion
- 示例："展示完整系统架构。推进到 'embedding model' 组件。"

**代码走查（Code Walkthrough）**
展示带语法高亮的代码。旁白讲到哪几行就高亮哪几行。可以做打字动画或渐进显现。
- 工具：`code_snippet` 工具 + Remotion
- 示例："Python 代码：`results = collection.query(embedding, n_results=5)`。旁白说到 'vector' 时高亮 `embedding` 参数。"

### 第 4b 步：按时长预算撰写旁白

若视频包含旁白，脚本**必须**写成能装进视频时长。

**时长预算公式：**
1. 从场景时序算出视频总时长（最后一个 cut 的 `out_seconds`）。
2. 把旁白目标定在视频时长的 **85-90%**，给片头/片尾留出呼吸空间。
3. 词数预算：带自然停顿的纪实风格取**每秒 2.0-2.5 词**；有活力/快节奏的演绎取**每秒 2.5-3.0 词**。
4. 示例：53 秒视频 → 目标 45-48 秒旁白 → 最多 90-120 词（纪实）或 112-144 词（有活力）。

**逐场景词数预算：**
- 按每个场景的时长按比例分配词数。
- 一个 5 秒的场景约 10-12 词。一个 6 秒的场景约 12-15 词。
- 场景转场之间留 0.5-1 秒静默，给画面留呼吸空间。

**校验（TTS 生成之前必做）：**
- [ ] 总词数在目标时长的预算之内
- [ ] 没有任何单个场景的旁白超出它的时间槽
- [ ] 开场和收尾场景的旁白简短（让画面呼吸）

**TTS 生成之后：**
- TTS 工具会返回 `audio_duration_seconds` —— 把它与视频时长比对。
- 若旁白比视频长出 1 秒以上，要么删减脚本重新生成，要么延长视频的收尾场景。
- 渲染之前始终跑 `composition_validator`，以自动捕获不匹配。

### 第 4c 步：五要素场景方案检查清单

> 每个场景都必须写明全部五个要素。对图解、图表和 Remotion 原生场景，"Subject" 可以映射到被推到前景的数据元素，"Camera" 可以标为 N/A —— 但必须**明确写出来**（例如 `"camera": "N/A — Remotion native scene, no virtual camera"`）。静默省略是最常见的失败模式，会产出不可预测的模型输出、脆弱的提示词，以及反复的 reviewer 打回。
>
> 1. **Subject** —— 类型 + 关键视觉属性；若有多个，如何区分。对图解/图表场景，这是被推到前景的数据元素（那个节点、那根柱子、那个被高亮的 KPI）。对生成图像，则是被描绘的人/物/概念。
> 2. **Subject Motion** —— 按时间顺序的动作；对动画图解而言，是节点/边/数值出现或变化的顺序。
> 3. **Scene** —— 叠加层（单独列！）+ POV + 环境 + 时段 + 场景动态。对 Remotion 场景，"环境"映射到背景处理 + 主题。
> 4. **Spatial Framing** —— 景别 + 画面内位置 + 纵深（前景/中景/背景）+ 相对相机高度；以及它们如何**变化**。对静态 Remotion 场景，记录版式栅格 + 哪个元素占据视觉中心。
> 5. **Camera** —— 播放速度 → 镜头畸变 → 高度 → 角度 → 对焦/景深 → 稳定度 → 运动。Remotion 原生场景标 N/A；`generated`/`broll`/`image_animation` 场景要写完整。
>
> 原语词汇表见 `skills/creative/video-gen-prompting.md`。

> **最终视频提示词（reference-driven）。** 当存在 `video_analysis_brief.json` 时，
> `type: "video"` 的 `required_assets[].description` **就是**可直接交给 provider 的逆向
> 提示词（经由 `lib.generation_spec.prompt_for_time_range`）。给剪辑人看的 `description` 保持
> 中文；不要用泛泛的摘要替换素材提示词。
>
> **最终视频提示词（explainer 默认）。** 对非参考类项目，场景方案的字段是
> **输入**，而不是发给 `video_selector` 的字符串。asset-director 会在生成时拼装完整的
> 逐镜头提示词（见 `asset-director.md` 的六段式表格 + 附录 A）。不要在这里用
> 跨场景的简写（"same as above"）—— 要提供足够的结构化节拍供 assets 展开。
>
> **最终图片提示词。** `required_assets[]` 中 `type: "image"`、`source: "generate"` 的
> **`description` 即最终发送给图片模型的提示词原文** —— 与视频约定一致（`metadata.image_prompts`
> 为早期临时约定，已废弃，勿再写入）。asset-director 不得把该 description 改写成通用摘要再发送；
> 如运行中确需改写，改写后的原文必须回写 `required_assets[].description` 并在 asset manifest
> 记录发送原文。

> **叠加层提醒。** 叠加层（标题、字幕、HUD、水印、边框图形、下三分之一条、section_title 条、stat_reveal 标签、hero_title 叠加、provider chip）**不**属于场景的 前景/中景/背景 纵深轴。在场景元数据中单独列出（`overlays: [...]`），写明内容和位置。绝不要把叠加层描述成"在前景里" —— 那会同时误导下游工具和任何重新分析输出的视频理解模型。

### 第 5 步：对照 Playbook 校验

风格 playbook 约束着你的视觉选择：

| Playbook 字段 | 对场景的影响 |
|----------------|-------------|
| `visual_language.color_palette` | 所有生成图像和图解都必须使用这些颜色 |
| `visual_language.composition` | 构图规则（三分法、居中等） |
| `motion.transitions` | 允许的转场类型（例如 `gentle-fade`、`soft-dissolve`） |
| `motion.animation_style` | 动画的感觉（例如 `ease-in-out, organic curves`） |
| `motion.pacing_rules` | 最短停留时间（例如"定场镜头至少保持 2 秒"） |
| `asset_generation.image_prompt_prefix` | 提炼成一个简短的视觉锚点；不要逐字粘贴进所有提示词 |
| `asset_generation.consistency_anchors` | 所有图像之间必须保持一致的东西（配色、光照、风格） |

**提交前检查清单：**
- [ ] 每个场景使用的转场都与 playbook 兼容
- [ ] 所有 required_asset 描述都包含来自 playbook 的风格提示
- [ ] 没有场景违反节奏规则（最短/最长时长）
- [ ] 图像描述引用的是本片真实的视觉识别，而不只是一个预设名字

### 第 6 步：核查覆盖度与多样性

**覆盖度检查：**
- [ ] 场景覆盖脚本的完整时长（第一个场景从 0 秒开始，最后一个场景在总时长处结束）
- [ ] 每个脚本段落至少有一个对应场景
- [ ] 场景之间没有超过 1 秒的空缺（除非是有意的节拍）
- [ ] 脚本中的所有增强提示都被某个场景或 required_asset 处理了

**多样性检查：**
- [ ] 同一类型的场景连续不超过 3 个
- [ ] 视频中至少使用了 3 种不同的场景类型
- [ ] 视觉节奏在高信息量场景（图解、动画）与呼吸空间（文字卡、生成图像）之间交替

**可行性检查：**
- [ ] 每个 `source: "generate"` 的 `required_asset` 都能用现有工具实现
- [ ] 图解描述具体到足以生成 Mermaid 语法
- [ ] 图像描述具体到足以做 FLUX/GPT Image 的提示词工程
- [ ] 没有场景需要工具注册表里没有的工具

### 第 7 步：自评

打分（1-5）：

| 标准 | 问题 |
|-----------|----------|
| **视觉叙事** | 每个场景是在推进理解，还是只在装饰？ |
| **与脚本对齐** | 每个场景是否与旁白此刻所说的内容相符？ |
| **技法多样性** | 你是否用了多种视觉技法，而不只是一种？ |
| **Playbook 忠实度** | 是否每个场景看起来都属于同一支视频？ |
| **素材可行性** | 每个 required_asset 真的能用现有工具生成吗？ |
| **节奏** | 视觉律动感觉自然吗？高信息量场景与呼吸空间平衡吗？ |

若任何一项低于 3 分，就修订。

### 第 8 步：提交

调用 `handle_explainer_scene_plan(state, {"scene_plan": scene_plan_json})` 做校验并持久化。

## 常见陷阱

- **一段一个场景**：脚本段落常常覆盖多个概念。一个 10 秒的段落可能需要 2-3 个视觉场景，才不至于停滞乏味。
- **无视增强提示**：脚本作者已经在 `enhancement_cues` 里埋了视觉线索。不要无视它们 —— 它们代表作者的视觉意图。
- **过于野心的动画**："数据中心的写实 3D 穿行"用当前工具做不出来。保持可实现。
- **没有转场策略**：随机转场会显得混乱。始终如一地使用 playbook 的转场规则。把特殊转场留给话题切换。
- **含糊的 required_assets**："一张关于数据库的图"对提示词工程毫无用处。"向量数据库的等距插画，embedding 向量漂浮在 3D 空间中，使用 playbook 的蓝绿配色"才可执行。
- **预设式思维**：一份只写着"做成 flat-motion-graphics"的场景方案是不够的。规划者必须写明是什么让**这支**视频的动态图形与众不同。
- **给动态概念用静态场景**：若旁白在描述一个过程或转变，画面就应当动起来。用动画或渐进显现，而不是一张静图。
- **给带确切文字的 CTA/收尾画面使用 `generated` 类型**：AI 图像模型会幻觉文字 —— 错误的商号、拼错的词、错的电话号码。任何需要逐字准确文字的场景（CTA、商家信息、联系方式、法务），都**必须**是 `type: "text_card"`，让 Remotion 精确渲染文字。绝不要为文字准确性重要的场景规划 `generated` 图像。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
