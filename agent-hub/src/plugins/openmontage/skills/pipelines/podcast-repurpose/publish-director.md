# 发布导演 —— Podcast Repurpose 管线

## 何时使用

把播客衍生的片段和配套素材打包，让每一条短视频都指回那一集，而不是变成一块漂流的孤立碎片。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["compose"]["render_report"]`、`state.artifacts["idea"]["brief"]`、`state.artifacts["script"]["script"]` | 产出、源素材实况、章节 |
| Playbook | 当前生效的风格 playbook | 品牌语气 |

## 流程

### 1. 让每条片段都指回那一集

每个短视频素材都应当引用：

- 节目名，
- 单集标题或期号，
- 相关时的嘉宾姓名，
- 完整单集的去处。

### 2. 定制文案

- Shorts / Reels / TikTok：钩子先行、简洁
- LinkedIn：以洞察为主、更有语境
- YouTube 配套：章节丰富、便于检索

### 3. 排定发布顺序

推荐顺序：

1. 最强的宣发片段
2. 次强的洞察片段
3. 语录主导或嘉宾主导的后续片段
4. 其余的辅助片段

### 4. 把互链事实存进元数据

推荐的元数据键：

- `episode_reference`
- `guest_tags`
- `posting_schedule`
- `clip_to_episode_map`

### 5. 质量门

- 每条片段都指回那一集，
- 嘉宾署名正确，
- 文案与平台相匹配，
- 发布顺序反映了片段的真实强弱。

## 常见陷阱

- 发布片段却没有清晰的单集索引。
- 当嘉宾的受众很重要时，却忘了标注或提及嘉宾。
- 在所有平台上复用同一种文案风格。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
