# 创意导演 —— Cinematic 管线

## 何时使用

预告片、品牌片、戏剧化蒙太奇，或任何律动、氛围和情绪递进比直接讲解更重要的情绪主导短片，都用本管线。

不要仅仅因为用户说了一句"做得电影感一点"就用本管线。若这个项目其实是屏幕演示、讲解视频或素材再利用，就把它导向相应管线。

## 参考输入

- `docs/cinematic-best-practices.md`
- `skills/creative/cinematic.md`
- `skills/creative/storytelling.md`

## 流程

### 1. 归类源素材实况

记录源素材模式：

- `footage_only`
- `footage_plus_stills`
- `still_led`
- `generated_support`
- `mixed_montage`

同时判断所要求的交付是否要求必须有运动。把它作为布尔值存进 `brief.metadata.motion_required`。

当视频的承诺依赖运动镜头或动画合成而非静帧时，设 `motion_required = true`。这包括：

- 科幻预告片，
- 电影感先导片，
- 动作或燃向剪辑，
- agent/数字人产出，
- 任何质量取决于生成视频片段的概念。

除非用户已经提供，或环境确实能做出来，否则不要假定存在素材库画面、生成的 b-roll 或音乐。

### 2. 定义情绪弧线

用平实语言选定弧线：

- 紧张 -> 揭示
- 惊叹 -> 尺度
- 亲密 -> 回报
- 紧迫 -> 解决
- 悬念 -> CTA

brief 应当告诉后续阶段这支视频想让观众**感受到**什么，而不只是它讲什么。

### 3. 选定交付形态

常见的输出形态：

- `teaser`
- `trailer`
- `hero_brand_film`
- `mood_cut`
- `social_cutdown`

把更长的规划细节放进 `brief.metadata`。

推荐的元数据键：

- `source_mode`
- `motion_required`
- `delivery_shape`
- `emotional_arc`
- `anchor_assets`
- `music_strategy`
- `generated_support_level`
- `aspect_ratio_plan`
- `rights_constraints`

### 4. 对处理方式做现实核查

若用户的源素材很弱、又没有生成路径，就明说。电影感的结果仍然需要足够的视觉或音频材料来承载情绪。

若 `motion_required = true`，就把运动路径写明白：

- 确认计划使用的片段生成 provider，
- 确认预期的合成是否需要 Remotion，
- 若两者之一不可用或不稳定，就把该处理方式标记为受阻，而不是静默地围绕静图重新设计它。

### 5. 音乐方案（必备）

电影感视频的成败系于它的音频。**在用户批准 brief 之前，把音乐的情况摆出来。**

按此顺序检查可用性：

1. **用户音乐库（`music_library/`）：** 检查这个目录是否存在、是否有曲目。列出可用曲目及其时长和情绪。让用户来选。
2. **音乐生成 API：** 检查 `registry.get_by_capability("music_generation")`。报告状态、配额和每首成本。
3. **免版税来源：** 说明用户可以从 YouTube Audio Library、Jamendo 或其他免费来源取一首曲子放进 `music_library/`。

呈现明确的选项：

```
音乐方案
├── 你的音乐库：[N 首 / 空]
├── AI 生成：[provider] —— [可用/不可用] [成本]
└── 自带音乐：在 assets 阶段之前把曲子放进 music_library/

选项：
  (a) 用音乐库里的一首（哪一首？）
  (b) 自己提供一首
  (c) 通过 API 生成（若可用）
  (d) 不用音乐继续（电影感作品不推荐）
```

把决定连同选定的来源和路径/提示词记入 `brief.metadata.music_strategy`。

### 6. 质量门

- 源素材的实况明确，
- brief 写明了运动是否为硬性要求，
- 情绪弧线具体，
- 输出形态与现有素材相称，
- 音乐方案已落定（选定来源，或明确推迟），
- 采用电影感处理是有理由的，而不只是贴了个标签。

## 常见陷阱

- 把一个只是加了黑边的普通剪辑称作电影感。
- 没有检查工具就假定生成的插入镜头可用。
- 悄悄地把一个以运动为主的 brief 变成静图主导的先导片。
- 规划了预告片的形态，却没有揭示或回报。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
