# 提案导演 —— Character Animation 管线

## 目标

呈现角色动画概念，并对本地骨骼运动、复用、成本和运行时选择保持诚实。

## 提案必备要素

每个方案都必须包含：

- 角色与其定位，
- 视觉风格，
- 动作复杂度，
- 骨骼复用策略，
- 样片方案，
- 音频架构，
- 音乐方案，
- 渲染运行时选项，
- 成本估算，
- 如实的局限说明。

## 运行时选择

在推荐运行时之前，先读 `skills/meta/animation-runtime-selector.md`。

当 Remotion 和 HyperFrames 都可用时：

- Remotion：当最终 composition 需要确定性的 React 渲染视频、字幕、
  音频、场景 JSON 和最终 MP4 治理时最合适。
- HyperFrames：当角色场景大量使用 HTML/SVG/GSAP、并能从
  Web 原生编写、lint、validate 和 registry blocks 中受益时最合适。
- FFmpeg：只做后期处理。不要把 FFmpeg 选作角色表演的主运行时。

在推荐其中一个之前，把 Remotion 和 HyperFrames 都呈现给用户。
把考虑过的备选记入 decision log，category 为
`render_runtime_selection`，包括 `hyperframes` 被接受或被否决的原因。
在锁定 `render_runtime` 之前等待用户批准。

## 样片优先规则

在全量生产之前，先提出一段 10-15 秒的样片，包含：

- 一个主角色，
- 一次表情变化，
- 一个身体动作，
- 一种镜头/背景处理，
- 若相关，一个音频/音乐提示。

在这段样片获批之前，不要批量生成所有素材。

## 成本要诚实

本地绑骨在渲染时很便宜，但在编写复杂度上很昂贵。
把这个差别报告清楚：

- 素材生成成本，
- TTS/音乐成本，
- 本地渲染成本，
- 人工复杂度风险。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
