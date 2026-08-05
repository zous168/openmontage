# 合成导演 —— Animation 管线

## 何时使用

渲染这支动画，重点关注文字锐利度、时序完整性和一致的输出节奏。对 `image_animation` 方式，本阶段还包括构建 composition JSON、取得音乐、跑渲染前校验，以及做渲染后自评。

## 运行时路由（强制的第一步）

在做任何其他事情之前，先读 `edit_decisions.render_runtime`。它在 proposal 阶段就已锁定，**不得**被静默更改。本技能其余部分假定 `render_runtime="remotion"`（本管线的默认值）。若 proposal 锁定的是另一个运行时：

- **`render_runtime="hyperframes"`** —— HTML/CSS/GSAP 渲染。**不要**照下面 Remotion 专属的章节做（public/ 暂存、Remotion composition JSON）。改为：
  1. 读 `skills/core/hyperframes.md` 了解完整路由模型。
  2. 读 `.agents/skills/hyperframes/SKILL.md` 和 `.agents/skills/hyperframes-cli/SKILL.md` 了解编写契约和 CLI 用法。
  3. 以 `edit_decisions.render_runtime="hyperframes"` 调用 `video_compose` —— 它会委派给 `hyperframes_compose`，后者负责在 `projects/<name>/hyperframes/` 下物化工作区、运行 `hyperframes lint → validate → render`，并返回 MP4 路径。
  4. 渲染之前 `hyperframes lint` 和 `hyperframes validate` **都必须**通过。绝不跳过 validate；迭代期间可以用 `skip_contrast=true` 暂缓对比度检查，但最终交付不行。
- **`render_runtime="ffmpeg"`** —— 简单的拼接/修剪，不做合成。直接调用 `video_compose`；它不会自动升级到 Remotion。
- **运行时不可用** —— **不要**静默换成另一个引擎。按 AGENT_GUIDE.md > "Escalate Blockers Explicitly" 把阻塞项上报给用户，并在切换之前等待批准（并把它记为 decision_log 中的一条 `render_runtime_selection` 决策）。

渲染后自评（final_review）在各运行时之间完全相同 —— 同样的 ffprobe 探测、抽帧、音频抽查和承诺保持检查。`final_review.checks.promise_preservation.render_runtime_used` 必须等于实际运行的那个运行时。

**调用 `video_compose.execute()` 时把 `proposal_packet` 传进去。** 这样工具就能直接把 proposal 锁定的运行时与 `edit_decisions` 中记录的运行时做比较，一旦不一致就把 `runtime_swap_detected` 置为 `true`。不传的话，这项检查会是 `skipped`，reviewer 技能就只能靠跨 artifact 比对来抓切换。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 时序方案与素材文件 |
| 工具 | `video_compose`、`audio_mixer`、`video_stitch` | 最终装配 |
| 工具 | `composition_validator` | 渲染前校验（强制） |
| 工具 | `audio_probe` | 音乐时长检查 |
| Playbook | 当前生效的风格 playbook | 渲染一致性 |
| 参考 | `remotion-composer/public/demo-props/mori-no-seishin.json` | Composition JSON 格式参考 |
| 参考 | `skills/core/remotion.md` | Remotion 范式、anime_scene 类型、关键约束 |

## 流程

### 1. 确保素材位于 Remotion 的 public 目录

**关键：** Remotion 只能通过 `staticFile()` 访问文件，而它是从 `remotion-composer/public/` 解析的。生成的图像和音乐文件在渲染之前**必须**被复制或符号链接到这个目录。

```
项目结构：
  projects/<name>/assets/images/*.png     ← 图像生成在这里
  remotion-composer/public/<name>/*.png   ← Remotion 从这里读

必需：把图像**和**音乐复制或符号链接到 public/<project-name>/
```

composition JSON 中的图像路径是相对于 `remotion-composer/public/` 的：
```json
"images": ["deep-ocean/scene1-a.png", "deep-ocean/scene1-b.png"]
"src": "deep-ocean/ambient-music.mp3"
```

