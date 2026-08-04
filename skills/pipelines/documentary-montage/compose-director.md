# 合成导演 —— Documentary Montage 管线

## 何时使用

时间线已经存在。每个剪辑点都有入/出点，转场已经
选定，音乐铺底已经锁定。你现在得渲染这件作品，
并施加那道让年代混杂的素材库感觉像同一部影片的
基调抹平处理（统一裁剪 + LUT + 混音）。

产出是一个 mp4 加一份 `render_report` artifact。

## 运行时路由（硬约束）

本管线当前**要求** `render_runtime="remotion"`。片尾标签栈（合成到最终场景之上的 ProRes 4444 叠加层，或 concat 兜底）依赖 Remotion 的 `CinematicRenderer` composition 及其保留 alpha 的渲染路径。HyperFrames 的片尾标签对等能力被明确列为 Wave 3 / 待办工作（见 `skills/core/hyperframes.md` → "哪些内容在 Phase 1 仍然只走 Remotion"）。

- 若 `edit_decisions.render_runtime` 不是 `remotion`，停下。这是 CRITICAL 级的治理违规。把冲突呈现给用户，把决策退回 proposal 阶段重新锁定 `render_runtime="remotion"`，在 decision_log 中记录一条 `render_runtime_selection` 更正，然后继续。
- 绝不要靠改写 edit_decisions 里的 render_runtime 来静默推进。纪录片的承诺（以运动为主、情绪驱动、统一调色）正是由 Remotion 这套栈保住的，而那个承诺才是用户批准的东西。
- 把 `proposal_packet` 传给 `video_compose.execute()`，好让工具内的 `runtime_swap_detected` 检查主动确认运行时端到端保持为 `remotion`。在本管线上出现 `skipped` 的检查，意味着你忘了传 proposal artifact。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]` | 剪辑点、转场、音乐、元数据提示 |
| 上游 artifact | `state.artifacts["assets"]["asset_manifest"]` | 文件路径、时长、provider |
| 工具 | `video_compose`（Remotion 优先 + FFmpeg 兜底） | 主渲染引擎 |
| 工具 | `audio_mixer` | 音乐淡变、静默窗口、L-cut |
| 工具（可选） | `color_grade` | 跨年代混杂片段的统一 LUT |
| 工具（可选） | `video_trimmer`、`video_stitch` | 必要时用的更底层辅助 |

## 心智模型

多数管线把合成当成一个乏味的导出步骤。对
纪录片蒙太奇而言它是一个**创意**步骤：这是最后一道让调色
和混音把来自截然不同来源的素材调和成一件作品的处理。

有三件事必须在这里做，更早都做不了：

1. **统一画幅与黑边。** Pexels 1920x1080、Prelinger
   640x480 的 4:3、NASA 1280x720，都得落在同一块画布上。
2. **统一调色。** 一条贯穿整条时间线的 LUT，才是让 1962 年的
   家庭录像能和 2023 年的厨房镜头挨在一起而不跳戏的
   原因。
3. **混音。** 音乐电平、静默窗口、L-cut 的环境声
   延续、最终淡出 —— 在手握时间线的情况下一次做完。

## 流程

### 0. 硬性要求核查

读 `brief` 和 `edit_decisions.metadata`，看有没有硬性要求。
若 brief 说了"不要旁白"，而剪辑里不知怎么冒出了一条旁白轨，
就**停下**并去问。不要在违反契约的前提下渲染。

同时确认 `edit_decisions.renderer_family` 锁定为
`documentary-montage`，并且所选渲染引擎保住了这个
决定。按本仓库的治理模型，`video_compose` 在
`operation="render"` 上是 Remotion 优先的，即便对素材主导的作品也是如此。

- 若 Remotion 可用，就走常规的 `render` 路径，保持
  已获批的 renderer family。
- 若 Remotion 不可用，**不要**悄悄退到 FFmpeg。把
  引擎变更呈现出来，取得批准之后再使用更底层的
  纯 FFmpeg 路径。

### 1. 确定画布

读 `brief.target_platform`：

| 目标 | 画布 | 黑边 |
|--------|--------|-----------|
| `social_short`（Instagram/TikTok） | 1080x1920（9:16） | 上下裁切；每个片段居中锚定 |
| `youtube` / `generic` | 1920x1080（16:9） | 无；也可加 2.35:1 的上下黑条以求电影感 |
| `linkedin` | 1920x1080（16:9） | 无 |

时间线上的每个片段都必须被缩放/裁切到这块画布上。
对 `social_short`，这通常意味着把 16:9 素材居中裁切。
对采用电影感 2.35:1 黑条处理的 `youtube`，在 1920x1080 画布上
上下各补 140px 黑边。

把这个决定写进 `render_report.metadata.canvas` 和
`render_report.metadata.letterbox`。

### 2. 为 `video_compose` 构建拼接方案

剪辑 artifact 给了你一串带入/出点、转场
和源 asset_id 的剪辑点。遍历 asset_manifest，把每个
asset_id 解析成真实文件路径。然后构建渲染方案。

对这样一条简单的管线，最干净的路径是：

```python
video_compose.execute({
    "operation": "render",
    "output_path": "projects/<name>/renders/final.mp4",
    "edit_decisions": edit_decisions_with_renderer_family,
    "asset_manifest": asset_manifest,
})
```

确切的字段名以渲染时 `video_compose` 的实时 schema 为准 ——
写这个调用之前，若有 `agent_skills` 就先去查。不要凭空发明参数。

`edit_decisions_with_renderer_family` 指的是保持
`renderer_family = "documentary-montage"` 完好无损的常规剪辑 artifact。

### 3. 通过 LUT 调色，而不是逐片段调

读 `edit_decisions.metadata.grade_profile`。把它映射到 LUT 文件：

| 配置 | LUT | 适合 |
|---------|-----|-------|
| `warm_film_100` | 复古胶片暖调，轻微提亮 | 哀歌、梦境 |
| `cool_archive_60` | 冷高光，压死的黑 | 紧迫、戏谑 |
| `neutral_doc_20` | 几乎察觉不到的中性平衡 | 庄重 |
| `bleach_bypass_80` | 去饱和、高对比 | 戏谑、纪实的严苛感 |

若样式库里没有这个配置，就用 `neutral_doc_20` 并在
`warnings` 中注明。不要试图自动调色 —— LUT 就是
这道基调抹平处理的全部意义。

在 composition 层级施加 LUT，而不是逐片段施加。一条 LUT、一条
时间线、一种一致的外观。这正是让 1962 年的 Prelinger
片段与 2023 年的 Pexels 片段感觉像同一部片子的原因。

### 4. 音频只在合成阶段混一次

剪辑 artifact 已经决定了音量、淡变、静默窗口
和 L-cut 的音效层。你的工作是忠实执行它们：

- 音乐铺底按 `edit_decisions.audio.music.volume`（默认 0.7）。
- 按 `fade_in_seconds` 淡入，按 `fade_out_seconds` 淡出。
- 静默窗口 = 在该窗口时长内压到 0.0，之后以 0.2 秒的
  延迟斜坡升回。
- L-cut 的音效层 = 以 0.5-0.7 的音量混在音乐之下。
- 除非 `edit_decisions.audio.narration` 里明确存在，否则不要有旁白。

**音乐是强制的。** 若剪辑里没有音乐条目，去查 brief：

- `brief.metadata.music_plan.source == "none"` 且有 `opt_out_reason` →
  用户明确弃用了。渲染成静默，并在
  `render_report.warnings` 中注明。
- 其他任何情况 → **停下**。这是违反契约。渲染之前把它
  呈现给用户。在一个音乐为强制项的 brief 上交出一个静默渲染，
  是本管线中最响亮的失败模式。

**不要**为了"填补空白"而加环境噪声。

### 4b. 通过 Remotion 渲染片尾标签

片尾标签是通过 Remotion **单独**渲染的，与 FFmpeg 的正片分开。
这让两个渲染引擎（FFmpeg 负责素材，
Remotion 负责排版）保持干净的分离。合成方式
取决于 `brief.metadata.end_tag_plan.mode`。

读 `brief.metadata.end_tag_plan`：

```json
{
  "text": "WE BUILT BOTH WITH THE SAME HANDS.",
  "palette": "warm_ivory_on_black",
  "duration_seconds": 5.5,
  "render_engine": "remotion",
  "component": "EndTag",
  "mode": "overlay"
}
```

#### 路径 A —— Overlay 模式（默认）

标签在正片素材的最后几个场景上淡入。这是
默认方式，效果更有电影感 —— 排版出现在实拍素材之上，
而不是切到一张黑卡。

**执行：**

1. 用 FFmpeg 合成正片（剪辑点 + LUT + 音乐 + 静默窗口）。
   保存为 `projects/<name>/renders/body.mp4`。记下正片的 fps。
2. 计算 `durationInFrames = round(duration_seconds × body_fps)`。
3. 通过 Remotion CLI 渲染带 alpha 的片尾标签：
   ```bash
   npx remotion render src/index.tsx EndTagOverlay \
     projects/<name>/renders/end_tag_overlay.mov \
     --codec=prores --prores-profile=4444 \
     --pixel-format=yuva444p10le --image-format=png \
     --props='{"text":"...","palette":"...","overlay":true,
               "fadeInSeconds":1.0,"holdSeconds":3.0,"fadeOutSeconds":1.5}'
   ```
   使用 `EndTagOverlay` composition，并设 `overlay: true`。这会
   产出一个带真实 alpha 通道的 ProRes 4444 MOV
   （pix_fmt=yuva444p12le）。画布必须与正片画布一致。
4. 计算叠加偏移量：
   - 若存在，读 `edit_decisions.end_tag.offset_seconds`。
   - 否则自动计算：`offset = 正片时长 - 标签时长`。
     标签的淡出应与正片收尾的淡出对齐。
5. 用 FFmpeg 的 overlay 配合 `-itsoffset` 做合成：
   ```bash
   ffmpeg -y \
     -i body.mp4 \
     -itsoffset {offset} -i end_tag_overlay.mov \
     -filter_complex "[0:v][1:v]overlay=0:0:format=auto:eof_action=pass[v]" \
     -map "[v]" -map "0:a" \
     -c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p \
     -c:a aac -b:a 192k \
     projects/<name>/renders/final.mp4
   ```
   `eof_action=pass` 表示叠加层结束之后正片视频继续。
   淡入/停留/淡出由叠加层自身的 alpha 负责。

**验证：** 从叠加区域抽一帧（例如
`offset + 2秒`），确认文字是显示在素材之上、而不是黑底之上。
若那一帧显示文字后面是黑背景，说明 alpha 通道丢了 ——
用 `--image-format=png` 重新渲染。

#### 路径 B —— Concat 模式

经典的尾卡：在正片之后追加一张不透明黑卡。只有当
`end_tag_plan.mode == "concat"` 时才用它。

**执行：**

1. 如上合成正片。
2. 把片尾标签渲染成不透明 MP4：
   ```bash
   npx remotion render src/index.tsx EndTag \
     projects/<name>/renders/end_tag.mp4 \
     --props='{"text":"...","palette":"...","durationInFrames":132}'
   ```
   （24fps 下 5.5 秒 = 132 帧）。画布必须与正片画布一致。
3. 把正片 + end_tag 拼接：
   ```bash
   ffmpeg -f concat -safe 0 -i list.txt -c copy final.mp4
   ```
   若编码不匹配就重新编码。

#### 通用规则（两种模式都适用）

**片尾标签是强制的。** 唯一能跳过它的方式，是用户明确
弃用，并记录为 `end_tag_plan: null` 加 `end_tag_opt_out_reason`。
若 brief 里有片尾标签方案而你跳过了渲染，那就是
违反契约。在定稿之前停下并呈现出来。

记入 `render_report`：
- `end_tag_rendered: true | false`
- `end_tag_mode: "overlay" | "concat"`
- `end_tag_path: "projects/<name>/renders/end_tag_overlay.mov"`（concat 模式则为 `.mp4`）
- `end_tag_offset_seconds: <数值>`（仅 overlay 模式）
- `end_tag_text: "..."`（用于审计轨迹）

若 brief 说了"不要音乐"，而剪辑里也正确地没有音乐
条目，**并且** `music_plan.source == "none"` 带有弃用理由，那就渲染成
静默。**不要**为了"填补空白"而加环境噪声。

### 5. 按纪录片规格渲染

纪录片蒙太奇的推荐编码设置：

| 字段 | 取值 | 理由 |
|-------|-------|-----|
| 编码 | `libx264`（H.264） | 通用，体积小 |
| 像素格式 | `yuv420p` | 通用兼容 |
| CRF | `18` | 对最终交付物而言视觉无损 |
| FPS | `24` | 电影感。**不要**把 24 上转成 30。 |
| 音频编码 | `aac` | 通用 |
| 音频码率 | `192k` | 对音乐铺底友好 |

若源片段是 30fps 而画布是 24fps，就让渲染管线
均匀丢帧 —— 不要做混合。对混合来源的素材做运动插值
看起来会很糟。

### 6. 渲染后验证

渲染成功之后，真的去探测输出文件并检查：

- **时长。** 应当与 `sum(out - in for cut in cuts) + 首尾
  淡变` 相差在 ±0.5 秒以内。
- **分辨率。** 应当与画布一致。
- **音频存在与否。** 若方案里有音乐，输出就必须
  有音频流。若方案是静默，也要确认。
- **首帧与末帧。** 打开文件，跳到 0 秒和
  时长-0.1 秒。首帧应当是淡入。末帧
  应当是（或正在渐变为）黑场。
- **静默窗口。** 跳到 silence_window 的起点。音频电平
  在波形上应当有明显下降。

把验证结果记入 `render_report.verification_notes`。

### 7. 产出 Render Report

```json
{
  "version": "1.0",
  "outputs": [
    {
      "path": "projects/<name>/renders/final.mp4",
      "format": "mp4",
      "codec": "h264",
      "audio_codec": "aac",
      "resolution": "1920x1080",
      "fps": 24,
      "duration_seconds": 89.8,
      "file_size_bytes": 18234112,
      "platform_target": "youtube"
    }
  ],
  "render_time_seconds": 42.3,
  "warnings": [],
  "verification_notes": [
    "Duration within +0.2s of planned",
    "First frame is black fade-in as specified",
    "Silence window 54-56s confirmed (music -60dB)",
    "Last frame fades to black at 89.0s"
  ],
  "render_grammar": "documentary-montage",
  "metadata": {
    "pipeline": "documentary-montage",
    "canvas": { "width": 1920, "height": 1080 },
    "letterbox": "2.35:1",
    "lut": "warm_film_100",
    "music_present": true
  }
}
```

### 8. 质量门

- 输出文件存在且能播放。
- 时长在 `brief.duration_seconds` 的 ±1 秒以内（含正片 + 片尾标签）。
- 分辨率与 `target_platform` 的画布一致。
- LUT 已被应用（或记录了警告）。
- **音乐存在**，除非 `brief.metadata.music_plan.source == "none"` 且有明确的弃用理由。
- **片尾标签 MP4 已渲染并拼接**，除非 `brief.metadata.end_tag_plan` 为 null 且有明确的弃用理由。在那种情况下，最终 MP4 的末帧必须是片尾标签卡。
- 首帧与末帧已验证。
- 静默窗口（若有）已在波形上验证。
- 除非 brief 已批准，否则没有旁白。
- `render_report.warnings` 列出了每一次替换。
- `render_report.metadata.music_mixed = true` 且 `render_report.metadata.end_tag_rendered = true`（或记录了明确的弃用）。

## 常见陷阱

- **让年代混杂的片段未经调色就渲染出去。** 作品会看起来
  像一份网络片段的 PowerPoint 幻灯片。LUT 是
  不可妥协的。
- **为了贴合画布而放大，而不是加黑边。**
  把 Prelinger 的 640x480 放大到 1920x1080 会像素化，很难看。
  把它居中加黑边，或者干脆把方正裁剪当作一种设计选择。
- **为了"填补空白"而加旁白或环境音效。** 这是重大
  变更，需要用户批准。
- **逐片段调色。** 整件作品用一条 LUT。不要
  试图逐个平衡每个片段 —— 那要花 10 倍时间，
  还会让基调**更不**一致，而不是更一致。
- **静默降级到 FFmpeg。** 若 Remotion 被卡住而你在没有
  呈现的情况下改走 FFmpeg，你就更改了已获批的渲染路径。
  渲染之前先停下并把这次降级说出来。
- **在渲染时覆盖剪辑决策。** 若你发现自己正在
  渲染调用里调整音量、淡变或修剪，那你就是在合成期
  做剪辑。回到 edit 阶段，把决策修好，
  重新产出 artifact，然后再渲染。
- **跳过验证。** 一个"成功了"但其实是静默、
  淡变不对，或把最后一个主镜头切掉的渲染，
  比失败更糟。打开文件看看。

## 渲染失败时

若 `video_compose` 返回错误：

1. 按决策沟通契约判断错误类别
   （鉴权 / provider / 工具 bug / 方案质量）。
2. 若是路径错误，去 asset manifest 中逐个校验
   asset_id → path 的解析。一个文件缺失就会让整次渲染失败。
3. 若是编码错误，输入片段可能有奇怪的容器
   （Archive.org 有时会给 Matroska）。先把每个输入
   过一遍 `video_trimmer` 归一化为 mp4/h264。
4. 若是内存或超时错误，就把渲染拆成两半，
   最后用 `video_stitch` 合起来。
5. 在改走保真度更低的路径之前，先呈现给用户。
   本管线是素材主导的；不存在生成静图的
   兜底方案。
