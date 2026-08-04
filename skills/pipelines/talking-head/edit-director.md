# 剪辑导演 —— Talking Head 管线

## 何时使用

你手上有一份场景方案和素材清单。你的工作是为口播视频组装剪辑决策表：主要是保留完整素材，叠上字幕，并施加可选的强化处理。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact 校验 |
| 上游 artifact | 场景方案、素材清单、脚本 | 剪辑输入 |
| Playbook | 当前生效的风格 playbook | 转场与节奏规则 |

## 流程

### 第 1 步：施加静音剪切（若已规划）

若场景方案里含有静音删除，就在定义各刀之前先跑 `silence_cutter`：

```
silence_cutter.execute({
    "input_path": "<raw_footage>",
    "mode": "remove",           # or "speed_up" for less jarring result
    "silence_threshold_db": -35,
    "min_silence_duration": 0.5,
    "padding_seconds": 0.08,    # prevents clipped words
    "output_path": "<project>/assets/video/footage_cut.mp4"
})
```

**如何选模式：**
- `remove` —— 硬跳切。最适合快节奏的社交内容（Reels、TikTok、Shorts）
- `speed_up` —— 以 6 倍速快进掠过静音。对长视频内容（YouTube、LinkedIn）观感更不突兀

把结果呈现给用户："删掉了 X 秒静音（Y%）—— 现在输出是 Z 秒。"

把剪过的素材作为后续所有步骤的源。

### 第 2 步：定义主剪辑

对 talking-head 而言，主剪辑通常就是完整素材（或裁切后的片段）。创建的各刀应当：
- 以原始素材（或静音剪切后的素材）为源
- 使用来自脚本 section 的时间戳
- 施加任何裁切决策（剪掉空白、口误重来）

### 第 3 步：配置字幕

- 启用字幕，样式与 playbook 相容
- 引用清单中的字幕素材
- 设定位置（通常是底部居中）

### 第 4 步：配置音频

- 把旁白设为原始素材的音频
- 若需要背景音乐，配置好闪避
- 按 playbook 设定音乐音量

### 第 5 步：规划强化处理

若场景方案里含有叠加层：
- 为文字卡、下三分之一条添加叠加层刀口
- 把它们与语音内容对时

### 第 6 步：自评

| 判据 | 问题 |
|-----------|----------|
| **覆盖度** | 各刀覆盖了完整的目标时长吗？ |
| **静音** | 若已规划，静音剪切施加了吗？删掉了百分之多少？ |
| **字幕** | 字幕启用了、也设了样式吗？ |
| **音频** | 音频配置完整吗？ |

### 第 7 步：提交

对照 schema 校验 edit_decisions，并通过检查点持久化。
