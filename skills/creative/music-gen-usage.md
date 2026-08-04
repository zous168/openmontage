# OpenMontage 中的音乐生成用法

> 资料来源：ElevenLabs Music API 文档、ElevenLabs 最佳实践指南、Artlist BPM
> 指南，以及位于 `.agents/skills/music/` 和 `.agents/skills/elevenlabs/` 的现有 Layer 3 技能

## 速查卡

```
API 模型：       music_v1
最短时长：       3,000ms（3 秒）
最长时长：       600,000ms（10 分钟）
纯器乐：         视频背景音乐一律设置 force_instrumental=true
成本：           每 30 秒约 $0.05
关键规则：       音乐必须比旁白低 18-20 dB（见 sound-design.md）
```

## 按视频类型选择 BPM

| 视频类型 | BPM 区间 | 提示词片段 |
|-----------|-----------|-----------------|
| 教育讲解 | 80-100 | "gentle ambient electronic, 90 BPM" |
| 企业 / 科技 | 100-120 | "upbeat corporate pop, 110 BPM, positive" |
| 史诗 / 戏剧化揭示 | 60-80 | "cinematic orchestral, 70 BPM, building tension" |
| 快节奏蒙太奇 | 120-140 | "energetic electronic, 130 BPM, driving beat" |
| 冥想 / 平静 | 50-70 | "ambient drone, 60 BPM, peaceful" |
| 喜剧 / 轻松 | 100-130 | "playful ukulele pop, 120 BPM, whimsical" |
| 忧伤 / 沉思 | 60-80 | "melancholic piano, 65 BPM, minor key" |
| 动作 / 燃 | 140-170 | "high-intensity drum and bass, 160 BPM" |

## 调性与情绪的映射

| 情绪 | 调性 | 音乐特征 |
|------|-----|----------------------|
| 欢快 / 上扬 | C 大调、G 大调 | 明亮、有解决感、有活力 |
| 严肃 / 专业 | D 小调、A 小调 | 沉稳、有权威感 |
| 神秘 / 好奇 | E 小调、B 小调 | 张力、期待 |
| 凯旋 / 鼓舞 | D 大调、降 B 大调 | 开阔、有高潮 |
| 忧郁 / 沉思 | F 小调、C 小调 | 内省、情绪化 |
| 中性 / 氛围 | C 大调、Am（无强调性） | 不喧宾夺主，适合背景 |

## 提示词工程

### 结构

```
[曲风/风格]、[BPM]、[调性/情绪]、[乐器]、[能量水平]、[用途]
```

### 示例

**教育讲解：**
```
Gentle lo-fi ambient electronic, 90 BPM, C major, soft synth pads and light
percussion, calm and steady energy, background music for narration
```

**企业产品演示：**
```
Modern upbeat corporate pop, 110 BPM, G major, acoustic guitar and light drums,
positive energy building gradually, underscore for product walkthrough
```

**技术深度解析：**
```
Minimal ambient electronic, 80 BPM, A minor, soft Rhodes piano and subtle
bass, contemplative and focused, background music for technical explanation
```

### 提示词关键规则

1. **始终写上 "background" 或 "underscore"** —— 这告诉模型在动态上保持平稳
2. **始终使用 `force_instrumental=true`** —— 歌词会与旁白争夺注意力
3. **明确指定 BPM** —— 不要指望曲风自动定下速度
4. **避免 "bright hi-hats" 或 "prominent vocals"** —— 高频繁忙元素会在 2-4 kHz 的语音可懂度频段与人声打架
5. **写明能量走向** —— 讲解类用 "steady energy"，揭示类用 "building gradually"

## 时长匹配

### 精确时长

```python
result = music_gen.execute({
    "prompt": "Gentle ambient, 90 BPM, background underscore",
    "duration_seconds": 150,  # 匹配视频长度
    "output_path": "assets/music/background.mp3"
})
```

### 分段映射（进阶）

对于有明确幕次的视频，分段生成：

| 视频段落 | 时长 | 音乐风格 |
|--------------|----------|-------------|
| 开场 / 钩子 | 8-10 秒 | 柔和、渐起 |
| 主体讲解 | 90-120 秒 | 平稳、中性 |
| 关键揭示 | 20-30 秒 | 加强、更饱满 |
| 片尾 | 10-15 秒 | 渐弱、温和 |

每段各生成一条独立音轨，在 `audio_mixer` 中做交叉淡化。

## 长视频的循环

当视频长于生成的音轨时：

1. 生成一条约为视频长度 30-60% 的音轨
2. 用 FFmpeg 做无缝循环：
   ```bash
   ffmpeg -stream_loop 2 -i music.mp3 -c copy music_looped.mp3
   ```
3. 在 `audio_mixer` 中于循环接点处加 2-3 秒交叉淡化

**更好的做法：** 按视频的确切时长直接生成。ElevenLabs 单次生成最长支持 10 分钟。

## 分轨（Stem）隔离

为了更干净地控制闪避，可以生成隔离的分轨：

- `"solo electric guitar in E minor, 90 BPM"` —— 纯吉他轨
- `"soft ambient pad in C major, 80 BPM"` —— 纯合成器铺底
- 在合成时用 FFmpeg 把分轨分层，以获得精确的闪避控制

## 应用到 OpenMontage

使用 `music_gen` 工具时：

1. **按内容类型匹配 BPM** —— 参照上表，不要退回到一句笼统的提示词
2. **始终设置 `force_instrumental=true`** —— 旁白之下不要有歌词
3. **每条提示词都写上 "background" 或 "underscore"**
4. **把时长设成与视频长度一致** —— 尽量避免循环
5. **预算核对** —— 按每 30 秒 $0.05 计，一支 3 分钟视频的音乐约 $0.30
6. **音乐比旁白闪避 18-20 dB** —— 闪避规则见 `skills/creative/sound-design.md`
7. **在 `audio_mixer` 中把音乐铺底的 2-4 kHz 切掉**，为语音可懂度频段让路
8. **在手机扬声器上测试** —— 若旁白被音乐盖住，就更激进地闪避
9. **一支视频一条音轨** —— 除非有明确的叙事转折，否则不要中途换音乐风格