**若跳过这一步，渲染会因文件缺失而失败，或者产出黑帧。**

### 2. 构建 Composition JSON（image_animation 方式）

对 `anime_scene` 类的 composition，在 `remotion-composer/public/demo-props/<name>.json` 构建一个 JSON 文件。

**必需结构：**

```json
{
  "cuts": [
    {
      "id": "scene-1-name",
      "source": "",
      "in_seconds": 0,
      "out_seconds": 5,
      "type": "anime_scene",
      "images": ["<project>/<image-a>.png", "<project>/<image-b>.png"],
      "animation": "<camera-motion>",
      "particles": "<particle-type>",
      "particleColor": "#HEXCOLOR",
      "particleCount": 20,
      "particleIntensity": 0.5,
      "backgroundColor": "#0A0A1A",
      "vignette": true,
      "lightingFrom": "rgba(r,g,b,a)",
      "lightingTo": "transparent"
    }
  ],
  "overlays": [...],
  "audio": { "music": { "src": "<project>/music.mp3", "volume": 0.15, "fadeInSeconds": 2, "fadeOutSeconds": 3 } }
}
```

**Prop 名称参考（JSON 字段 → AnimeScene prop）：**

| JSON 字段 | 类型 | 取值 | 必填 |
|------------|------|--------|----------|
| `type` | string | `"anime_scene"` | 是 |
| `images` | string[] | 1-4 个相对 `public/` 的图像路径 | 是 |
| `animation` | string | `zoom-in`、`zoom-out`、`pan-left`、`pan-right`、`ken-burns`、`drift-up`、`drift-down`、`parallax`、`static` | 否（默认 `ken-burns`） |
| `particles` | string | `fireflies`、`petals`、`sparkles`、`mist`、`light-rays` | 否 |
| `particleColor` | string | 十六进制颜色 | 否（默认 `#FFE082`） |
| `particleCount` | number | 1-50 | 否（默认 20） |
| `particleIntensity` | number | 0-1 | 否（默认 0.6） |
| `backgroundColor` | string | 场景背景的十六进制颜色 | 否（默认 `#0A0A1A`） |
| `vignette` | boolean | 电影感暗角叠加 | 否（默认 true） |
| `lightingFrom` | string | 渐变起始色（`rgba(...)` 或 `transparent`） | 否 |
| `lightingTo` | string | 渐变结束色 | 否 |

**参考：** 完整可运行的示例见 `mori-no-seishin.json`（吉卜力森林）和 `deep-ocean.json`（水下生物发光）。

### 3. 取得音乐并找到最佳偏移量

用 `tools/audio/pixabay_music.py` 找与情绪匹配的免版税氛围音乐。

**下载之后，运行音频能量分析（强制）：**

```python
from tools.analysis.audio_energy import AudioEnergy
result = AudioEnergy().execute({
    "input_path": "path/to/music.mp3",
    "video_duration_seconds": 30,  # 你的视频时长
})
data = result.data
print(f"Recommended offset: {data['recommended_offset_seconds']}s")
print(f"Reason: {data['offset_reason']}")
print(f"Needs loop: {data['needs_loop']}")
```

这个工具会：
1. **找出最佳段落** —— 分析逐秒响度，找到平均能量最高的那个 N 秒窗口。氛围音乐往往在主旋律进来之前有一段安静的前奏（10-30 秒）。
2. **建议是否循环** —— 若从偏移点开始的音乐短于视频，它会提示你启用循环。

**在 composition JSON 中应用这个偏移：**

```json
"audio": {
  "music": {
    "src": "project/music.mp3",
    "volume": 0.15,
    "fadeInSeconds": 2,
    "fadeOutSeconds": 3,
    "offsetSeconds": 55,
    "loop": false
  }
}
```

- `offsetSeconds` —— 从音轨的这个位置开始播放（跳过安静的前奏）
- `loop` —— 若剩余音乐短于视频，就设为 `true`

**若工具报告 `needs_loop: true`：** 在 composition JSON 中设 `"loop": true`。Remotion 会无缝循环音频，并在每次循环时重置音量淡变。

