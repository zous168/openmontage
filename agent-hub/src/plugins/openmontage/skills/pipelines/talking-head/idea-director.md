# 创意导演 —— Talking Head 管线

## 何时使用

你正在启动一个口播（talking-head）视频项目。你手上有一段人物讲话的原始素材。你的工作是分析这段素材、弄清它包含什么，并搭建一份 brief，捕捉内容的本质与制作目标。

与 explainer 管线（从一个题目起步）不同，你是从**已有素材**起步。Brief 记录的是：你在用什么素材，以及最终视频应当是什么样。

## 运行时选择（强制 —— 把约束呈现出来，不要静默替用户选）

锁定 `render_runtime = "remotion"`（首选 —— 使用 `TalkingHead` + `remotion_caption_burn`）或 `"ffmpeg"`（用于源素材拼接、不做合成）。**Phase 1 中 HyperFrames 在本管线上不是合法运行时** —— TalkingHead 合成与词级字幕烧录目前还没有 HyperFrames 的对等能力。

按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：**不要**静默默认到 remotion。告诉用户："HyperFrames 是可用的，但 talking-head 依赖 Remotion 的 TalkingHead 合成，所以 remotion 是唯一可行的合成选择（或用 ffmpeg 做一个原始粗剪）—— 可以这样继续吗？"记录一条 `render_runtime_selection` 决策，把 hyperframes 列为被拒选项（`rejected_because: "TalkingHead + caption parity deferred on talking-head"`）。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/brief.schema.json` | Artifact 校验 |
| 输入 | 原始素材文件路径 | 源素材 |
| 工具 | `ffprobe`（经由 shell） | 素材元数据提取 |

## 流程

### 第 1 步：检视素材

用 ffprobe 提取元数据：
- 时长
- 分辨率
- 帧率
- 音频声道与编码
- 文件大小

这告诉你手上是什么 —— 质量、长度、格式。

### 第 2 步：快速内容评估

在脑中把素材过一遍（或者在 frame_sampler 可用时抽帧看）：
- 这个人在讲什么？
- 原始素材有多长？
- 目标平台是什么？（不清楚就问用户）
- 音频好吗？有背景噪声吗？

### 第 3 步：搭建 Brief

创建一份 brief artifact，记录：
- **标题**：基于素材内容的描述性标题
- **钩子**：凭什么值得看？
- **要点**：素材中涵盖的主要话题
- **语气**：匹配说话人的真实语气（随意、专业、教学）
- **风格**：从素材、说话人的人设、受众和平台推导叠加层/观感方向。`clean-professional` 是一个安全兜底，而不是所有 talking-head brief 的默认答案。
- **目标平台**：这支视频将发布到哪里
- **目标时长**：可能短于原始素材（做过裁切）

### 第 4 步：自评

| 判据 | 问题 |
|-----------|----------|
| **准确性** | Brief 是否如实反映了素材里实际有的东西？ |
| **完整性** | 所有必填的 brief 字段都有了吗？ |
| **平台匹配** | 目标平台适合这类内容吗？ |

### 第 5 步：提交

对照 schema 校验 brief，并通过检查点持久化。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
