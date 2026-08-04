# 素材导演 —— Localization Dub 管线

## 何时使用

本阶段产出本地化素材包：译制字幕文件、配音音频、可选的唇形同步渲染，以及最终输出所需的任何语种专属替换内容。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["idea"]["brief"]` | 语种方案与转写稿包 |
| 工具 | `tts_selector`、`subtitle_gen`、`lip_sync`、`audio_enhance` —— `tts_selector` 会自动从注册表发现所有可用的 TTS provider | 配音音频、字幕与可选的唇形同步制作 |
| Playbook | 当前生效的风格 playbook | 字幕与替换文字的规则 |

## 流程

### 1. 先产出字幕素材

为每个语种创建字幕包。这样即便配音音频生成或唇形同步被卡住，也有一个可供审校的兜底。

### 1b. 主场景样片（强制）

批量生成素材之前：
1. 找出主场景（视频的视觉高点）
2. 为该场景生成**一段**目标语言的配音音频样本
3. 呈现它："这是最重要那个场景的配音方向。这符合你的设想吗？我会按这个风格生成其余的。"
4. 在进入批量生成之前等待批准

这可以避免代价最高的错误：朝着用户并不喜欢的方向生成了 10 多个配音素材。

### 2. 逐语种生成配音音频

使用已获批的译制脚本包，而不是机器翻译的原始输出。记录每种语言使用了哪个音色或哪条合成路径。

### 3. 把唇形同步当作可选项

只为真正需要的场景和语种生成唇形同步素材。若工具路径被卡住，就把它记录下来，并保住配音音频这条路。

### 4. 用元数据记录本地化事实

推荐的元数据键：

- `subtitle_assets_by_language`
- `dub_audio_assets_by_language`
- `lip_sync_assets_by_language`
- `voice_map`
- `pronunciation_warnings`
- `blocked_assets`

### 5. 质量门

- 字幕素材存在，
- 计划中的配音输出都有对应的配音音频素材，
- 唇形同步明确保持为可选项，
- 每个被引用的文件都真实存在。

### 生产中途的事实核验

若你在素材生成过程中遇到不确定之处：
- 用 `web_search` 核实对象的视觉准确性（例如：这栋建筑实际上长什么样？）
- 在生成插画之前用 `web_search` 找参考图
- 在 decision log 中记录核验：`category="visual_accuracy_check"`

视觉准确性很重要。若脚本提到某个具体的地点、人物或物件，
先核实它实际长什么样，再去生成图像。不要依赖
AI 模型的训练数据 —— 它可能是错的或过时的。

## 常见陷阱

- 在翻译审校定稿之前就生成配音音频。
- 把唇形同步当成每个语种都必须做的事。
- 没有记录哪个语种素材对应哪个音色和哪套字幕。


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
