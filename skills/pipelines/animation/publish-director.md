# 发布导演 —— Animation 管线

## 何时使用

为这支动画做打包，让元数据、封面构想和平台构图能真实反映本项目的视觉体系。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["compose"]["render_report"]`、`state.artifacts["proposal"]["proposal_packet"]`、`state.artifacts["research"]["research_brief"]`、`state.artifacts["script"]["script"]` | 最终产出与题材框定 |
| Playbook | 当前生效的风格 playbook | 视觉命名的一致性 |

## 流程

### 1. 让打包匹配动画模式

例如：

- 图解密集的视频应当显得结构清晰、易读，
- 动态排版作品应当围绕有力的文案来打包，
- 插画式动画应当围绕主视觉图像来打包。

### 2. 保留视觉体系的事实

存进 `publish_log.metadata`：

- `animation_mode`
- `hero_frame_notes`
- `thumbnail_concept`
- `platform_notes`

当项目封面来源是 **文生图（text_to_image）** 时，`export_bundle` 会通过 `image_selector`
自动生成 `exports/thumbnails/thumbnail.png`，所用提示词由封面钩子文案、风格说明、标题、
playbook 和交付物画幅比拼装而成。provider 失败时，
它会退回到自动截帧。

### 3. 质量门

- 元数据符合实际的动画模式，
- 封面构想与最终的视觉体系相符，
- 导出物按用途和平台做了标注，
- 这个包不需要额外的手工加工就能用。

## 常见陷阱

- 写出无视动画风格的泛泛元数据。
- 做出与最终画面毫无关系的封面构想。
- 混放各平台变体却不做清晰标注。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
