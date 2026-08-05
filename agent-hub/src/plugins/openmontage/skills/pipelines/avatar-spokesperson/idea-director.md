# 创意导演 —— Avatar Spokesperson 管线

## 何时使用

当交付物是一支出镜人主导的数字人视频时使用本管线：代言广告、产品介绍、入职欢迎、内部通讯更新，或任何以讲述者为视觉主心骨的短篇脚本化讲解。

你的第一项工作是如实归类数字人路径 —— 别让人先为一个根本不可能实现的制作方案写好了精致文案。

## 运行时选择（强制 —— 把约束讲出来，不要静默选定）

锁定 `render_runtime = "remotion"`。**在 Phase 1 中，HyperFrames 在本管线上不是合法运行时** —— avatar-spokesperson 依赖 Remotion 的 `TalkingHead` composition 和 `remotion_caption_burn`，而 HyperFrames 对这两者都还没有对等能力。

按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：**不要**静默取默认值。告诉用户："你的机器上有 HyperFrames，但 avatar-spokesperson 依赖 Remotion 的 TalkingHead composition 和字幕烧录，所以这里 remotion 是唯一可行的运行时 —— 可以这样推进吗？" 记录一条 `render_runtime_selection` 决策，把 hyperframes 标为 `rejected_because: "TalkingHead + caption parity deferred on avatar-spokesperson"`。

## 参考输入

- `docs/avatar-spokesperson-best-practices.md`
- `skills/creative/storytelling.md`
- `skills/creative/short-form.md`

## 流程

### 1. 归类数字人路径

记录这个项目实际拥有的生产模式：

- `platform_avatar`
- `photo_talking_head`
- `presenter_plate_lip_sync`

同时记录该数字人是已经存在，还是仍需在当前运行之外去制作。

### 2. 定义信息形态

抓住：

- 受众，
- 核心主张或 CTA，
- 时长目标，
- 平台目标，
- 这支视频是以销售、入职、支持还是公告为导向。

代言视频在只承担**一项**明确任务时效果最好。

### 3. 记录源素材的真实情况

brief 应当明确写出：

- 是否提供了干净的旁白，
- TTS 是否可接受，
- 是否已有品牌背景或叠加层，
- 是否需要字幕，
- 是否预期做多语种变体。

### 4. 构建 Brief

推荐的元数据键：

- `avatar_path`
- `avatar_exists`
- `narration_source`
- `target_audience`
- `cta_type`
- `background_strategy`
- `deliverable_mix`
- `missing_capabilities`

### 5. 质量门

- 数字人路径明确，
- 信息足够聚焦，适合代言人这种形态，
- 缺失的旁白或数字人依赖尽早暴露，
- 交付物与实际的源素材条件相匹配。

## 常见陷阱

- 把一个笼统的"生成视频"请求当成确定性的数字人工作流。
- 在确认数字人和旁白路径之前就写好了 CTA。
- 在主版式还没被验证之前就规划多个画幅比。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
