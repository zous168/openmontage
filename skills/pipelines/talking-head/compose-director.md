# 合成导演 —— Talking Head 管线

## 何时使用

你手上有剪辑决策和素材清单。你的工作是渲染最终的口播视频：施加强化链、烧录字幕、混音，并按目标档位编码。

## 运行时路由（硬约束 —— 仅 Remotion 或 FFmpeg）

Phase 1 中 HyperFrames 被推迟。`edit_decisions.render_runtime` 必须是 `"remotion"`（首选 —— 使用 `TalkingHead` 合成 + `remotion_caption_burn`）或 `"ffmpeg"`（用于源素材拼接、不做合成）。

- 若 `edit_decisions.render_runtime == "hyperframes"`，停下。重新打开 idea 阶段并把该约束呈现出来。静默改写属于治理违规。
- 按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：管线自身的约束并不能省掉这场对话。把约束呈现给用户，让他们知道 HyperFrames 是存在的，只是在这里不可行。记录一条 `render_runtime_selection` 决策，把 hyperframes 标为 `rejected_because: "TalkingHead + caption parity deferred on talking-head"`。
- 把 `proposal_packet`/`brief` 传给 `video_compose.execute()`，以便检测运行时切换。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/render_report.schema.json` | Artifact 校验 |
| 上游 artifact | 剪辑决策、素材清单 | 渲染输入 |
| 工具 | `video_compose`、`audio_mixer` | 渲染 |
| 媒体档位 | `lib/media_profiles.py` | 输出格式 |

## 流程

### 第 0 步：预检

在渲染任何东西之前，先校验输入，把那些事后修起来很贵的问题抓出来。

1. **静音检测** —— 以 mark 模式运行 `silence_cutter`：
   ```
   silence_cutter.execute({
       "input_path": "<raw_footage>",
       "mode": "mark",
       "silence_threshold_db": -35,
       "min_silence_duration": 0.5
   })
   ```
   - 报告所有 > 0.5 秒的空档及其时间戳。
   - 若静音总计 > 5 秒，**建议先剪掉再继续**。长静音会浪费渲染时间，并在成片里留下死点。

2. **ASR 置信度检查** —— 扫描词级转写，找出低置信度的词：
   - 标出任何概率 < 0.7 的词。
   - 把被标出的词连同时间戳列出来，好让用户核对转写是否正确。
   - 需要留意的常见误识：专有名词、品牌名、领域行话。

3. **自动构建纠错字典**，基于常见的 ASR 错误模式：
   ```python
   corrections = {
       # Indian finance context
       "DMI": "EMI",
       "AMI": "EMI",
       # Common brand misspellings
       "open montage": "OpenMontage",
       "remotion": "Remotion",
       # Numbers that got split by ASR
       "4 -5": "4-5",
       "10 -15": "10-15",
   }
   ```
   根据视频主题，用领域专属的纠错项扩充这个字典。施加之前，把纠错项呈现给用户复核。

4. **绿幕标记** —— 检查场景导演第 0 步是否标记了绿幕/蓝幕素材。若是，记下将会需要第 3c 步（绿幕合成）。

### 第 1 步：跑强化链

严格按此顺序施加视频强化。只要工具可用，就**每一步都尝试** —— 不要无缘无故跳过。

1. **人脸增强** —— 施加 `talking_head_standard` 预设
2. **眼部增强** —— 去黑眼圈 + 提亮眼睛
3. **调色** —— 施加一个调色档
4. **音频增强** —— 降噪、归一

**眼部增强** —— 在 face_enhance 之后一律尝试这一步。它在网络摄像头/手机素材上有肉眼可见的改善：
```
eye_enhance.execute({
    "input_path": "<face_enhanced_video>",
    "output_path": "<project>/assets/video/eye_enhanced.mp4",
    "operations": ["dark_circles", "brighten_eyes"],
    "dark_circle_intensity": 0.4,       # 0-1, subtle is better
    "eye_brighten_intensity": 0.3,
})
```
**重要：** 强度保持低位（0.2-0.5）。处理过度会让眼睛显得不自然。若工具失败（例如没装 MediaPipe），记录降级并继续使用 face_enhanced 的视频。

### 第 1b 步：变速调整（若有要求）

若用户想把视频加速或放慢，用 `video_trimmer`：
```
video_trimmer.execute({
    "operation": "speed",
    "input_path": "<enhanced_video>",
    "output_path": "<project>/assets/video/speed_adjusted.mp4",
    "speed_factor": 1.25    # 0.5x (slow), 1.25x, 1.5x, 2x (fast)
})
```

常见的变速系数：
| 系数 | 使用场景 |
|--------|----------|
| `0.5` | 慢动作，用于戏剧效果 |
| `1.0` | 正常（不变） |
| `1.25` | 略快 —— 收紧节奏，同时听感仍然自然 |
| `1.5` | 明显更快 —— 适合回顾或压缩型内容 |
| `2.0` | 双倍速 —— 延时摄影效果 |

在强化处理**之后**、重新构图**之前**施加变速。

### 第 2 步：自动重新构图（若目标平台需要）

若目标平台要求不同的画幅比（例如 Instagram Reels = 9:16），用 `auto_reframe`：

```
auto_reframe.execute({
    "input_path": "<enhanced_video>",
    "output_path": "<project>/renders/reframed.mp4",
    "target_aspect": "portrait",       # 9:16 for Reels/TikTok/Shorts
    "smoothing_window": 15,            # smooth camera pan
    "face_padding": 0.4,              # 40% padding around face
})
```

**画幅比预设：**
| 预设 | 比例 | 平台 |
|--------|-------|----------|
| `portrait` | 9:16 | Instagram Reels、TikTok、YouTube Shorts |
| `square` | 1:1 | Instagram 信息流 |
| `landscape` | 16:9 | YouTube、LinkedIn |
| `vertical_4_5` | 4:5 | Instagram 竖版帖子 |

该工具会自动跑人脸检测，让说话人保持居中。若未安装 MediaPipe，会降级为居中裁切。

**重要：** auto_reframe 要在 face_enhance 和 color_grade **之后**、烧录字幕**之前**运行。字幕需要按最终画幅比来定位。

### 第 2b 步：构建 ASR 纠错字典

烧录字幕之前，扫描转写，找出可能的 ASR 误识。常见问题：
- 产品/品牌名："cloud" → "Claude"、"co-pilot" → "Copilot"、"remotion" → "Remotion"
- 技术术语："pythonic" 被听成 "pathonic"、"API" 被听成 "a pie"
- 说话人姓名或公司名
- 领域专属行话

构建一个纠错字典：
```python
corrections = {
    "cloud": "Claude",
    "co pilot": "Copilot",
    "open montage": "OpenMontage",
}
```

把这个字典同时传给 `subtitle_gen`（若要生成 SRT）和 `remotion_caption_burn`（若使用 Remotion 字幕）。即便你发现一处纠错都不需要，也要显式传一个空字典 `{}`，以确认你查过了。

### 第 3 步：烧录字幕

**一律使用 Remotion 的 TikTok 风格字幕**（逐词高亮）。这是默认且首选的方式。除非 Remotion 完全不可用，**不要**退回 FFmpeg 的 ASS 字幕。

**Remotion 字幕的要求：**
- **自动检测视频尺寸** —— **不要**把宽高写死。用 `visual_qa` 探测或 ffprobe 拿到真实尺寸，再把它们传给渲染。
- **按实际视频时长设 `--frames`** —— 由探测结果算出：`frames = duration_seconds * fps`。绝不要用写死的帧数。
- 逐词高亮，当前词使用高亮色（`highlight_color`）。
- 字幕定位在画面底部，远离面部。

```
remotion_caption_burn.execute({
    "input_path": "<reframed_or_enhanced_video>",
    "output_path": "<project>/assets/video/captioned.mp4",
    "segments": <transcript_segments_from_asset_manifest>,
    "corrections": {"cloud": "Claude", "co-pilot": "Copilot"},
    "words_per_page": 4,
    "font_size": 52,
    "highlight_color": "<theme_accent>",
})
```

**仅当 Remotion 完全不可用时的降级方案：** 用 `video_compose` 的 `burn_subtitles` 操作。这是降级体验 —— 要提醒用户逐词高亮将不可用。

**关键：9:16 竖屏视频的字幕定位（仅限 FFmpeg 降级路径）。**
字幕**必须**位于画面下方 20% 的区域。在 1920 高的画面上，这意味着 `MarginV=160` 或更高。FFmpeg 字幕的默认位置是居中 —— 那**一定**会遮住面部。你**必须**覆写它。

竖屏口播用的 FFmpeg 字幕样式串：
```
"FontName=Arial,FontSize=22,Bold=1,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Shadow=0,MarginV=160,Alignment=2"
```

**绝不要**使用默认字幕位置。**绝不要**把字幕放在画面中央或上半部。若你在视觉 QA 中看到字幕压在脸上，这支视频必须以修正后的定位重新渲染。

### 第 3b 步：烧录叠加图形（若场景方案含叠加层）

若场景方案里含有叠加层场景（text_cards、stat_cards、图表、对比、标注），就把它们与字幕一起传给 `remotion_caption_burn`。**字幕与叠加层在同一次 Remotion 渲染中一并完成** —— 不需要另做 FFmpeg 合成。

**它是怎么工作的：** TalkingHead 的 Remotion 合成会渲染三层：
1. **视频**（底层）—— 口播素材
2. **叠加层**（中层）—— 定位好的图表、数据、标注，带淡入/淡出
3. **字幕**（顶层）—— 逐词高亮，始终可见

**把第 3 步和第 3b 步合并成一次 `remotion_caption_burn` 调用：**
```
remotion_caption_burn.execute({
    "input_path": "<reframed_or_enhanced_video>",
    "output_path": "<project>/assets/video/captioned.mp4",
    "segments": <transcript_segments>,
    "corrections": {"cloud": "Claude"},
    "words_per_page": 4,
    "font_size": 52,
    "highlight_color": "<theme_accent>",
    "overlays": [
        {
            "id": "term-agentic-ai",
            "type": "callout",
            "text": "Agentic AI: software that acts autonomously toward goals",
            "callout_type": "info",
            "in_seconds": 22.0,
            "out_seconds": 26.0,
            "position": "lower_third",
            "backgroundColor": "<theme_background>",
            "accentColor": "<theme_accent>"
        },
        {
            "id": "stat-market-size",
            "type": "stat_card",
            "stat": "$4.8B",
            "subtitle": "Global AI Agent Market (2026)",
            "in_seconds": 35.0,
            "out_seconds": 39.0,
            "position": "upper_third",
            "accentColor": "<theme_secondary_accent>"
        },
        {
            "id": "chart-growth",
            "type": "bar_chart",
            "chartData": [
                {"label": "2023", "value": 1.2},
                {"label": "2024", "value": 2.1},
                {"label": "2025", "value": 3.5},
                {"label": "2026", "value": 4.8}
            ],
            "title": "AI Agent Market ($B)",
            "in_seconds": 40.0,
            "out_seconds": 45.0,
            "position": "lower_third",
            "chartColors": ["<theme_accent>", "<theme_secondary_accent>", "<theme_tertiary_accent>", "<theme_supporting_accent>"]
        }
    ]
})
```

**叠加层位置选项：**
- `lower_third` → 底部区域，位于字幕之上（默认 —— 对多数叠加层最安全）
- `upper_third` → 顶部区域（说话人居中/偏下时，适合放数据）
- `left_panel` → 画面左侧 45%（与说话人并排）
- `right_panel` → 画面右侧 45%
- `full_overlay` → 带深色底的全屏（节制使用，最多 1-2 秒）

**叠加层类型 → 必需 props**（与素材导演的映射相同）：

| 类型 | 必需 props |
|------|---------------|
| `text_card` | `text` |
| `stat_card` | `stat`、`subtitle`（可选） |
| `callout` | `text`、`callout_type`（info/warning/tip/quote） |
| `comparison` | `leftLabel`、`rightLabel`、`leftValue`、`rightValue` |
| `bar_chart` | `chartData`（`{label, value}` 数组） |
| `line_chart` | `chartSeries`（`{name, data: number[]}` 数组） |
| `pie_chart` | `chartData`（`{label, value}` 数组） |
| `kpi_grid` | `chartData`（`{label, value}` 数组） |
| `hero_title` | `text`、`subtitle`（可选） |
| `section_title` | `text`、`subtitle`（可选） |
| `stat_reveal` | `text`（数据本身）、`subtitle`（标签） |

**重要：** 做过变速调整之后，要重算叠加层时间戳：`adjusted_time = original_time / speed_factor`。

**降级（没有 Remotion）：** 若 Remotion 不可用，`remotion_caption_burn` 会降级到 FFmpeg，且只做字幕。在 FFmpeg 降级模式下**不会**渲染叠加层 —— 要提醒用户叠加层需要 Remotion。

### 第 3c 步：绿幕合成（若素材是绿幕）

若素材带绿幕/蓝幕（在场景导演第 0 步中检测到），按以下管线操作：

1. **运行 `green_screen_processor` 工具**去除绿幕/蓝幕：
   ```
   green_screen_processor.execute({
       "input_path": "<enhanced_video>",
       "output_path": "<project>/assets/video/greenscreen_removed.mp4",
       "method": "auto"
   })
   ```
   `auto` 方式会检测背景是绿是蓝，并施加对应的色键。

2. **用 Explainer 合成渲染 Remotion 动态背景**：
   ```
   # Render an AnimatedBackground clip (gradient mesh, floating orbs, subtle grid)
   # Use the Explainer composition — NOT a flat #0F172A solid color
   npx remotion render src/index.ts Explainer --props='{"duration":VIDEO_DURATION}' --output=<project>/assets/video/animated_bg.mp4
   ```
   AnimatedBackground 提供的是带漂浮光球和淡网格图案的专业渐变网格。这远优于一块纯色平面。

3. **运行 `green_screen_composite` 工具**，把说话人叠到动态背景上：
   ```
   green_screen_composite.execute({
       "foreground_path": "<greenscreen_removed_video>",
       "background_path": "<animated_bg>",
       "output_path": "<project>/assets/video/composited.mp4",
       "layout": "news_anchor"
   })
   ```
   默认版式是 `news_anchor`（说话人居中偏下，背景铺满画面）。根据第 0 步检测到的说话人位置调整版式。

4. **经由 Remotion TalkingHead 合成烧录字幕**（**不是** FFmpeg 的 ASS 字幕）：
   ```
   remotion_caption_burn.execute({
       "input_path": "<composited_video>",
       "output_path": "<project>/assets/video/captioned.mp4",
       "segments": <transcript_segments>,
       "corrections": <corrections_dict>,
       "words_per_page": 4,
       "font_size": 52,
        "highlight_color": "<theme_accent>",
       "overlays": <overlay_list_from_scene_plan>
   })
   ```

5. **混入背景音乐**（在语音下方闪避至 15% 音量）：
   ```
   audio_mixer.execute({
       "operation": "duck",
       "video_path": "<captioned_video>",
       "music_path": "<bg_music>",
       "music_volume": 0.15,
       "output_path": "<project>/assets/video/with_music.mp4"
   })
   ```

6. **最终编码**到目标平台规格（见下方第 6 步）。

### 第 3d 步：制作 Showcase 卡片（若是多片段合辑）

若输出是一支带 showcase 片段的合辑，为每一个片段用 `showcase_card`：
```
showcase_card.execute({
    "input_path": "<showcase_video>",
    "output_path": "<project>/assets/video/sc_<name>.mp4",
    "title": "VIDEO TITLE",
    "subtitle": "Description | Style | Cost: $0.15",
    "background_color": "0x0A0F1A",
})
```
这会生成带字体排印的 9:16 加黑边卡片。

### 第 4 步：多片段组装（若适用）

若输出包含多个片段（例如口播 + showcase 片段），用 `video_stitch`：
```
video_stitch.execute({
    "operation": "stitch",
    "clips": ["intro.mp4", "showcase1.mp4", ..., "outro.mp4"],
    "output_path": "<project>/renders/assembled.mp4",
    "transition": "crossfade",         # or "fade" for fade-through-black
    "transition_duration": 0.5,
})
```
**转场指引：**
- `crossfade`（叠化）：口播与 showcase 之间的平滑过渡
- `fade`（过黑淡入淡出）：showcase 片段之间短暂压黑
- 混用转场类型：口播→showcase 用 `crossfade`，showcase 之间用 `fade`

### 第 5 步：混音

用 `audio_mixer` 铺上背景音乐：

**对多片段合辑** —— 用 `segmented_music`，让音乐只在口播段落播放：
```
audio_mixer.execute({
    "operation": "segmented_music",
    "video_path": "<assembled_video>",
    "music_path": "<bg_music>",
    "music_volume": 0.20,
    "segments": [
        {"start": 0, "end": 17.0},       # intro speech
        {"start": 167.0, "end": 175.0}    # outro speech
    ],
    "fade_duration": 0.5,
    "output_path": "<project>/renders/final.mp4",
})
```

**对单支口播视频** —— 用 `duck` 或 `full_mix`：
- 把原始音频与背景音乐叠层
- 有音乐时施加闪避
- 对最终电平做归一

### 第 6 步：最终编码 —— 强制

**不要跳过这一步。** 没有最终编码，输出会体积过大，且可能在目标平台上播放异常。

用 `video_compose` 的 `encode` 操作：
- 施加目标媒体档位（youtube_landscape、tiktok、instagram_reels 等）
- 用两遍编码保证质量

**目标文件大小：**
| 平台 | 最大时长 | 目标体积 |
|----------|-------------|-------------|
| Instagram Reels | 90 秒 | < 50 MB |
| TikTok | 10 分钟 | < 100 MB |
| YouTube Shorts | 60 秒 | < 40 MB |
| YouTube | 不限 | < 25 MB/分钟 |

若输出超出目标，就用更低码率重新编码。一支 66 秒的 Instagram Reel 做到 76 MB 是不可接受的 —— 它应当在 30 MB 以内。

```
video_compose.execute({
    "operation": "encode",
    "input_path": "<mixed_video>",
    "output_path": "<project>/renders/final.mp4",
    "media_profile": "instagram_reels",
    "video_bitrate": "4M",
    "audio_bitrate": "192k",
})
```

### 第 7 步：视觉 QA

在宣布成功之前，用 `visual_qa` 校验输出：
```
visual_qa.execute({
    "operation": "review",
    "input_path": "<final_video>",
    "timestamps": [3.0, 10.0, 25.0, 50.0, 100.0, 170.0],
})
```
然后**逐张读取抽出的帧**来确认：
- 字幕可见且位于底部（没有压在脸上）
- 人脸增强已施加（皮肤看着平滑，但没有处理过度）
- 转场干净（转场点没有瑕疵）
- Showcase 卡片的字体排印可读

同时跑探测校验：
```
visual_qa.execute({
    "operation": "probe",
    "input_path": "<final_video>",
    "expected": {
        "width": 1080, "height": 1920,
        "has_audio": true,
        "pixel_format": "yuv420p"
    },
})
```

并检查音频电平：
```
visual_qa.execute({
    "operation": "audio_levels",
    "input_path": "<final_video>",
    "timestamps": [5.0, 50.0, 170.0],
})
```
确认：语音段落的音量高于 showcase 段落（这印证了音乐的铺放位置正确）。

### 第 8 步：搭建 Render Report

记录输出：路径、格式、分辨率、时长、文件大小、QA 结果。

### 第 9 步：自评

| 判据 | 问题 |
|-----------|----------|
| **可播放性** | 视频能无错播放吗？ |
| **质量** | 强化处理施加正确吗？ |
| **构图** | 若做过重新构图 —— 面部居中吗？有没有裁掉重要内容？ |
| **音频** | 语音清晰、电平均衡吗？音乐只在预期段落出现吗？ |
| **字幕** | 字幕在底部可见吗？没遮住脸吗？逐词高亮生效了吗？ |
| **转场** | 转场干净吗？类型对吗（crossfade 还是 fadeblack）？ |
| **Showcase** | Showcase 卡片加黑边是否得当？字体排印可读吗？ |

### 第 10 步：提交

对照 schema 校验 render_report，并通过检查点持久化。

**输出唯一性(硬性)**:
- `render_report.outputs` 不得包含重复产物:同一路径,或相同内容(相同 file_size_bytes + duration_seconds + resolution)只记录一次。
- 重渲染时:用新输出**替换**旧条目,绝不追加(追加会产生重复输出,校验会拦截)。
- 不同运行时/不同内容的变体(如 FFmpeg 版与 Remotion 字幕版**内容确实不同**)可并列记录,但必须内容真实不同。

