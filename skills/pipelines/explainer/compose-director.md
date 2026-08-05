# 合成导演 —— Explainer 管线

## 何时使用

你是一支生成式讲解视频的合成师。你手上有一份含完整剪辑时间线的 `edit_decisions` 和一份含全部文件路径的 `asset_manifest`。你的工作是渲染最终视频：装配画面、分层音频、烧录字幕，并编码为目标格式。

这是视频成为可播放文件之前的最后一个技术阶段。一切在这里汇聚。

## 运行时路由（强制的第一步）

在做任何其他事之前，先读 `edit_decisions.render_runtime`。它在 proposal 阶段就已锁定，不得被静默更改。本技能其余的流程步骤（Remotion 的 public/ 暂存、词级字幕烧录等）都假定 `render_runtime="remotion"` —— 数据驱动讲解视频的默认值。

- **`render_runtime="hyperframes"`** —— HTML/CSS/GSAP 渲染。**不要**照下面 Remotion 专属的步骤做。改为：读 `skills/core/hyperframes.md`、`.agents/skills/hyperframes/SKILL.md` 和 `.agents/skills/hyperframes-cli/SKILL.md`。用原封不动的 edit_decisions 调用 `video_compose` —— 它会委派给 `hyperframes_compose`，后者会在 `projects/<name>/hyperframes/` 下物化工作区、运行 `lint → validate → render`，并返回 MP4。渲染之前 lint **和** validate 都必须通过；迭代期间可以暂缓对比度检查，但最终交付不行。
- **`render_runtime="ffmpeg"`** —— 简单的拼接/修剪。直接调用 `video_compose`；当这个运行时被显式锁定时，它**不会**自动升级到 Remotion。
- **运行时不可用** —— 按 AGENT_GUIDE.md > "Escalate Blockers Explicitly" 上报阻塞项，并在切换之前取得用户批准（记录为 decision_log 中的一条 `render_runtime_selection` 决策）。

`final_review.checks.promise_preservation.render_runtime_used` 必须等于实际运行的那个运行时；除非有已获批的决策授权切换，否则 `runtime_swap_detected` 必须为 `false`。

