# 场景导演 —— Podcast Repurpose 管线

## 何时使用

你要根据**实际的**源素材模式，决定每个播客交付物应当长什么样。正是在这里，你避免"虚假的丰富感"，并选择诚实而有效的处理方式。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["script"]["script"]`、`state.artifacts["idea"]["brief"]` | 亮点集合与源素材实况 |
| 工具 | `frame_sampler` | 视频播客源的可选视觉检视 |
| Playbook | 当前生效的风格 playbook | 品牌一致性 |

## 流程

### 1. 为每个交付物挑对处理方式

优先采用忠于源素材的层级：

- 若有视频播客素材，优先使用以说话人为主的场景，
- 若只有音频，就用音频波形图或语录主导的版式，
- 若品牌素材有限，就让视觉体系保持简单且可重复。

### 2. 不要装出复杂度

除非预算和工具支撑得住，否则不要为整集规划没完没了的生成话题配图。一个干净的品牌化配套版式，胜过一个嘈杂、力不从心的伪制作。

### 3. 定义场景族

有用的 schema 场景类型：

- `talking_head` 用于源视频中的说话人镜头
- `text_card` 用于语录卡和章节卡
- `generated` 用于可选的话题配图
- `diagram` 用于讨论确实需要图形的少数情形
- `transition` 用于章节切换

### 4. 用元数据表达版式策略

推荐的 `scene_plan.metadata` 键：

- `deliverable_layouts`
- `speaker_card_rules`
- `quote_card_rules`
- `audiogram_rules`
- `full_episode_companion_rules`

### 5. 规划安全区与署名

每个版式都应当清楚地保住：

- 说话人署名，
- 字幕区域，
- 节目品牌标识，
- 需要时的 CTA 或单集索引区域。

### 6. 质量门

- 每个交付物的处理方式都与实际源素材相符，
- 有源视频时就用它，而不是把它藏在通用图形后面，
- 纯音频类素材在视觉上保持简洁、可读，
- 长视频配套的视觉是可实现的。

## 常见陷阱

- 为纯音频的节目规划以说话人为中心的版式。
- 把每条片段都做成同一个"波形 + Logo"的构图。
- 用生成图形去掩盖剪辑上的弱选择。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
