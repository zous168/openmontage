# 合成导演 —— Localization Dub 管线

## 何时使用

渲染本地化输出。质量底线是：可听懂、时序连贯，以及每个语种包都有清晰的版本标注。

## 运行时路由（硬约束 —— 仅 Remotion 或 FFmpeg）

Phase 1 中 HyperFrames 被推迟。`edit_decisions.render_runtime` 必须是 `"remotion"` 或 `"ffmpeg"`。本地化依赖 Remotion 的字幕栈（逐语种字幕烧录）；做带唇形同步的配音时，还依赖 Remotion 的 TalkingHead 管线。Phase 1 中 HyperFrames 对两者都没有对等能力。

- 若 `edit_decisions.render_runtime == "hyperframes"`，停下。重新打开 idea 阶段并把这个约束呈现出来 —— 不要静默改写运行时。
- 按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：管线自身的约束**不能**免掉与用户的对话。把约束呈现给用户，让他们知道 HyperFrames 是存在的但在这里不可行。记录一条 `render_runtime_selection` 决策，把 hyperframes 标为 `rejected_because: "caption + lip-sync parity deferred on localization-dub"`。
- 把 `proposal_packet`/`brief` 传给 `video_compose.execute()`，以便端到端检测运行时切换。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 逐语种的渲染指令 |
| 工具 | `video_compose`、`audio_mixer`、`video_trimmer`、`audio_enhance` | 最终渲染与音频收尾 |
| Playbook | 当前生效的风格 playbook | 字幕摆放与输出质量 |

## 流程

### 1. 逐语种渲染

把每个目标语种当作它自己的一套交付物。文件名和输出目录都要写明确。

### 2. 预留时序调整

要允许：

- 字幕重排，
- 配音音频的时长漂移，
- 更长的 CTA 停留，
- 可选的修剪或遮盖段落。

### 3. 验证每个语种

把重要发现记录在：

- `render_report.verification_notes`
- `render_report.warnings`
- `render_report.metadata.locale_notes`

检查：

- 可听懂程度，
- 字幕是否装得下，
- 明显的同步漂移，
- 版本标注。

### 4. 质量门

- 每个语种的输出都存在，
- 配音与字幕的时序可接受，
- 标签和文件名无歧义，
- 警告被保留下来。

**输出唯一性(硬性)**:
- `render_report.outputs` 不得包含重复产物:同一路径,或相同内容(相同 file_size_bytes + duration_seconds + resolution)只记录一次。
- 重渲染时:用新输出**替换**旧条目,绝不追加(追加会产生重复输出,校验会拦截)。
- 不同运行时/不同内容的变体(如 FFmpeg 版与 Remotion 字幕版**内容确实不同**)可并列记录,但必须内容真实不同。

## 常见陷阱

- 把所有语种当成时序完全一致来渲染。
- 忘了在翻译之后重新检查字幕行长。
- 输出命名把语种或处理模式给藏起来了。