**把 `proposal_packet` 传给 `video_compose.execute()`**，好让工具内的切换检测真的能触发。不传的话，`runtime_swap_check` 会被报告为 `skipped`，你就只能依赖 reviewer 技能的跨 artifact 比对。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["edit"]["edit_decisions"]`、`state.artifacts["assets"]["asset_manifest"]` | 要渲染什么 |
| Playbook | 当前生效的风格 playbook | 质量目标 |
| 工具 | `video_compose`、`audio_mixer` | 渲染能力 |
| Media profile | `lib/media_profiles.py` | 输出格式规格（分辨率、编码、码率） |
| 项目交付规格 | `meta.json` → `production_inputs` | 由工具自动应用（见下） |

### 项目交付规格（自动）

当项目在 Backlot 设置中有交付字段（`aspect_ratio`、`quality_tier`、`fps`，外加 `target_platform`）时，工具会**无需**手动传 `profile`/`compose_target` 参数就应用它们：

- **`video_compose` / `hyperframes_compose` / `video_stitch`** —— 从 `lib/deliverable_spec.resolve_deliverable()` 设置 `edit_decisions.metadata.compose_target` 和默认 `profile`
- **`export_bundle`** —— 把交付规格写进导出的 `metadata.json` 和 `publish_log`
- **AI 视频/图像工具** —— 未设置时，从同一规格取默认的 `aspect_ratio`、`width`、`height`

显式传入的工具参数仍然优先。可通过项目设置 API（`deliverable`）或 `python -m lib.project_status <id> --json` → `intake.deliverable` 读取解析后的规格。

## 流程

### 第 1 步：选择渲染策略

根据剪辑决策，挑选渲染方式：

**Remotion 渲染**（**默认** —— 除非被显式覆盖，都用它）：
- 动画文字卡、数据卡、图表场景
- 复杂转场（形变、缩放、ken-burns）
- 程序化动态图形
- 音频嵌入（旁白 + 音乐，带淡变/音量）
- 通过 CaptionOverlay 组件实现的词级字幕
- 最适合：**所有**讲解视频，无论是基于图像还是动画密集的

**FFmpeg 管线**（**兜底** —— 只在 Remotion 不可用时）：
- 带 Ken Burns 的静态图像
- 音频分层
- SRT 字幕烧录
- 最适合：没有安装 Node.js/Remotion 的环境

**重要：使用 Remotion 时，以下全部走 Remotion —— 而不是 FFmpeg：**
- 音频（旁白 + 音乐）→ Remotion 的 `audio` prop，**不是**外部的 audio_mixer
- 字幕 → Remotion 的 `captions` prop（词级），**不是**通过 FFmpeg 烧 SRT
- 文字叠加（CTA、标题）→ Remotion 的 `text_card` cut 类型，**不是** AI 生成的图像

### 第 2 步：音频获取（旁白、音乐、字幕）

渲染之前，把音频选项呈现给用户并取得他们的偏好。

**呈现给用户：**

> **这支视频的音频设置：**
>
> **旁白：** 我可以用 OpenAI TTS 生成 TTS 旁白（`gpt-4o-mini-tts` —— 每分钟 $0.015，6 种音色，支持配音指导）。你想要哪种音色和调性？我可以根据视频题材推荐一个，你也可以自己选：
> - `onyx` —— 低沉、权威（纪录片、科技）
> - `echo` —— 共鸣、未来感（产品广告、科幻）
> - `nova` —— 明亮、有活力（上扬、讲解）
> - `fable` —— 温暖、讲故事（叙事、教育）
> - `shimmer` —— 有表现力、温暖（有机、生活方式）
> - `alloy` —— 中性、均衡（通用）
>
> **音乐：** 我可以自动从 Pixabay 找免版税背景音乐（不需要 key）。若你有 `FREESOUND_API_KEY`，我还可以把 Freesound 作为备用来源检索。
>
> **字幕：** 我会用 WhisperX 转写最终旁白来生成词级字幕，并通过 Remotion 的 captions 烧进视频。
>
> 要我按推荐推进，还是要调整哪一项？

**用户确认之后：**

1. **按时长预算撰写旁白脚本**（见 scene-director 第 4b 步）：
   - 从各 cut 算出视频时长
   - 按视频时长的 85-90% 做预算
   - 纪实风格用每秒 2.0-2.5 词，有活力的用 2.5-3.0
   - 生成 TTS 之前先核对词数

2. **生成 TTS 旁白：**
   ```python
   from tools.audio.openai_tts import OpenAITTS
   result = OpenAITTS().execute({
       'text': narration_script,
       'voice': '<用户选定或 agent 推荐>',
       'instructions': '<与视频调性匹配的配音指导>',
       'output_path': 'path/to/narration.mp3',
   })
   # 关键：把 result.data['audio_duration_seconds'] 与视频时长比对
   # 若旁白比视频长出 1 秒以上：缩短脚本并重新生成
   ```

3. **下载背景音乐：**
   ```python
   from tools.audio.pixabay_music import PixabayMusic
   result = PixabayMusic().execute({
       'query': '<与视频题材匹配的情绪/曲风>',
       'min_duration': video_duration_seconds,
       'max_duration': 300,
       'output_path': 'path/to/music.mp3',
   })
   ```

4. **通过 WhisperX 生成字幕：**
   ```python
   from tools.analysis.transcriber import Transcriber
   result = Transcriber().execute({
       'input_path': 'path/to/narration.mp3',
       'model_size': 'base',
       'language': 'en',
   })
   # 把 word_timestamps 转换成 Remotion 的字幕格式：
   # [{ "word": "Hello", "startMs": 0, "endMs": 340 }, ...]
   ```

5. **组装带音频配置的 composition JSON：**
   ```json
   {
     "audio": {
       "narration": { "src": "path/to/narration.mp3", "volume": 1 },
       "music": { "src": "path/to/music.mp3", "volume": 0.1, "fadeInSeconds": 2, "fadeOutSeconds": 3 }
     },
     "captions": [ ... 来自 WhisperX 的词级字幕 ... ]
   }
   ```

### 第 3 步：准备渲染输入

对剪辑决策中的每个 cut：
1. 确认源素材存在于其声明的路径上
2. 检查素材的尺寸/时长是否符合预期
3. 准备变换参数（缩放、位置、裁切）

对音频：
1. 确认旁白时长能装进视频时长（用 `audio_probe`）
2. 确认音乐时长覆盖视频时长
3. 从剪辑决策中准备闪避参数

### 第 3 步：确定输出 Profile

从 brief artifact 读取目标平台。映射到一个 media profile：

| 平台 | Profile | 分辨率 | 备注 |
|----------|---------|-----------|-------|
| YouTube | `youtube_landscape` | 1920x1080 | 多数讲解视频的默认 |
| TikTok/Reels | `tiktok` | 1080x1920 | 竖屏，需要重新构图 |
| Twitter/X | `twitter_landscape` | 1280x720 | 更短的形态 |
| LinkedIn | `linkedin` | 1920x1080 | 专业语境 |

通过 `ffmpeg_output_args(get_profile(name))` 取得确切的编码参数。

### 第 4 步：渲染视频

调用 `video_compose` 工具，传入：
```
{
  "operation": "render",
  "edit_decisions": <edit_decisions artifact>,
  "asset_manifest": <asset_manifest artifact>,
  "output_profile": "youtube_landscape",
  "output_path": "renders/output.mp4",
  "options": {
    "subtitle_burn": true,
    "audio_normalize": true,
    "two_pass_encode": true
  }
}
```

若动画段落使用 Remotion：
1. 从剪辑决策生成 Remotion 的 composition 数据
2. 对动画段落用 `operation: "remotion_render"` 调用 `video_compose`
3. 通过 FFmpeg 把 Remotion 的输出与其余段落装配起来

**零 key 的 Remotion 渲染（纯组件视频）：**
当所有场景都是 Remotion 组件类型（hero_title、stat_card、bar_chart、line_chart、
pie_chart、kpi_grid、comparison、callout、progress_bar、text_card）时，就把整支视频
渲染为一个 Remotion composition，使用 Explainer 入口。不需要 FFmpeg 装配。
edit_decisions 的 cuts 数组直接映射到 Remotion props。经过验证的公式见
`skills/core/remotion.md` —— 尤其是为保证视觉一致性的全深色背景规则。

### 第 5 步：音频后处理

**Remotion 路径（默认）：** 完全跳过外部音频混音。Remotion 通过 `<Audio>` 组件
原生处理所有音频。把音频源作为 composition props 传入：
```json
{
  "audio": {
    "narration": { "src": "project/narration.mp3", "volume": 1.0 },
    "music": { "src": "project/music.mp3", "volume": 0.12, "fadeInSeconds": 1.5, "fadeOutSeconds": 2.5 }
  }
}
```
Remotion 在一次渲染中同时输出音频和视频 —— 不需要外部复用。
用 Remotion 渲染时**不要**用 `audio_mixer` 做闪避/混音。

**FFmpeg 兜底（仅在 Remotion 不可用时）：**
调用 `audio_mixer` 工具来：
1. 按顺序分层旁白段
2. 按 playbook 音量混入背景音乐
3. 应用闪避（旁白期间音乐下压）
4. 归一化整体音量
5. 输出最终混音音轨
video_compose 工具会把它与视频复用在一起。

### 第 5b 步：生成字幕（强制）

字幕对所有讲解内容都是强制的。从旁白音频生成字幕 —— **不要**跳过这一步。

**Remotion 路径（默认 —— 使用 Remotion 渲染时）：**

1. 用 `transcriber` 工具（whisperx）**转写**完整旁白：
   ```python
   from tools.analysis.transcriber import Transcriber
   result = Transcriber().execute({
       'input_path': 'projects/<project>/assets/audio/narration_full.mp3',
       'model_size': 'base',
       'language': 'en',
       'output_dir': 'projects/<project>/assets/audio'
   })
   # result.data 含有带词级时间戳的 segments
   ```

2. **转换成 Remotion 的 WordCaption 格式**（**不是** SRT）：
   ```python
   captions = []
   for segment in result.data['segments']:
       for word_info in segment.get('words', []):
           captions.append({
               'word': word_info['word'],
               'startMs': int(word_info['start'] * 1000),
               'endMs': int(word_info['end'] * 1000),
           })
   ```

3. **把字幕加进 composition props** —— 它们与 `cuts` 和 `audio` 并列放在 `captions` 数组里：
   ```json
   {
     "cuts": [...],
     "audio": {...},
     "captions": [
       { "word": "Root", "startMs": 120, "endMs": 340 },
       { "word": "canals", "startMs": 340, "endMs": 680 }
     ]
   }
   ```

   Remotion 的 CaptionOverlay 会把它们渲染成逐词高亮的字幕，使用主题的
   `captionHighlightColor` 和 `captionBackgroundColor`。这优于 FFmpeg 的 SRT 烧录，因为
   它能产出与旁白同步的、带动画的词级高亮。

**FFmpeg 兜底（仅在 Remotion 不可用时）：**

若 Remotion 不可用，就退回到生成 SRT + FFmpeg 烧录：
   ```python
   from tools.subtitle.subtitle_gen import SubtitleGen
   SubtitleGen().execute({
       'segments': transcription_data['segments'],
       'format': 'srt',
       'output_path': 'projects/<project>/assets/subtitles.srt',
       'max_words_per_cue': 8,
       'max_chars_per_line': 42
   })
   # 然后用 video_compose 的 operation='burn_subtitles' 烧进去
   ```

**最终交付物**必须**有字幕** —— 要么走 Remotion captions，要么走 FFmpeg 烧录。

### 第 5c 步：渲染前校验（强制）

**渲染之前一律运行 composition validator。** 它能抓出那些会白白浪费渲染时间的问题。

```python
from tools.analysis.composition_validator import CompositionValidator
result = CompositionValidator().execute({
    'composition_path': 'path/to/composition.json',
    'assets_root': 'remotion-composer/public',
})
# 进入渲染之前 result.data['valid'] 必须为 True
# 若为 False：先修好报告出来的错误（素材缺失、音画不匹配等）
```

常见捕获项：
- 旁白音频长于视频（会被截断）
- 图像/音频文件缺失（渲染会失败）
- 音乐短于视频（结尾出现静音）

**不要跳过这一步。** 若校验失败，先修好问题并重新校验，再去渲染。

### 第 6 步：渲染后自评（强制 —— 每一步都要做）

渲染之后，agent **必须复看自己的产出**，然后才能呈现给用户。这能抓出校验器看不到的问题（视觉质量、音画同步、字幕可读性）。

**关键：你必须完成 6a 到 6e 的全部步骤。不要跳过任何一步。
agent 最常见的失败，就是做了 6a（抽帧）和 6c（视觉检查）却跳过了
6b（音频转写）—— 从而漏掉了"音频完全缺失"这类灾难性问题。**

**6a. 探测渲染文件（第一步 —— 是其余所有检查的门禁）：**
```bash
ffprobe -v quiet -print_format json -show_format -show_streams rendered_video.mp4
```
确认：
- 视频流存在（codec_type: "video"）且分辨率正确
- **音频流存在（codec_type: "audio"）** —— 若**没有**音频流，立刻停下并修复
- 时长在目标的 ±5% 以内
- 文件大小合理（不是 0 字节）

**若音频流缺失：说明渲染没有嵌入音频。**不要**把视频呈现
给用户。修好音频配置并重新渲染。**

**6b. 抽取复看帧：**
```python
from tools.analysis.frame_sampler import FrameSampler
midpoints = [(cut['in_seconds'] + cut['out_seconds']) / 2 for cut in cuts]
FrameSampler().execute({
    'input_path': 'path/to/rendered_video.mp4',
    'strategy': 'timestamps',
    'timestamps': midpoints,
    'output_dir': 'path/to/review-frames',
    'format': 'png',
})
```

**6c. 转写渲染出来的音频（强制 —— 不要跳过）：**
```python
from tools.analysis.transcriber import Transcriber
result = Transcriber().execute({
    'input_path': 'path/to/rendered_video.mp4',
    'model_size': 'base',
    'language': 'en',
    'output_dir': 'path/to/review-frames',
})
# 若返回 0 个词：音频是静音/缺失 —— 停下并修复
# 若词数少于脚本词数的 80%：音频被截断 —— 需排查
```

**6d. 视觉检查 —— 逐帧复看：**
- 背景颜色/渐变是否符合意图？（当心深色主题视频里出现白色背景）
- 图像渲染是否正确？（不是空白，不是被拉伸）
- 字幕是否可见、间距是否合适？
- 叠加层（章节标题、数据揭示）位置是否正确？
- 开场画面在视觉上够有力吗？（这对社交媒体封面很重要）
- CTA/收尾画面显示的文字对吗？（AI 生成图像中的文字经常幻觉 —— 任何必须精确的文字都用 Remotion 的 text_card）

**6e. 音频检查 —— 把转写稿与脚本比对：**
- 完整旁白都被录进去了吗？（把转写的最后一个词与脚本的最后一个词比对）
- 结尾有没有被切掉的词？（旁白超出视频时长）
- 时序对齐 —— 各旁白段是否大致对应它们预期的场景？
- 背景音乐可闻吗？（转写器可能捕获不到音乐，但 ffprobe 能确认音频流）

**6f. 汇总并向用户呈现复看结果：**

> **"[视频标题]" 的渲染后复看：**
>
> **文件：** [时长] 秒，[分辨率]，[文件大小] —— 音频流：[存在/缺失]
> **音频：** [完整/在 X 秒处被截断] —— 从渲染输出中转写出 [N]/[M] 个词
> **画面：** [已检查 N 个场景] —— [问题，或"所有场景渲染正确"]
> **字幕：** [Remotion CaptionOverlay / FFmpeg SRT / 缺失] —— [词级高亮正常 / 有问题]
> **发现的问题：** [逐条列出问题及严重程度]
>
> **建议：** [如果有需要修的，写在这里]
>
> 要我修掉这些问题并重新渲染，还是就这样可以了？

**只有在用户批准之后（或 agent 确实零问题时），这支视频才算最终版。**

### 第 6 步（旧版）：文件与内容验证

**文件验证：**
- [ ] 输出文件存在于声明的路径
- [ ] 文件大小合理（不是 0 字节，也不是小得可疑）
- [ ] 文件是合法容器（ffprobe 成功）

**内容验证：**
- [ ] 时长在目标的 ±5% 以内
- [ ] 分辨率与所选 profile 一致
- [ ] 有音频声道（立体声）
- [ ] 没有音频削波，也没有超过 1 秒的静音断层

**质量检查（由上面的自评覆盖）：**
- [ ] 视觉：所有场景画面已检查
- [ ] 音频：完整转写已验证
- [ ] 字幕：可见且时序正确

### 第 7 步：构建 Render Report

```json
{
  "version": "1.0",
  "outputs": [
    {
      "path": "renders/output.mp4",
      "format": "mp4",
      "codec": "h264",
      "resolution": "1920x1080",
      "fps": 30,
      "duration_seconds": 62.4,
      "file_size_mb": 45.2,
      "audio_codec": "aac",
      "audio_channels": 2,
      "render_strategy": "ffmpeg",
      "render_time_seconds": 180
    }
  ],
  "render_summary": {
    "total_cuts_rendered": 12,
    "subtitles_burned": true,
    "audio_tracks_mixed": 3,
    "target_duration_seconds": 60,
    "actual_duration_seconds": 62.4
  }
}
```

### 第 8 步：自评

打分（1-5）：

| 标准 | 问题 |
|-----------|----------|
| **可播放性** | 视频在标准播放器中能无错播放吗？ |
| **时长准确性** | 实际时长在目标的 ±5% 以内吗？ |
| **音频质量** | 旁白清晰、音乐平衡、没有削波吗？ |
| **画面质量** | 图像锐利、转场平滑、没有伪影吗？ |
| **字幕准确性** | 字幕存在、可读且同步吗？ |

若任何一项低于 3 分，就排查并重新渲染。

### 第 9 步：提交

**输出唯一性(硬性)**:
- `render_report.outputs` 不得包含重复产物:同一路径,或相同内容(相同 file_size_bytes + duration_seconds + resolution)只记录一次。
- 重渲染时:用新输出**替换**旧条目,绝不追加(追加会产生重复输出,校验会拦截)。
- 不同运行时/不同内容的变体(如 FFmpeg 版与 Remotion 字幕版**内容确实不同**)可并列记录,但必须内容真实不同。

按 schema 校验 render_report 并通过检查点持久化。

## 常见陷阱

- **素材文件缺失**：开始渲染之前，务必确认每个被引用的文件都存在。渲染中途缺文件就是浪费时间。
- **音画同步漂移**：跨旁白段累积的时序误差会造成音画失同步。用绝对时间戳，不要用相对偏移。
- **字幕编码**：把字幕烧进视频（硬字幕）以获得最大兼容性。社交媒体上不要依赖软字幕。
- **单遍编码**：两遍编码能在同等文件大小下获得更好画质。多花的渲染时间是值得的。
- **无视 media profile**：YouTube 和 TikTok 的要求非常不同。始终检查目标 profile。
