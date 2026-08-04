# 创意导演 —— Podcast Repurpose 管线

## 何时使用

当源素材是一集播客（纯音频或视频播客），而用户想要片段、社交素材或一版配套长视频处理时，使用本管线。

你的首要职责是判断：基于**实际存在**的源素材，什么是可行的。

## 运行时选择（强制 —— 把约束讲出来，不要静默选定）

锁定 `render_runtime = "remotion"`（音频波形图和合成输出）或 `"ffmpeg"`（纯音频主导的片段导出）。**在 Phase 1 中，HyperFrames 在本管线上不是合法运行时** —— 播客输出依赖 Remotion 的词级字幕栈，而 HyperFrames 尚无对等能力。

按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：把约束呈现给用户 —— "你的机器上有 HyperFrames，但 podcast-repurpose 依赖 Remotion 的字幕烧录，所以这里 remotion 是唯一可行的选择"。记录一条 `render_runtime_selection` 决策，把 hyperframes 标为 `rejected_because: "caption-burn parity deferred on podcast-repurpose"`。

## 参考输入

- `docs/podcast-repurposing-best-practices.md`
- `skills/creative/short-form.md`
- `skills/creative/long-form.md`

## 流程

### 1. 归类源素材

记录源素材模式：

- `audio_only`
- `video_podcast`
- `hybrid`（音频加静图、封面图、嘉宾照片）

同时记录对话形态：

- 独白
- 访谈
- 圆桌
- 叙事 / 精制节目

### 2. 选择与现实相符的交付物

默认交付物应当在现有源素材和工具下可行。

稳妥的选项：

- 短视频亮点片段，
- 音频波形图或字幕主导的片段，
- 语录主导的片段，
- 一个可选的整集配套版式。

除非源视频、品牌素材和可选配图确实存在，否则不要假定能做出高制作水准的整集 YouTube 处理。

### 3. 定一个合理的交付物组合

典型起点：

- `3-5` 条亮点片段
- 若该集有有力的金句，则 `1-3` 条语录主导的素材
- 若源素材撑得住，可选一版长视频配套

### 4. 尊重平台差异

- Shorts、Reels、TikTok 用 `9:16`
- LinkedIn 和更稳妥的信息流再利用用 `1:1`
- YouTube 配套视频用 `16:9`

若源素材是纯音频，就在 brief 中明确写出来。下游阶段不应当去规划根本不存在的、以说话人构图为主的视频。

### 5. 构建 Brief

用 `brief.metadata` 承载更丰富的播客专属契约：

- `source_mode`
- `show_name`
- `episode_title`
- `episode_number`
- `speakers`
- `conversation_format`
- `deliverable_mix`
- `brand_assets_available`
- `full_episode_companion_feasible`

### 6. 质量门

- 交付物组合与实际源素材相符，
- 片段数量对该集时长而言现实，
- brief 写明了视觉将以源素材、语录还是音频波形图为主导，
- 长视频方面的野心已按现有素材缩放到位。

## 常见陷阱

- 把纯音频源和视频播客源当成同一个制作问题。
- 从一集内容薄弱的节目里规划了太多交付物。
- 在没有素材支撑的情况下承诺丰富的整集视觉处理。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
