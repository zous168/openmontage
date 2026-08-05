# 合成导演 —— Avatar Spokesperson 管线

## 何时使用

渲染最终的代言人输出。底线很简单：出镜人必须看起来稳定、语音必须清晰、字幕或辅助卡不能把画面挤满。

## 运行时路由（硬约束 —— 仅 Remotion）

Phase 1 中 HyperFrames 被推迟。`edit_decisions.render_runtime` 必须是 `"remotion"`。本管线依赖 Remotion 的 `TalkingHead` composition 和 `remotion_caption_burn` —— Phase 1 中两者都没有 HyperFrames 的对等能力。

- 若 `edit_decisions.render_runtime == "hyperframes"`，停下。重新打开 idea 阶段并把这个约束呈现出来。静默改写属于违反治理规则。
- 按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：锁定 remotion **不是**跳过与用户对话的借口。用户有权知道 HyperFrames 作为运行时是存在的，以及它为什么不适用于 avatar-spokesperson。记录一条 `render_runtime_selection` 决策，把 hyperframes 标为 `rejected_because: "TalkingHead + caption parity deferred on avatar-spokesperson"`。
- 把 `proposal_packet`/`brief` 传给 `video_compose.execute()`，以便工具内部检测运行时切换。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 要渲染什么 |
| 工具 | `video_compose`、`audio_mixer`、`video_stitch`、`audio_enhance` | 渲染与音频收尾 |
| Playbook | 当前生效的风格 playbook | 排版与版式规则 |

## 流程

### 1. 先渲染主剪辑

先做一版有力的母版，再做衍生版。合成：

- 出镜人视频，
- 字幕，
- 下三分之一条，
- CTA 卡，
- 混好的旁白。

### 2. 保持画面干净

在这里，字幕和 CTA 的位置比花哨的转场更重要。让脸部和嘴部区域不被遮挡。

### 3. 验证口部时序与音频

若数字人路径用了唇形同步或音频驱动的口播人像，检查：

- 口部时序，
- 面部伪影，
- 长段落上的漂移，
- 音频清晰度。

### 4. 验证每一个输出

把重要发现记录在：

- `render_report.verification_notes`
- `render_report.warnings`
- `render_report.metadata.variant_notes`

### 5. 质量门

- 输出文件合法，
- 语音清晰，
- 字幕保持可读，
- 出镜人在视觉上保持稳定。

**输出唯一性(硬性)**:
- `render_report.outputs` 不得包含重复产物:同一路径,或相同内容(相同 file_size_bytes + duration_seconds + resolution)只记录一次。
- 重渲染时:用新输出**替换**旧条目,绝不追加(追加会产生重复输出,校验会拦截)。
- 不同运行时/不同内容的变体(如 FFmpeg 版与 Remotion 字幕版**内容确实不同**)可并列记录,但必须内容真实不同。

## 常见陷阱

- 让字幕盖住下巴或嘴部区域。
- 没有抽查漂移就交付一段长时长的唇形同步渲染。
- 做出会把出镜人或 CTA 切掉的衍生裁剪版本。
