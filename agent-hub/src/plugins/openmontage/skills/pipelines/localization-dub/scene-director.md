# 场景导演 —— Localization Dub 管线

## 何时使用

规划每个本地化交付物如何处理时序、可见的口型、字幕和屏幕文字。正是在这里，管线决定是保留原剪辑、遮盖口型可见的段落，还是尝试唇形同步。

## 参考输入

- `docs/localization-dubbing-best-practices.md`
- `skills/creative/video-editing.md`

## 流程

### 1. 为每个交付物选定配音模式

从中选一个：

- `subtitle_only`
- `dub_audio_only`
- `lip_synced`
- `hybrid_covered`

`hybrid_covered` 指的是：在口型明显对不上、会分散注意力的段落，用 B-roll、图形或文字来遮盖。

### 2. 映射时序风险

找出因以下原因而可能漂移的场景：

- 语速快，
- 法务文案密集，
- 多说话人，
- 快切，
- 可见的口部特写。

### 3. 记下屏幕语言依赖

记录含有以下内容的场景：

- UI 文字，
- 下三分之一条，
- 标题卡，
- 已烧录的字幕，
- 可能需要替换或遮盖的图表或标签。

### 4. 用元数据规划变体

推荐的元数据键：

- `dub_mode_map`
- `timing_risk_map`
- `on_screen_text_replacement_map`
- `language_variant_notes`

### 5. 质量门

- 每个交付物都有明确的本地化处理方式，
- 时序风险已被映射，
- 唇形同步是有选择地使用的，
- 文字替换的需求没有被隐藏。

## 常见陷阱

- 假定配音音频会严丝合缝地装进源片时序。
- 为每个镜头都选唇形同步，而不是只给值得的那些镜头。
- 把已烧录的文字拖到合成时才想起来。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
