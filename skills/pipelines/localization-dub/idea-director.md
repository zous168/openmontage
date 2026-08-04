# 创意导演 —— Localization Dub 管线

## 何时使用

当用户手上有一支源视频、并希望得到译制交付物时使用本管线：一种或多种目标语言的字幕、配音音频，或本地化视频。

你的首要职责是定义实际需要的是哪一类本地化，因为纯字幕、配音音频和唇形同步译制是三件不同的活。

## 运行时选择（强制 —— 把约束讲出来，不要静默选定）

锁定 `render_runtime = "remotion"`（带逐语种字幕烧录/唇形同步的合成交付物）或 `"ffmpeg"`（在源片上纯烧字幕、不做合成）。**在 Phase 1 中，HyperFrames 在本管线上不是合法运行时** —— 本地化依赖 Remotion 的字幕栈，而带唇形同步的配音还依赖 Remotion 的 TalkingHead 管线。

按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：**不要**静默默认成 remotion。告诉用户："HyperFrames 是可用的，但 localization-dub 依赖 Remotion 的字幕 + TalkingHead 对等能力，而这在 Phase 1 还没有 —— 所以 remotion 是唯一可行的选择"。记录一条 `render_runtime_selection` 决策，把 hyperframes 标为 `rejected_because: "caption + lip-sync parity deferred on localization-dub"`。

## 参考输入

- `docs/localization-dubbing-best-practices.md`
- `skills/creative/short-form.md`
- `skills/creative/long-form.md`

## 流程

### 1. 定义本地化范围

记录：

- 源语种，
- 目标语种，
- 审校负责人，
- 是否需要术语表或法务审校，
- 用户需要的是字幕、配音音频、唇形同步，还是它们的组合。

### 2. 归类源素材

记录源素材模式：

- `single_speaker`
- `multi_speaker`
- `voiceover_led`
- `speaker_led_on_camera`

同时记录屏幕文字或动态图形是否需要人工替换或遮盖。

### 3. 选择与现实相符的交付物

可能的交付物：

- 仅字幕包，
- 不带唇形同步的配音视频，
- 唇形同步的本地化视频，
- 逐语种的导出包。

### 4. 构建 Brief

推荐的元数据键：

- `source_language`
- `target_languages`
- `deliverable_mode_map`
- `glossary_terms`
- `protected_terms`
- `review_requirements`
- `timing_risks`

### 5. 质量门

- 本地化范围明确，
- 目标产出现实，
- 术语表和审校要求已记录，
- 由说话人数量或可见口型带来的风险上升已被指出。

## 常见陷阱

- 把每一个翻译请求都当成配音请求。
- 把术语表管控拖到音频生成之后才处理。
- 在视觉条件很差的源素材上承诺唇形同步却不作提醒。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
