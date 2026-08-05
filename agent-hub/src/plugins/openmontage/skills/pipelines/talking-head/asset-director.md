# 素材导演 —— Talking Head 管线

## 何时使用

你手上有一份场景方案和脚本。你的工作是为口播视频生成配套素材：字幕、提取出的音频、叠加层图形（图表、文字卡、数据揭示），以及任何补充视觉物。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact 校验 |
| 上游 artifact | 场景方案、脚本 | 要做哪些素材 |
| 工具 | `subtitle_gen`、`audio_mixer` | 字幕与音频生成 |
| 工具 | `image_selector`（可选） | 用于叠加层的图库图片 |
| 工具 | `pixabay_music`（可选） | 免版税背景音乐 |

## 流程

### 第 0 步：主场景样片（强制）

在批量生成素材之前：
1. 指认主场景（整支视频的视觉高点）
2. 只为该场景生成**一件**样例素材（字幕样式、叠加层，或背景）
3. 呈现它："这是最重要那个场景的视觉方向。和你想的一致吗？我会照这个风格把其余的生成出来。"
4. 等审批通过，再进入批量生成

这能避免最昂贵的错误：照着用户不喜欢的方向生成 10 件以上素材。

### 第 1 步：生成字幕

用 script 阶段的转写数据来创建：
- 带词级时序的 SRT 或 ASS 字幕文件
- 按 playbook 设定字幕样式（字体、字号、颜色、位置）

若场景方案里含有 `corrections` 字典，就把它传给 `subtitle_gen`：
```
subtitle_gen.execute({
    "segments": <transcript_segments>,
    "corrections": {"cloud": "Claude"},
    "max_words_per_line": 5,
    "output_path": "<project>/assets/subtitles/subtitles.srt"
})
```

### 第 2 步：提取并处理音频

- 从原始素材中提取音轨
- 有需要时施加降噪（经由 `audio_mixer`）
- 让音频电平归一

### 第 3 步：取得背景音乐

若场景方案里含有背景音乐：

1. **查本地 pixabay 音乐库** —— 找已下载的、与情绪相符的 MP3
2. **用 `pixabay_music` 工具** —— 按场景方案中的情绪/风格关键词搜索
3. **对选定曲目跑 `audio_energy` 分析**，找出最佳起始偏移（跳过安静的前奏）

把音乐路径、偏移量，以及是否需要循环，记录到素材清单中。

### 第 4 步：生成叠加层素材

若场景方案里含有叠加层场景（来自场景导演的「看素材并提方案」步骤），就为每一个生成素材。

**对 Remotion 渲染的叠加层**（图表、对比、KPI 网格、数据卡）：

为每个叠加层创建一段合成 JSON 片段。它们将由合成导演渲染。每个叠加层都需要：

```json
{
  "overlay_id": "overlay_1",
  "remotion_cut": {
    "id": "term-agentic-ai",
    "type": "callout",
    "text": "Agentic AI: software that acts autonomously toward goals",
    "in_seconds": 0,
    "out_seconds": 4,
    "backgroundColor": "<theme_background>",
    "accentColor": "<theme_accent>",
    "icon": "💡"
  },
  "overlay_timestamp": 22.0,
  "position": "lower_third"
}
```

**叠加层类型 → Remotion cut 的映射：**

| 场景方案中的叠加层 | Remotion `type` | 必需 props |
|-------------------|-----------------|----------------|
| 关键术语释义 | `callout` | `text`、`icon`（可选） |
| 统计/数字 | `stat_card` | `stat`（数字本身）、`text`（标签） |
| 对比 | `comparison` | `leftLabel`、`rightLabel`、`leftValue`、`rightValue` |
| 数据图表 | `bar_chart` | `chartData`（`{label, value}` 数组） |
| 饼图 | `pie_chart` | `chartData`（`{label, value}` 数组） |
| 折线图 | `line_chart` | `chartSeries`（`{name, data: number[]}` 数组） |
| KPI 仪表盘 | `kpi_grid` | `chartData`（`{label, value}` 数组）—— 数字要小，用后缀（例如 "2.4M"） |
| 进度指示 | `progress_bar` | `progress`（0-100）、`text` |
| 段落标题 | `hero_title` | `text`、`subtitle`（可选） |
| 标注/引语 | `callout` | `text`、`icon` |
| 下三分之一条 | `text_card` | `text` |

**Remotion AnimatedBackground：**

Explainer 合成现在包含一个 `AnimatedBackground` 组件，它会渲染动态渐变网格、漂浮光球和一层淡淡的网格图案。它比纯色平面背景专业得多。

- 场景背景应当使用当前生效的主题背景色，好让 AnimatedBackground 与叠加层卡片看起来是同一套体系。
- **不要**给背景用任意的纯色 —— 让 AnimatedBackground 与主题去决定这层处理。
- 合成绿幕素材时，把 AnimatedBackground 作为替换背景来渲染（见 compose-director 第 3c 步）。

