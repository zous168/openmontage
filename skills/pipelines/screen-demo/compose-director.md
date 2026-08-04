# 合成导演 —— Screen Demo 管线

## 何时使用

渲染最终的屏幕演示输出。质量标准很简单：UI 必须可读，节奏必须显得是有意为之，成片必须与规划好的平台形态相符。

## 运行时路由（强制的第一步）

先读 `edit_decisions.render_runtime`。屏幕演示的合成会依据演示形态使用三类不同运行时：

- **`render_runtime="remotion"` 且使用 `TerminalScene`** —— 合成型终端/CLI/安装流程的首选路径。见 `.agents/skills/synthetic-screen-recording/`。
- **`render_runtime="remotion"`**（其他场景）—— 用于「屏幕录制 + 动画叠加层」的混合形态。
- **`render_runtime="hyperframes"`** —— 用于自定义的合成 HTML UI 演示，这类场景 CSS + GSAP 能自然地表达 UI。读 `skills/core/hyperframes.md`。渲染之前 `hyperframes lint` 和 `hyperframes validate` 必须都通过。
- **`render_runtime="ffmpeg"`** —— 用于真实屏幕录制的简单裁切/拼接，不做合成。

在运行时之间静默替换属于 CRITICAL 级治理违规。若被锁定的运行时不可用，按 AGENT_GUIDE.md 上报，然后再谈替代。

**把 `proposal_packet` 传给 `video_compose.execute()`**，这样工具就能直接确认：提案阶段锁定的运行时与 edit_decisions 中所写的一致。不传它，工具内的替换检查会被跳过，你就完全依赖 reviewer 技能去发现漂移。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 要渲染什么 |
| 工具 | `video_compose`、`audio_mixer`、`video_trimmer` | 渲染能力 |
| Playbook | 当前生效的风格 playbook | 质量目标 |

## 流程

### 1. 先为可读性而渲染

优先选最简单且可靠的渲染链：

- 裁切并调整源素材速度，
- 合成叠加层与字幕，
- 只在需要的程度上混音，
- 用适合文字密集内容的码率编码。

### 2. 务实地选择输出形态

| 平台 | 画幅比 | 分辨率 | 备注 |
|----------|--------------|------------|-------|
| YouTube / 文档 | `16:9` | 1920x1080 或更高 | 密集 UI 最稳妥的默认值 |
| LinkedIn 信息流 | `1:1` | 1080x1080 | 当竖屏太挤时的好折中 |
| Shorts / Reels / TikTok | `9:16` | 1080x1920 | 仅当裁切方案确实可读时才用 |

若源素材是 4K 且文字很小，在可行的情况下保留更高分辨率。

### 3. 按正确顺序合成

1. 施加裁切与变速，
2. 施加裁切构图策略，
3. 摆放遮罩与叠加层，
4. 烧录字幕，
5. 混音，
6. 用保护文字的设置编码。

使用锐利的缩放算法，避免激进压缩。编码质量一下滑，屏幕文字是观众最先注意到的东西。

### 4. 让音频保持诚实

- 保住原始语音的清晰度，
- 不要过度压缩，
- 把加速片段里无用的噪声静音或简化，
- 音乐要节制使用，甚至可以完全不用。

### 5. 验证每一个输出

**文件检查：**
- [ ] 输出文件存在，且是合法的 MP4 容器
- [ ] 时长与有效目标的偏差在 +/-5% 以内
- [ ] 分辨率与选定档位相符

**画面抽查：**
- [ ] 在抽样帧上文字锐利可读
- [ ] 裁切转场足够平滑，能跟得上
- [ ] 标注叠加层出现与消失都干净
- [ ] 模糊遮罩完整覆盖敏感数据
- [ ] 没有黑帧或时序抖动
- [ ] 字幕没有压在关键 UI 之上

**音频抽查：**
- [ ] 旁白/口播清晰、音量稳定
- [ ] 若用了音乐，它没有与语音争抢
- [ ] 变速边界处没有明显的音频瑕疵
- [ ] 没有削波或失真

把重要发现记录到：

- `render_report.verification_notes`
- `render_report.warnings`
- `render_report.metadata.variant_notes`

## 常见陷阱

- 渲染出技术上确实导出了、实际上根本读不清的 `9:16` 版本。
- 用通用的低码率社交默认值来编码屏幕文字。
- 让装饰性背景或留白把可用 UI 面积压得太小。
