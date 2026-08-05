# 剪辑导演 —— Explainer 管线

## 何时使用

你是一支生成式讲解视频的剪辑师。你手上有一份包含全部生成文件的 `asset_manifest`、一份带视觉结构的 `scene_plan`，以及一份带时序的 `script`。你的工作是装配剪辑决策表（EDL）：什么时候播什么、元素如何分层、字幕放在哪里，以及音乐和旁白如何相互作用。

正是在这里，零散素材变成一支连贯的视频。好的剪辑能让普通素材发光；糟糕的剪辑会浪费掉优秀素材。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["assets"]["asset_manifest"]`、`state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]` | 素材、视觉方案、时序 |
| Playbook | 当前生效的风格 playbook | 转场、节奏规则、叠加样式 |

## 流程

### 第 1 步：把素材映射到时间线

对场景方案中的每个场景：
1. 从 asset manifest 中找出匹配的素材（按 `scene_id`）
2. 找出匹配的旁白音频（按脚本段落）
3. 记下该场景的时序（`start_seconds`、`end_seconds`）

构建一张时间线映射表：
```
0s-10s: scene-1 (talking_head) | narration-s1 | img-intro.png
10s-18s: scene-2 (diagram) | narration-s2 | diagram-flow.svg
18s-22s: scene-3 (text_card) | narration-s3 | [text overlay]
...
```

### 第 2 步：定义剪辑点

每个剪辑点定义展示什么画面、何时展示：

```json
{
  "id": "cut-1",
  "source": "img-scene-1",
  "in_seconds": 0,
  "out_seconds": 10,
  "layer": "primary",
  "transform": {
    "scale": 1.0,
    "position": "center",
    "animation": "ken-burns-slow-zoom"
  },
  "transition_in": "fade",
  "transition_out": "dissolve",
  "transition_duration": 0.4
}
```

**分层规则：**
- `primary` —— 主画面（同一时刻只有一个）
- `overlay` —— 文字卡、数据卡、关键术语（叠在 primary 之上）
- `background` —— 所有内容之后的纯色或纹理

### 第 3 步：配置字幕

字幕对所有讲解内容都是强制的：

```json
{
  "subtitles": {
    "enabled": true,
    "style": "word-by-word",
    "font": "Inter",
    "font_size": 48,
    "color": "#FFFFFF",
    "background": "#00000088",
    "position": "bottom-center",
    "max_words_per_line": 8
  }
}
```

**字幕时序**：从旁白音频的时间戳推导。每个词应当在被说出时高亮（逐词样式），或按短语块显示（短语样式）。

字体选择使用 playbook 的排版设定。

### 第 4 步：配置音频层

```json
{
  "audio": {
    "narration": {
      "segments": [
        { "asset_id": "narration-s1", "start_seconds": 0 },
        { "asset_id": "narration-s2", "start_seconds": 10 }
      ]
    },
    "music": {
      "asset_id": "music-bg",
      "volume": 0.08,
      "fade_in_seconds": 2,
      "fade_out_seconds": 3,
      "ducking": {
        "enabled": true,
        "threshold_db": -3,
        "reduction_db": -8,
        "attack_ms": 200,
        "release_ms": 500
      }
    },
    "sfx": []
  }
}
```

**音乐闪避**：旁白响起时音乐音量下降，停顿时回升。使用 playbook 的 `audio.ducking_threshold_db`。

### 第 5 步：应用节奏规则

检查 playbook 的 `motion.pacing_rules`：
- 没有剪辑点短于 `min_scene_hold_seconds`
- 没有剪辑点长于 `max_scene_hold_seconds`
- 文字卡停留 `text_card_hold_seconds`
- 转场使用 `transition_duration_seconds`

若有任何一项违反这些规则，就调整剪辑时序。

### 第 6 步：核查剪辑完整性

**时间线覆盖：**
- [ ] 剪辑点覆盖完整视频时长（没有黑帧）
- [ ] 没有重叠的 primary 剪辑点
- [ ] scene_plan 中的每个场景都至少有一个对应剪辑点

**素材引用：**
- [ ] 每个剪辑点的 `source` 都引用 manifest 中一个有效的 asset_id
- [ ] 每个旁白段都引用一个有效的音频素材
- [ ] 音乐素材存在

**音频同步：**
- [ ] 旁白段有序且不重叠
- [ ] 旁白时序与对应的画面剪辑点对齐
- [ ] 已配置音乐闪避

**字幕：**
- [ ] 字幕已启用
- [ ] 字幕样式使用与 playbook 兼容的字体和颜色

### 第 7 步：自评

打分（1-5）：

| 标准 | 问题 |
|-----------|----------|
| **连续性** | 视频的每一秒都有画面吗？ |
| **节奏** | 剪辑点是否遵循 playbook 的时序规则？ |
| **音画同步** | 每一刻你看到的和你听到的是否一致？ |
| **字幕质量** | 字幕可读、时序正确吗？ |
| **转场连贯性** | 转场是否落在 playbook 允许的集合内？ |

若任何一项低于 3 分，就修订。

### 第 8 步：提交

按 schema 校验 edit_decisions artifact 并通过检查点持久化。

## 常见陷阱

- **忘了空缺**：若 scene-1 在 10 秒结束而 scene-2 在 10.5 秒开始，中间就有 0.5 秒黑帧。检查空缺。
- **音频漂移**：旁白音频可能比计划稍长或稍短。要按**实际**旁白时长而不是计划时长去调整画面剪辑点。
- **没有闪避**：旁白之下音乐满音量播放，会让视频没法看。始终配置闪避。
- **到处用同一个转场**：变换转场能制造律动。用 playbook 允许的集合，但不要每个剪辑点都用同一个。
- **字幕字体不匹配**：字幕应当使用 playbook 的正文字体，而不是某个随意的默认值。
