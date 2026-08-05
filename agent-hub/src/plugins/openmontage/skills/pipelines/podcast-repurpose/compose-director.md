# 合成导演 —— Podcast Repurpose 管线

## 何时使用

以音频保真度为最高优先级来渲染播客衍生的输出。画面要**支撑**语音，而不是与之争夺注意力。

## 运行时路由（硬约束 —— 仅 Remotion 或 FFmpeg）

Phase 1 中 HyperFrames 被推迟。`edit_decisions.render_runtime` 必须是 `"remotion"`（音频波形图、合成输出）或 `"ffmpeg"`（纯音频主导的片段导出）。HyperFrames 的字幕烧录对等能力被推迟，而播客输出依赖 Remotion 的词级字幕栈。

- 若 `edit_decisions.render_runtime == "hyperframes"`，停下。重新打开 idea 阶段并把这个约束呈现给用户。绝不要静默改写运行时。
- 按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：告诉用户 HyperFrames 是存在的，以及它在本管线上为什么不可行，而不是静默锁定 remotion。记录一条 `render_runtime_selection` 决策，把 hyperframes 标为 `rejected_because: "caption-burn parity deferred on podcast-repurpose"`。
- 把 `proposal_packet`/`brief` 传给 `video_compose.execute()`，以便端到端检测运行时切换。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 输出方案与素材路径 |
| 工具 | `video_compose`、`audio_mixer` | 渲染与混音控制 |
| Playbook | 当前生效的风格 playbook | 品牌一致性 |

## 流程

### 1. 先渲染价值最高的输出

优先顺序：

1. 短亮点片段
2. 语录主导的片段
3. 可选的长视频配套

这样最可发布的素材能最先到手。

### 2. 保住音频质量

- 避免不必要的重新编码，
- 让语音保持可懂、稳定，
- 音乐要用得节制，且只在不抢戏时使用，
- 渲染之后验证字幕同步。

### 3. 尊重平台形态

- 短视频社交用 `9:16`
- 语录主导或适合信息流的片段用 `1:1`
- 长视频 YouTube 配套输出用 `16:9`

### 4. 验证每个交付物

- 时长正确，
- 画幅比正确，
- 字幕可读，
- 说话人署名准确，
- 音频稳定，
- 品牌处理一致。

### 5. 使用 Render Report 元数据

推荐的元数据键：

- `deliverable_groups`
- `audio_notes`
- `subtitle_checks`
- `failed_outputs`

**输出唯一性(硬性)**:
- `render_report.outputs` 不得包含重复产物:同一路径,或相同内容(相同 file_size_bytes + duration_seconds + resolution)只记录一次。
- 重渲染时:用新输出**替换**旧条目,绝不追加(追加会产生重复输出,校验会拦截)。
- 不同运行时/不同内容的变体(如 FFmpeg 版与 Remotion 字幕版**内容确实不同**)可并列记录,但必须内容真实不同。

## 常见陷阱

- 让视觉处理拖累了音频质量。
- 先渲染整集配套，反而拖延了最重要的那些片段。
- 忘了：一条简洁、可读的片段，胜过一条技术复杂却让人困惑的片段。
