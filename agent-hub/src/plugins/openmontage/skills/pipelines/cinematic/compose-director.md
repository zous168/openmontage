# 合成导演 —— Cinematic 管线

## 何时使用

渲染这件电影感作品，重点关注调色、音频动态和画面处理。这不是一个通用的导出步骤。

## 运行时路由（强制的第一步）

读 `edit_decisions.render_runtime`。电影感作品路由到：

- **`render_runtime="remotion"`** —— 使用 `CinematicRenderer` 的视频主导预告片的默认项。把视频片段、转场和环境叠加层放在同一次基于 React 的渲染中完成。
- **`render_runtime="hyperframes"`** —— 用于动态标题卡、HTML/GSAP 驱动的预告片，或视觉语法本身就是 HTML/CSS 的发布短片式合成。见 `skills/core/hyperframes.md`。渲染之前 `hyperframes lint` 和 `hyperframes validate` 都必须通过。
- **`render_runtime="ffmpeg"`** —— 简单的源素材拼接，不做合成。

`delivery_promise.motion_required=true` 意味着被锁定的运行时是一项承诺。静默切换到另一个运行时（包括 FFmpeg 的 Ken Burns）属于 CRITICAL 级的治理违规。若锁定的运行时失败了，按 AGENT_GUIDE.md > "Escalate Blockers Explicitly" 上报。

**把 `proposal_packet` 传给 `video_compose.execute()`**，好让工具的 `runtime_swap_detected` 检查能直接与 `proposal_packet.production_plan.render_runtime` 比对。不传的话，这项切换检查在工具内会被跳过，只能靠 reviewer 技能来抓漂移。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 剪辑方案与媒体素材 |
| 工具 | `video_compose`、`audio_mixer`、`video_stitch`、`video_trimmer`、`color_grade`、`audio_enhance` | 渲染与收尾 |
| Playbook | 当前生效的风格 playbook | 收尾的一致性 |

## 流程

### 0. 渲染前先核对硬性要求

若已获批的 brief 或场景方案把运动定为硬性要求，就要确认渲染路径仍然兑现这个承诺。

- 若需要 Remotion 而它不可用或正在失败，立刻停下并把问题抛给用户。
- 不要为一支以运动为主的预告片、先导片或 agent 视频切换到只用 FFmpeg 的静图兜底。
- 除非用户明确批准这种降级，否则不要把作品变成动态分镜。
- 若渲染引擎发生实质变化，在渲染之前告诉用户并解释原因。

**强制的 Remotion preflight（当场景方案包含任何 Remotion 场景类型 —— 标题卡、数据卡、anime/hero_title、片尾标签、叠加层 —— 时，每次渲染前都跑一遍）：**

```bash
python -c "
from plugins.openmontage.tools.tool_registry import registry
registry.discover()
info = registry.get('video_compose').get_info()
print('Render engines:', info.get('render_engines'))
print('Remotion note:', info.get('remotion_note'))
"
```

若 Remotion 不在可用渲染引擎里，停下并按决策沟通契约向用户报告。未经批准，不要替换成保真度更低的渲染路径。

### 1. 有意识地使用画面处理

只有当黑边、24fps 的取向或重度调色确实对作品有帮助时才用。不要因为管线名字里有 cinematic 就套上它们。

### 2. 保住音频动态

混音应当允许：

- 安静的时刻，
- 冲击的时刻，
- 清晰的对白或旁白，
- 受控的音乐涌起。

### 3. 验证最终情绪

检查：

- 开场画面，
- 揭示节拍，
- 最终落地，
- 相关处的字幕可读性。

### 4. 使用渲染元数据

推荐的元数据键：

- `frame_treatment`
- `grade_profile`
- `mix_notes`
- `variant_outputs`

**输出唯一性(硬性)**:
- `render_report.outputs` 不得包含重复产物:同一路径,或相同内容(相同 file_size_bytes + duration_seconds + resolution)只记录一次。
- 重渲染时:用新输出**替换**旧条目,绝不追加(追加会产生重复输出,校验会拦截)。
- 不同运行时/不同内容的变体(如 FFmpeg 版与 Remotion 字幕版**内容确实不同**)可并列记录,但必须内容真实不同。

## 常见陷阱

- 把音频压平，导致作品失去动态。
- 给需要每一个像素的素材加黑边。
- 让调色或锐化损害了人脸或文字。
- 在 Remotion 渲染受阻时，静默换成保真度更低的静图导出。