**组件约束：**

| 组件 | 最小宽度 | 720px 竖屏可用？ | 值类型 |
|-----------|-----------|-----------------|------------|
| comparison | 900px | 否 -> 改用 2 个 stat_card | string |
| kpi_grid | 720px | 是 | 仅 numeric（不能写 "15+"） |
| bar_chart | 500px | 是 | numeric |
| stat_card | 300px | 是 | string 可以 |
| callout | 400px | 是 | string |
| hero_title | 400px | 是 | string |
| line_chart | 500px | 是 | numeric |
| progress_bar | 600px | 是 | numeric |
| stat_reveal | 300px | 是 | string 可以 |

关键规则：
- `comparison` 需要 900px 以上宽度。在 720px 的竖屏画面中，改用两个依次出现的 `stat_card`。
- `kpi_grid` 的值**必须**是纯数字（例如 `4.8`、`73`、`2400`）。像 `"15+"`、`"$4.8B"` 或 `"2.4M"` 这样的格式化字符串会导致渲染报错。带字符串格式的数字请改用 `stat_card`。
- 选组件之前，一律先确认目标画面宽度。竖屏（720px）排除 `comparison`。

**叠加层主题规则** —— 叠加层的背景、强调色和文字颜色，都要从选定的 playbook 或自定义识别体系推导。只有当素材/主题需要时才用深色卡片；一场明亮的编辑部风格演讲，完全可以合理地用浅色卡片，只要对比度依然够强。

**对简单文字叠加层**（Remotion 显得杀鸡用牛刀时）：

用 FFmpeg 或 PIL 生成 PNG 图片，存放于 `<project>/assets/overlays/overlay_<id>.png`。

### 第 5 步：搭建素材清单

把所有生成出来的素材连同路径、类型和工具引用记录下来：

```json
{
  "subtitles": {
    "path": "assets/subtitles/subtitles.srt",
    "format": "srt",
    "word_count": 208
  },
  "music": {
    "path": "assets/audio/bg_music.mp3",
    "offset_seconds": 3.5,
    "needs_loop": true
  },
  "overlays": [
    {
      "overlay_id": "overlay_1",
      "type": "callout",
      "timestamp": 22.0,
      "duration": 4.0,
      "remotion_cut": { ... },
      "position": "lower_third"
    }
  ],
  "transcript_segments": "assets/audio/transcript.json"
}
```

### 第 6 步：自评

| 判据 | 问题 |
|-----------|----------|
| **字幕** | 字幕存在吗？与语音时序相符吗？ |
| **音频** | 音频干净、已归一了吗？ |
| **音乐** | 是否对音乐跑了 audio_energy 来找最佳偏移？ |
| **叠加层** | 场景方案中的每个叠加层都有对应生成的素材吗？ |
| **叠加层内容** | 叠加层里的数据与说话人实际所说的一致吗？ |
| **文件** | 所有素材路径都指向真实存在的文件吗？ |

### 第 7 步：提交

对照 schema 校验 asset_manifest，并通过检查点持久化。

### 生产中途的事实核验

若你在生成素材过程中遇到不确定：
- 用 `web_search` 核验主体的视觉准确性（例如：这栋建筑实际长什么样？）
- 在生成插画之前，用 `web_search` 找参考图
- 把核验记入 decision log：`category="visual_accuracy_check"`

视觉准确性很重要。若脚本提到了某个具体地点、人物或物件，
就在生成图像之前先核实它实际长什么样。不要依赖
AI 模型的训练数据 —— 它可能是错的或过时的。

## 当你不知道该怎么做时

若你遇到某种拿不准的生成技法、provider 行为或提示词模式：

1. **上网搜索**当前最佳实践 —— 模型和 API 变化频繁，agent 的训练数据可能已过时
2. **查 `.agents/skills/`** 里已有的 Layer 3 知识（provider 专属提示词指南、API 模式）
3. **若两者都无解**，就在 `projects/<project-name>/skills/<name>.md` 写一份项目级技能，记录你学到的东西
4. **在技能中引用来源 URL**，让知识可追溯
5. **记录它**到 decision log：`category: "capability_extension"`、`subject: "learned technique: <name>"`

以下情形尤其重要：
- **视频生成提示词** —— 模型对特定词汇有反应，而这些词汇每个版本都在变
- **图像模型参数** —— FLUX、GPT Image、Imagen 的最优设置各不相同，且在演进
- **音频 provider 的怪癖** —— 声音克隆、音乐生成和 TTS 各有其模型专属的最佳实践
- **Remotion 组件模式** —— 随着框架演进，会出现新的合成技法

不要依赖陈旧知识。拿不准时，先搜索。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
