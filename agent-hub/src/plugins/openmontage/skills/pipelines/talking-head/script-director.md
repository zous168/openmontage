# 脚本导演 —— Talking Head 管线

## 何时使用

你手上有一份 brief 和一段口播原始素材。你的工作是转写这段素材，并把它结构化成一份带时间戳分段的 script artifact。

与 explainer 管线（从零写脚本）不同，你是在**提取并结构化已有的语音**。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/script.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["idea"]["brief"]` | 内容语境 |
| 工具 | `transcriber`（WhisperX） | 带时间戳的语音转文字 |

## 流程

### 第 1 步：转写

用 transcriber 工具拿到词级时间戳：
- 模型：追求最佳质量用 `large-v3`，追求速度用 `base`
- 打开词级对齐，以获得精确时序
- 记下语言检测结果

### 第 2 步：切分成 section

把转写按逻辑分组成若干 section：
- 按内容检测话题切换
- 尊重自然停顿（> 1.5 秒静音 = 潜在的段落分界）
- 每个 section 都要有：id、text、start_seconds、end_seconds

### 第 3 步：丰富 Section 元数据

为每个 section 补上：
- 强化提示（叠加层、B-roll 或文字卡可以放在哪儿）
- 说话人备注（从音频中检测到的重音、语速变化）

### 第 4 步：搭建 Script Artifact

把结构化脚本组装起来，包含：
- 总时长（来自转写）
- 全部带时间戳的 section
- 每个 section 的强化提示

### 第 5 步：自评

| 判据 | 问题 |
|-----------|----------|
| **转写准确性** | 词写对了吗？（抽查几个段落） |
| **时间戳准确性** | Section 边界与实际语音对齐吗？ |
| **覆盖度** | 脚本是否覆盖了完整的素材时长？ |

### 第 6 步：提交

对照 schema 校验 script，并通过检查点持久化。

### 生产中途的事实核验

若你在写脚本过程中遇到不确定：
- 用 `web_search` 在把事实性主张写进脚本之前先核验
- 用 `web_search` 找参考图，保证视觉准确性
- 把核验记入 decision log：`category="visual_accuracy_check"`

脚本中的每一条事实性主张都应能追溯到 `research_brief`。
若你提出了调研中没有的主张，就补做调研并补上来源。
不要杜撰统计数字、日期或出处。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
