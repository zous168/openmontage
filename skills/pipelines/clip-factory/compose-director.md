# 合成导演 —— Clip Factory 管线

## 何时使用

逐条渲染每个片段和每个平台变体。这里重要的是一致性、批处理的容错，以及对部分失败的清晰报告。

## 运行时路由（硬约束 —— 仅 Remotion 或 FFmpeg）

本管线在 HyperFrames 的接入排期中被推迟到 Phase 1 之后。`edit_decisions.render_runtime` 必须是 `"remotion"`（默认）或 `"ffmpeg"`（不做合成的纯拼接类片段任务）。HyperFrames 在这里**不是**合法运行时 —— clip-factory 依赖 Remotion 的词级字幕烧录，而 HyperFrames 的字幕对等能力仍是待办工作。

- 若 `edit_decisions.render_runtime == "hyperframes"`，停下。重新打开 idea 阶段，让用户看到真实的约束，并用一条把 `hyperframes` 记为 `rejected_because: "caption-burn parity deferred on clip-factory"` 的 `render_runtime_selection` 决策锁定 `remotion`。
- 按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：这个约束**不是**跳过对话的借口。用户仍然有权知道 HyperFrames 是存在的，以及它在这里为什么不可行。
- 把 `proposal_packet`/`brief` 传给 `video_compose.execute()`，让工具内的运行时切换检查能端到端跑起来。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 片段剪辑与素材 |
| 工具 | `video_trimmer`、`video_compose`、`audio_mixer`、`color_grade` | 渲染管线 |
| Media profile | `lib/media_profiles.py` | 平台目标 |

## 流程

### 1. 把每个输出当作独立任务

一条片段发三个平台就是三个渲染任务。显式命名并逐个追踪。

### 2. 复用可共享的部分

- 尽可能共享音频混音，
- 共享字幕样式，
- 共享叠加层素材，
- 若源素材需要，共享调色。

### 3. 柔性失败

若某条片段或某个平台变体失败：

- 清楚地记录它，
- 继续跑完这一批的其余部分，
- 不要阻塞已经成功的导出。

### 4. 验证每一个输出

对每次渲染：

- 时长正确，
- 分辨率/画幅比正确，
- 开头没有黑帧，
- 钩子按时出现，
- 字幕渲染正确，
- 音频存在且一致。

### 5. 使用 Render Report 元数据

推荐的元数据键：

- `job_index`
- `failed_jobs`
- `shared_intermediates`
- `platform_groupings`

**输出唯一性(硬性)**:
- `render_report.outputs` 不得包含重复产物:同一路径,或相同内容(相同 file_size_bytes + duration_seconds + resolution)只记录一次。
- 重渲染时:用新输出**替换**旧条目,绝不追加(追加会产生重复输出,校验会拦截)。
- 不同运行时/不同内容的变体(如 FFmpeg 版与 Remotion 字幕版**内容确实不同**)可并列记录,但必须内容真实不同。

## 常见陷阱

- 任务本可并行，却毫无理由地串行渲染。
- 因为一条片段失败就停掉整批。
- 让某个平台变体悄悄用错了构图或字幕区域。
