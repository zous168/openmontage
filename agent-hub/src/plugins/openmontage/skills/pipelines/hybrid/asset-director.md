# 素材导演 —— Hybrid 管线

## 何时使用

本阶段围绕主线剪辑准备辅助套件：字幕、图解、生成的插入镜头、旁白、音乐，以及可复用的叠加层体系。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["idea"]["brief"]` | 辅助需求与变体方案 |
| 工具 | `subtitle_gen`、`tts_selector`、`image_selector`、`video_selector`、`diagram_gen`、`code_snippet`、`music_gen`、`audio_enhance` —— selector 会自动从注册表发现所有可用 provider | 可选的辅助素材制作 |
| Playbook | 当前生效的风格 playbook | 一致性规则 |

## 流程

### 1. 先做共享的辅助素材

从可复用体系开始：

- 字幕处理，
- 下三分之一条或标签体系，
- 数据卡体系，
- CTA 容器，
- 图解风格。

### 1b. 样片预览（避免浪费花费）

批量生成辅助素材之前，每种昂贵的生成类型先出一个样本给用户看：

1. **TTS 样本**（若需要旁白）：生成其中一段。在批量之前确认音色和调性。
2. **图像/视频样本**（若要生成插入镜头）：生成一个有代表性的视觉。在批量之前确认风格与源素材相衬。

若被否决，调整参数重试（最多 3 轮）。未获批准之前不要批量生成。

### 2. 只生成你需要的辅助素材

辅助素材应当填补脚本和场景方案中已识别的需求，而不是可能性上的猜测。

### 3. 保住主线的事实

在元数据中清楚区分哪些素材是：

- 从源素材派生的，
- 用户提供的，
- 录制的，
- 还是生成的。

### 4. 用元数据表达辅助映射

推荐的元数据键：

- `shared_support_assets`
- `scene_asset_index`
- `source_vs_generated_map`
- `variant_assets`

### 5. 质量门

- 辅助素材对应真实的叙事需求，
- 可复用套件已到位，
- 源素材与生成素材被清楚区分，
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

- 主线剪辑还没被验证，就把辅助素材做过头。
- 分不清哪些素材是生成的、哪些是用户提供的。
- 在同一个项目里做出彼此不一致的叠加层体系。


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
