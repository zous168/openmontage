# 场景导演 —— Animation 管线

## 何时使用

你要把脚本转化成一份可行的动画方案。正是这个阶段决定了这个项目最终显得是被设计过的，还是杂乱无章的。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["script"]["script"]`、`state.artifacts["proposal"]["proposal_packet"]` | 节拍图与工具路径 |
| Playbook | 当前生效的风格 playbook | 配色、排版、运动一致性 |

## 流程

### 1. 做一份有动态分镜意识的方案

对每个场景，定义：

- 最先出现什么，
- 什么在变化，
- 什么被保持，
- 场景如何退场。

### 2. 限制转场家族

选定一小组转场语义：

- 硬切，
- 淡化，
- 滑动，
- 形变。

### 3. 让场景类型匹配工具路径

使用：

- `diagram` 场景做结构化讲解，
- `animation` 场景做以运动为先的段落，
- `text_card` 做干净、有冲击力的文案时刻，
- `generated` 只在必要处使用。

**对 `image_animation` 方式（动画/插画风格）：**

每个场景使用 `anime_scene` 类型。规划：

- **每场景图像数**：2-3 张，来自同一套视觉体系、seed 相近，以便做交叉淡化
- **镜头运动**：从 `zoom-in`、`zoom-out`、`pan-left`、`pan-right`、`ken-burns`、`drift-up`、`drift-down`、`parallax`、`static` 中选 —— 逐场景变化以防单调
- **粒子类型**：从 `fireflies`、`petals`、`sparkles`、`mist`、`light-rays` 中选 —— 与场景情绪相匹配
- **光照**：可选的 `lightingFrom`/`lightingTo` 渐变，用于场景内的氛围变化
- **暗角**：`true` 用于电影感构图（默认），`false` 用于明亮/开阔的场景
- **场景时长**：每场景 4-7 秒。更长的场景需要更多图像来保证交叉淡化的变化。

**image_animation 的场景多样性规则：**
- 相邻场景不要用同一种镜头运动
- 暖色与冷色的粒子类型交替使用
- 混用特写与开阔的定场镜头
- 用叠加层（`hero_title`、`section_title`）来增加叙事结构

**JSON prop 名称映射**（在 composition JSON 中使用这些确切字段名）：

| 概念 | JSON 字段 | 示例取值 |
|---------|-----------|----------------|
| 镜头运动 | `animation` | `"zoom-in"`、`"pan-right"`、`"ken-burns"` |
| 粒子效果 | `particles` | `"fireflies"`、`"sparkles"`、`"mist"` |
| 粒子颜色 | `particleColor` | `"#FFE082"` |
| 粒子密度 | `particleCount` | `20`（范围：1-50） |
| 粒子亮度 | `particleIntensity` | `0.5`（范围：0-1） |
| 光照起始 | `lightingFrom` | `"rgba(255,200,100,0.15)"` 或 `"transparent"` |
| 光照结束 | `lightingTo` | `"rgba(255,107,157,0.08)"` 或 `"transparent"` |
| 电影感边缘压暗 | `vignette` | `true` / `false` |
| 场景背景 | `backgroundColor` | 由主题派生的值，例如 `"#0A0A1A"` 或 `"#F6F1E8"` |

参考：`remotion-composer/public/demo-props/mori-no-seishin.json` —— 使用该范式的 6 个场景。
参考：`remotion-composer/public/demo-props/deep-ocean.json` —— 换了配色的 6 个水下场景。

### 4. 用元数据表达时序规则

推荐的元数据键：

- `animatic_rules`
- `transition_rules`
- `hold_rules`
- `tool_path_map`
- `reusable_motifs`

### 5. 五要素场景方案检查清单

> 每个场景都必须写明全部五个要素，**但**侧重会随场景的 `animation_mode` 变化。Manim 及其他图解/程序化场景最关心 **Subject** 和 **Spatial Framing** —— 摄影意义上的 Camera 和 Subject Motion 往往标为 N/A 或映射到抽象等价物。AI 视频 / `image_animation` / `anime_scene` 场景则五个要素都关心，行为上就像电影镜头。把某个要素标为 N/A 是允许的，但必须逐场景写明；静默省略是被禁止的。
>
> 1. **Subject** —— 类型 + 关键视觉属性；对 Manim 而言是被推到前景的那个方程/物体/图像；对 `anime_scene` 而言是聚焦的角色或环境。
> 2. **Subject Motion** —— 对 Manim 而言是 `Create`/`Transform`/`FadeIn` 的先后顺序以及每个动画传达了什么；对 AI 视频而言是按时间顺序的动作与互动。
> 3. **Scene** —— 叠加层（单独列！）+ POV + 环境 + 时段 + 场景动态。对 Manim 而言，"环境"就是画布背景 + 坐标轴风格；对 `anime_scene` 而言是环境 + 光照渐变。
> 4. **Spatial Framing** —— 景别 + 画面内位置 + 纵深（前景/中景/背景）+ 相对相机高度；以及这些如何**变化**。Manim 关心版式栅格 + 元素位置；AI 视频关心完整的电影构图。
> 5. **Camera** —— 播放速度 → 镜头畸变 → 高度 → 角度 → 对焦/景深 → 稳定度 → 运动。对 Manim 和纯动态图形，除非使用了虚拟镜头运动（`MoveCamera`、`self.frame`），否则默认 N/A。对 `anime_scene` 和 AI 视频，要写完整。
>
> 把这一点与场景元数据中的 `animation_mode` 挂钩：一个把 Camera 写得满满当当的 Manim 场景是过度规格化；一个省略了 Camera 的 AI 视频场景是规格不足。原语词汇表见 `skills/creative/video-gen-prompting.md`。

> **叠加层提醒。** 叠加层（标题、字幕、HUD、水印、边框图形、下三分之一条、`hero_title`、`section_title`、`provider_chip`）**不**属于场景的 前景/中景/背景 纵深轴。在场景元数据中单独列出（`overlays: [...]`），写明内容和位置。绝不要把叠加层描述成"在前景里" —— 那会同时误导下游工具和任何重新分析输出的视频理解模型。

### 6. 质量门

- 每个场景都有清晰的时序意图，
- 按该场景的 `animation_mode` 满足了五要素检查清单（该 N/A 的地方明确写 N/A），
- 叠加层放在 `overlays:` 下，绝不写进构图描述里，
- 转场体系有限而有意义，
- 工具路径明确，
- 整个序列感觉像是**一套**被设计过的体系。

## 常见陷阱

- 每个场景都冒出一个新的转场点子。
- 规划出没有现实制作路径的场景。
- 给文字密集的场景加了过多动画。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