### 4. 渲染前校验（强制 —— 没有例外）

每次渲染之前都运行 `composition_validator`：

```python
from tools.analysis.composition_validator import CompositionValidator
result = CompositionValidator().execute({
    "composition_path": "remotion-composer/public/demo-props/<name>.json",
    "assets_root": "remotion-composer/public",
})
# 继续之前 result.data["valid"] 必须为 True
```

它能捕获：
- 会导致黑帧或渲染错误的缺失图像/音频文件
- 无效的 cut 时序（out ≤ in）
- 音频长于视频时长

**若校验失败，在渲染**之前**修好问题。不要渲染一个无效的 composition。**

### 5. 保持运动时序

不要让导出设置或粗心的合成，改变了停留、错峰或场景转场在观感上的时序。

### 6. 保护文字与图表的锐利度

动画常常在导出时因为文字发虚、细线发糊或移动端构图局促而翻车。

### 7. 渲染

```bash
cd remotion-composer
npx remotion render Explainer \
  --props="public/demo-props/<name>.json" \
  --output="<output-path>/final.mp4" \
  --codec=h264 --crf=18
```

**注意：** composition 名是 `Explainer`（不是 `ExplainerVideo`）。**不要**把 `src/index.ts` 指定为入口 —— Remotion 会自动发现。

### 8. 渲染后自评（强制）

渲染之后，抽取各场景中点的帧并目视检查：

```bash
# 从每个场景的中间抽一帧
ffmpeg -y -i final.mp4 \
  -vf "select='eq(n\,75)+eq(n\,225)+eq(n\,375)+eq(n\,525)+eq(n\,675)+eq(n\,825)'" \
  -vsync vfr frames/scene_%02d.png
```

**逐帧检查：**
- [ ] 图像可见（不是黑帧/过暗的帧）
- [ ] 粒子在渲染（星光、萤火虫等可见）
- [ ] 镜头运动明显（构图与静止时不同）
- [ ] 叠加层在正确时刻显示，文字干净
- [ ] 跨场景的配色一致
- [ ] 暗角制造出电影感的纵深

**同时验证输出文件：**
```bash
ffprobe -v quiet -print_format json -show_format -show_streams final.mp4
```
- 时长在目标的 ±5% 以内吗？
- 分辨率是 1920×1080 吗？
- 音频流存在吗？

**若发现问题：** 找出成因（图像缺失、时序错误、渲染故障）并在呈现给用户之前修好。

### 9. 使用渲染元数据

推荐的元数据键：

- `render_fps`
- `sharpness_checks`
- `safe_zone_checks`
- `variant_outputs`

**输出唯一性(硬性)**:
- `render_report.outputs` 不得包含重复产物:同一路径,或相同内容(相同 file_size_bytes + duration_seconds + resolution)只记录一次。
- 重渲染时:用新输出**替换**旧条目,绝不追加(追加会产生重复输出,校验会拦截)。
- 不同运行时/不同内容的变体(如 FFmpeg 版与 Remotion 字幕版**内容确实不同**)可并列记录,但必须内容真实不同。

## 常见陷阱

- **忘了把素材复制到 `remotion-composer/public/`** —— 渲染失败的头号原因。图像生成到 `projects/<name>/assets/`，而 Remotion 是从 `public/` 读的。
- 渲染之后文字发虚或有锯齿。
- 损害图表的压缩参数选择。
- 预览与成片之间场景节奏发生变化。
- **跳过 `composition_validator`** —— 它能在你浪费渲染时间之前抓出缺失文件、错误时序和音频不匹配。
- **不抽帧做自评** —— 一支渲染好的视频在帧被目视检查之前不算"完成"。黑帧、粒子缺失或图像不可见，单看文件大小并不总是能发现。
- **用 `useVideoConfig()` 的 `durationInFrames` 做场景级时序** —— 它返回的是**整个** composition 的时长，不是该场景 Sequence 的时长。见 `skills/core/remotion.md` 的关键约束。
