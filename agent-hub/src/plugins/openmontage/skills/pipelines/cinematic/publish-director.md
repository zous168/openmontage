# 发布导演 —— Cinematic 管线

## 何时使用

把这件电影感作品及其各种精简版打包，让主版本保持清晰、分发意图一目了然。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["compose"]["render_report"]`、`state.artifacts["proposal"]["proposal_packet"]`、`state.artifacts["research"]["research_brief"]`、`state.artifacts["script"]["script"]` | 最终产出与节拍图 |
| Playbook | 当前生效的风格 playbook | 调性与命名的一致性 |

## 流程

### 1. 区分主版本与衍生版

典型交付物：

- 主预告片或品牌片，
- 先导剪辑，
- 社交精简版，
- 定帧海报或封面构想。

### 2. 让元数据匹配调性

打包应当反映真实的情绪：

- 戏剧化，
- 高端，
- 神秘，
- 沉思，
- 紧迫。

### 3. 保留剪辑上的事实

存进 `publish_log.metadata`：

- `hero_output`
- `derivative_outputs`
- `poster_frame_notes`
- `distribution_notes`

### 4. 质量门

- 主导出物被清晰标出，
- 衍生导出物按用途标注，
- 元数据与调性相符，
- 这个包不需要人工清理就能用。

## 常见陷阱

- 先导片与主版本导出混在一起却没有清晰命名。
- 写出无视情绪的泛泛元数据。
- 把所有精简版当成可以互换的。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
