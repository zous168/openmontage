# 合成导演 —— Hybrid 管线

## 何时使用

渲染这个混合项目，让源媒体、辅助图形和音频在所有输出中都保持连贯。

## 运行时路由（强制的第一步）

读 `edit_decisions.render_runtime`。混合类作品通常仍用 Remotion，因为源素材 + React 辅助叠加层能在一次渲染中干净地合成：

- **`render_runtime="remotion"`** —— 默认。源素材通过 `<OffthreadVideo>`，辅助图形作为 React 组件，一次渲染完成。
- **`render_runtime="hyperframes"`** —— 只有当辅助层是 HTML/GSAP 原生（例如动画文字标注、registry blocks）时才选它。源素材仍可通过 `<video class="clip">` 使用，但会失去一部分 Remotion 组件栈。见 `skills/core/hyperframes.md`。
- **`render_runtime="ffmpeg"`** —— 在本管线上很少见；意味着没有生成的辅助层。

静默切换运行时属于 CRITICAL 级的治理违规。替换之前按 AGENT_GUIDE.md 上报阻塞项。

**把 `proposal_packet` 传给 `video_compose.execute()`**，好让工具内的切换检测直接针对提案运行，而不是被标为 `skipped`。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 剪辑逻辑与辅助素材 |
| 工具 | `video_compose`、`audio_mixer`、`video_stitch`、`video_trimmer`、`color_grade`、`audio_enhance` | 最终装配与打磨 |
| Playbook | 当前生效的风格 playbook | 输出一致性 |

## 流程

### 1. 核查源素材与辅助素材的配比

最终渲染看起来仍应当是一支带辅助元素、源素材主导的视频，而不是一堆互不相干体系的拼贴。

### 2. 检查各变体的完整性

对每个输出变体，确认：

- 裁剪安全，
- 文字安全，
- 字幕可读性，
- 音频一致性。

### 3. 让音频保持连贯

源素材对白、旁白、音乐和音效应当感觉像**一次**混音，而不是几层在互相抢位置。

### 4. 使用渲染元数据

推荐的元数据键：

- `variant_outputs`
- `balance_checks`
- `subtitle_checks`
- `audio_notes`

**输出唯一性(硬性)**:
- `render_report.outputs` 不得包含重复产物:同一路径,或相同内容(相同 file_size_bytes + duration_seconds + resolution)只记录一次。
- 重渲染时:用新输出**替换**旧条目,绝不追加(追加会产生重复输出,校验会拦截)。
- 不同运行时/不同内容的变体(如 FFmpeg 版与 Remotion 字幕版**内容确实不同**)可并列记录,但必须内容真实不同。

## 常见陷阱

- 母版剪辑很好，平台变体却坏掉了。
- 辅助图形在竖屏导出中被裁切。
- 源素材段落与生成段落之间响度发生跳变。
