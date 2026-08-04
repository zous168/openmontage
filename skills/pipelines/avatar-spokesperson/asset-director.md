# 素材导演 —— Avatar Spokesperson 管线

## 何时使用

本阶段准备真正的代言人原料：旁白、数字人或唇形同步素材、字幕资源、品牌背景，以及完成剪辑所需的最少辅助图形。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["idea"]["brief"]` | 出镜人方案与旁白需求 |
| 工具 | `talking_head`、`lip_sync`、`tts_selector`、`subtitle_gen`、`image_selector`、`audio_enhance` —— selector 会自动从注册表发现所有可用 provider | 数字人、旁白与辅助素材选项 |
| Playbook | 当前生效的风格 playbook | 背景、字体与字幕规则 |

## 流程

### 1. 锁定数字人生成路径

只用一条主路径，并把它清楚记录下来：

- 由静态图像加音频驱动的 `talking_head`，
- 由已有出镜人底板加新音频驱动的 `lip_sync`，
- 若数字人渲染是在当前运行时之外制作的，则为外部提供的成品。

不要隐瞒受阻的数字人路径。把它记录下来。

### 1b. 样片预览（避免浪费花费）

批量生成素材之前，每种昂贵类型先出一个样本给用户看：

1. **TTS 样本**（若要生成旁白）：生成其中一段。在批量生成其余部分之前确认音色、语速和人设。
2. **数字人样本**（若使用 `talking_head`）：生成一小段测试片。在投入完整生成之前确认数字人质量可接受。

若被否决，调整参数重试（最多 3 轮）。未获批准之前不要批量生成。

### 2. 先解决旁白，再做辅助图形

代言视频依赖语音。先确定旁白是：

- 用户提供的，
- TTS 生成的，
- 还是已经内嵌在出镜人底板里的。

若旁白缺失且没有任何 TTS 工具可用，就把项目标记为受阻，而不是假装这个阶段成功了。

### 3. 构建最小辅助套件

只准备场景方案真正需要的东西：

- 字幕文件，
- 一套下三分之一条体系，
- CTA 卡，
- 背景或底板素材，
- 可选的静图或产品辅助图。

### 4. 用元数据表达能力事实

推荐的元数据键：

- `avatar_generation_path`
- `narration_assets`
- `subtitle_assets`
- `background_assets`
- `scene_asset_index`
- `blocked_assets`

### 5. 质量门

- 数字人路径明确，
- 旁白与数字人素材相互吻合，
- 辅助图形保持精简，
- 每个被引用的文件都真实存在。

## 无数字人路径

当 EP 触发了"旁白配图形"的转向（`talking_head` 和 `lip_sync` 都不可用）时，完全跳过数字人生成，改为产出一套以图形驱动的素材包：

### 要产出什么：
1. **旁白音频** —— 通过 `tts_selector`（强制；若连 TTS 也没有，就把项目标记为受阻）。
2. **场景视觉** —— 通过 `image_selector` 或 `video_selector`。每个场景一个主视觉，用来强化口播的论点（图解、插画、产品图或素材片段）。
3. **字幕文件** —— 与标准路径相同。
4. **文字卡** —— 关键点叠加、数据卡、CTA 结尾卡。
5. **背景** —— 与 playbook 匹配的一致家族。

### 要跳过什么：
- 不调用 `talking_head` 或 `lip_sync`。
- 没有出镜人构图元数据。
- `avatar_generation_path` 应设为 `"none — narration-over-graphics pivot"`。

### 这条路径的元数据：
- `avatar_generation_path`：`"narration_over_graphics"`
- `pivot_reason`：为什么选择无数字人路径
- 其余元数据键保持不变。

### 生产中途的事实核验

若你在素材生成过程中遇到不确定之处：
- 用 `web_search` 核实对象的视觉准确性（例如：这栋建筑实际上长什么样？）
- 在生成插画之前用 `web_search` 找参考图
- 在 decision log 中记录核验：`category="visual_accuracy_check"`

视觉准确性很重要。若脚本提到某个具体的地点、人物或物件，
先核实它实际长什么样，再去生成图像。不要依赖
AI 模型的训练数据 —— 它可能是错的或过时的。

## 常见陷阱

- 在旁白路径还没解决时就先做装饰性素材。
- 在一支简单的代言视频里混用多种数字人生成策略。
- 核心的出镜人素材还只是假设，就把这个阶段标记为完成。
- （无数字人路径）生成与旁白毫无关联的填充画面 —— 每张图都必须强化口播的论点。


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
