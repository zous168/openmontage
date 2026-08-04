# 发布导演 —— Clip Factory 管线

## 何时使用

本阶段把这一批片段打包成一份分发方案。目标不只是导出文件，而是一台可用的内容引擎。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["compose"]["render_report"]`、`state.artifacts["idea"]["brief"]`、`state.artifacts["script"]["script"]` | 产出、排序与目标 |
| Playbook | 当前生效的风格 playbook | 品牌语气 |

## 流程

### 1. 用最强的那条片段打头阵

不要按时间顺序排期。按排名排期。

第一条发布的片段通常应当是：

- 钩子最强的，
- 独立成立性最干净的，
- 最贴合这一批目标的。

### 2. 按平台定制文案

每个平台都需要自己的语气与包装：

- TikTok / Reels：直接、快、钩子先行
- Shorts：可被检索、有关键词意识
- LinkedIn：以洞察为主，更专业
- X：短、有力、适合表达观点

### 3. 干净地打包这一批

按平台分组，并附上可直接粘贴的文本资源，而不只是视频文件。

### 4. 保留批次事实

存进 `publish_log.metadata`：

- `clip_catalog`
- `posting_order`
- `platform_copy_map`
- `schedule_notes`

### 5. 质量门

- 最强的片段领跑投放，
- 文案因平台而异，
- 导出目录不需要额外清理就能用，
- 批次目录清晰地把排名、文件路径和发布意图关联了起来。

## 常见陷阱

- 把整批片段在同一天全发出去。
- 到处用同一条文案。
- 渲染完成之后就把排名/顺序的逻辑弄丢了。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
