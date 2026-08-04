# 创意导演 —— Hybrid 管线

## 何时使用

当项目把真实源媒体与辅助视觉结合起来时使用本管线：访谈加图解、素材加叠加层、屏幕录制加品牌图形，或源素材主导的剪辑加生成插入镜头。

Hybrid 不是一个什么都往里装的筐。你的第一项工作是定义什么保持主体地位。

## 运行时选择（强制 —— 两个运行时都要呈现）

在锁定制作计划之前，与用户一起确定 `render_runtime`。Hybrid 同时支持 Remotion 和 HyperFrames；两者都不是自动默认。遵循 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)" 中的契约：

1. 查询 `video_compose.get_info()["render_engines"]`。若 `remotion` 和 `hyperframes` 都为 `True`，就结合本次 brief 的具体情况把两者呈现给用户：
   - **Remotion** —— 当源素材占主导、辅助层是 React 场景组件（图表、标注框、文字卡）时合适。Remotion 通过 `<OffthreadVideo>` 在一次渲染中把视频片段 + React 叠加层合成起来。
   - **HyperFrames** —— 当辅助层是 HTML/GSAP 原生的（动态标注、registry blocks、排版叠加），而源素材以 `<video class="clip">` 形式嵌入时合适。
2. 推荐其中一个，理由要与主导媒介和辅助层的形态挂钩。
3. 等待用户明确批准。
4. 把这个选择记入 `decision_log`，作为一条 `render_runtime_selection` 决策，`options_considered` 中包含**两个**运行时。

若两个运行时都可用，而 `render_runtime_selection` 决策的 `options_considered` 里只有一个，这是 CRITICAL 级的 reviewer 发现。

## 参考输入

- `docs/hybrid-video-best-practices.md`
- `skills/creative/storytelling.md`
- `skills/creative/video-editing.md`

## 流程

### 1. 选定主导媒介

挑出叙事的主心骨：

- `talking_head`
- `broll_footage`
- `screen_recording`
- `still_sequence`
- `narration_led_graphics`

### 2. 定义辅助层

可能的辅助层：

- 字幕，
- 图解，
- 代码视觉，
- 数据卡，
- 生成的插入镜头，
- 旁白，
- 音乐。

每个辅助层都应当解决一个具体问题，而不只是给时间线做装饰。

### 3. 确定交付物组合

常见输出：

- 主剪辑，
- 竖屏精简版，
- 方形精简版，
- 带章节的版本，
- 广告变体。

### 4. 构建 Brief

推荐的元数据键：

- `anchor_medium`
- `source_inventory`
- `support_layers`
- `deliverable_mix`
- `missing_capabilities`
- `fallback_policy`

### 5. 质量门

- 主导媒介明确，
- 辅助层有正当理由，
- 交付物组合与源素材清单相称，
- 缺失的能力尽早暴露。

## 常见陷阱

- 什么都叫 hybrid，却没有定义一个主导媒介。
- 还没弄清源素材就开始规划辅助层。
- 把可选的生成插入镜头当成板上钉钉的东西。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
