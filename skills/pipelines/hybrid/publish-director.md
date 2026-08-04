# 发布导演 —— Hybrid 管线

## 何时使用

把混合项目的输出打包，让主剪辑及其衍生版保持有条理，并让源素材/辅助素材的构成保持清晰。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["compose"]["render_report"]`、`state.artifacts["idea"]["brief"]`、`state.artifacts["script"]["script"]` | 最终产出与混合框架 |
| Playbook | 当前生效的风格 playbook | 调性一致性 |

## 流程

### 1. 区分母版与变体

把输出分组为：

- 母版剪辑，
- 短视频衍生版，
- 格式变体，
- 带章节或带语境的变体。

### 2. 在打包中保住源素材的事实

若项目以访谈素材、屏幕录制或产品素材为主心骨，元数据就应当如实反映这一点，而不是把它当成纯生成作品来包装。

### 3. 记录跨输出的备注

推荐的元数据键：

- `master_output`
- `derivative_outputs`
- `source_mix_notes`
- `platform_copy_map`

### 4. 质量门

- 母版与变体标注清晰，
- 元数据与真实的素材构成相符，
- 导出目录按用途组织，
- 这个包不需要人工清理就能用。

## 常见陷阱

- 让人看不出哪个输出是主剪辑。
- 把一个源素材主导的项目包装成通用的生成素材。
- 各变体之间丢失了平台专属的文案和标注。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
