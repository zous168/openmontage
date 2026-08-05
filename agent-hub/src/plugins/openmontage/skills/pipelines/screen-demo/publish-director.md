# 发布导演 —— Screen Demo 管线

## 何时使用

把完成的演示打包，让用户能快速发布，并让元数据如实反映真实的任务、结果和涉及的工具。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["compose"]["render_report"]`、`state.artifacts["idea"]["brief"]`、`state.artifacts["script"]["script"]` | 视频、brief 与各 section |
| Playbook | 当前生效的风格 playbook | 封面与文案语气 |

## 流程

### 1. 构建可被搜索到的元数据

屏幕演示的标题，在组合了以下三者时效果最好：

- 任务，
- 工具，
- 结果。

好的模式：

- `How to deploy on Vercel from Next.js`
- `Fix CORS in React + Express`
- `Set up GitHub Actions for Python tests`

关键词的来源：

- 软件名，
- 框架，
- 命令，
- 精确的报错文本，
- 结果类词汇，例如 `deploy`、`fix`、`connect`、`publish`、`ship`。

### 2. 用章节标记做导航

把脚本的各 section 作为章节标记和打包要点的基础。一个好的屏幕演示包，能让用户还没按下播放，就已经可以速览整个工作流。

### 3. 封面策略

若需要一个封面概念，它应当展示：

- 结果状态，而不是通用的初始界面，
- 可辨认的工具界面，
- 2-4 个字的价值文案。

把该概念存进 `publish_log.metadata.thumbnail_concepts`。

### 4. 按平台打包

准备好：

- 视频文件，
- 标题与描述/文案，
- 相关时提供章节标记，
- 关键词列表，
- 封面概念备注。

对开发者或产品演示类内容，还要打包：

- 展示过的命令，
- 提到的软件/版本，
- 若是排障演示，还包括报错术语。

### 5. 质量门

- 元数据点名了真实的工具与任务，
- 章节与实际渲染出的流程一致，
- 导出目录干净、可复用，
- 文案是按平台定制的，而不是复制粘贴。

## 常见陷阱

- 用省略了真实软件或任务的通用标题去发布。
- YouTube、LinkedIn 和短视频社交共用同一份文案。
- 只照着脚本做章节标记，却不去核对成片。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
