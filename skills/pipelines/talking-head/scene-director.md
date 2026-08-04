# 场景导演 —— Talking Head 管线

## 何时使用

你手上有一份脚本（来自转写）和原始素材。你的工作是**看素材、理解内容、提出一份创意强化方案** —— 然后搭建一份场景方案，把原始口播素材变成一支有吸引力、视觉丰富的视频。

你不只是个处理器。你是创意导演。你的工作是弄清说话人在讲什么，并提出能让内容更抓人、更好懂的视觉强化。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/scene_plan.schema.json` | Artifact 校验 |
| 上游 artifact | Script、Brief | Section 时序与语境 |
| 工具 | `frame_sampler`（可选） | 提取代表性帧 |
| 工具 | `face_tracker`（可选） | 分析说话人面部位置，供重新构图使用 |
| 工具 | `silence_cutter`（可选） | 检测静音，供跳切规划使用 |

## 流程

### 第 0 步：素材分析

在看内容之前，先分析原始素材，弄清物理拍摄设置。

1. **抽取 5 帧**（沿时长均匀分布），用 ffmpeg：
   ```
   ffmpeg -i <footage> -vf "select='not(mod(n\,TOTAL_FRAMES/5))'" -vsync vfr -frames:v 5 frame_%02d.png
   ```

2. **对每一张抽样帧运行 visual_qa 或直方图分析**，以检测：
   - **背景类型：** 绿幕 / 蓝幕 / 自然背景。绿幕/蓝幕在直方图上会呈现一个占主导的窄带颜色尖峰。用 `visual_qa` 配提示词 "Is this a green screen or blue screen background?" 来确认。
   - **说话人位置：** 画面居中、偏左还是偏右。估出大致的包围盒（例如「说话人占据画面中央 40%，从 x=30% 到 x=70%」）。
   - **打光质量：** 均匀的影棚光、硬阴影、逆光、混合色温。记下任何可能影响抠像的问题。

3. **检测到绿幕了吗？**
   - 若是，记下 compose 阶段会需要 `green_screen_processor` 工具。
   - 记录检测到的幕布颜色（绿或蓝）以及估计的均匀度。
   - compose-director 会据此运行色键抠除，并合成到动态背景之上。

4. **测出说话人安全区：**
   - 由说话人的包围盒，判断图形可以放在哪里而**不会**与说话人重叠。
   - 说话人居中：左侧面板和右侧面板都可安全放叠加层。
   - 说话人偏左：右侧面板是主要安全区。
   - 说话人偏右：左侧面板是主要安全区。
   - 不论说话人位置如何，上三分之一和下三分之一通常都是安全的。

把所有发现记录到场景方案的 metadata 中，供下游阶段使用。

### 第 1 步：看与听 —— 理解内容

**这是最重要的一步。不要跳过。**

仔细读完整份转写。弄清：
- 说话人的**主题**是什么？
- 他们讲解了哪些**关键概念**？
- 他们在哪里用到了**数字、统计或数据**？
- 他们在哪里做了**对比**（A vs B、前/后、旧 vs 新）？
- 他们在哪里**列举了条目**（3 条建议、5 个步骤等）？
- 他们在哪里引入了**技术术语**或行话？
- **段落转场**（话题切换）在哪里？
- **情绪弧线**是什么（兴奋、严肃、幽默）？

若 `frame_sampler` 可用，抽取 5-8 张代表性帧，看清说话人的机位设置、背景、打光和手势。

### 第 2 步：提出创意叠加层

基于你的内容分析，提出会在关键时刻与说话人同框出现的**屏幕图形**。这些是 Remotion 组件，会被合成到口播素材之上或旁边。

**可用的叠加层类型：**

| 叠加层类型 | Remotion 组件 | 最适合 |
|-------------|-------------------|----------|
| **关键术语释义** | `text_card` | 说话人引入技术术语时 —— 显示术语 + 简短释义 |
| **统计/数字** | `stat_card` | 说话人提到某个数字或百分比时 —— 在屏幕上做动画 |
| **对比** | `comparison` | 说话人对比两样东西（A vs B）时 —— 并排展示 |
| **数据图表** | `bar_chart` / `pie_chart` / `line_chart` | 说话人引用数据或排名时 |
| **KPI 仪表盘** | `kpi_grid` | 多个数字被一并提到时 |
| **进度指示** | `progress_bar` | 说话人描述某个流程或百分比时 |
| **段落标题** | `hero_title` | 主要话题转场处 —— 显示新段落标题 |
| **标注/引语** | `callout` | 说话人抛出值得强调的关键点时 |
| **下三分之一条** | `text_card` | 开头处的说话人身份标识 |

**Remotion 组件约束：**

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

当某个组件的最小宽度超出可用空间时（例如 900px 的 `comparison` 塞不进 720px 的竖屏画面），就换成推荐的替代方案。对 `comparison`，改用两个依次出现的 `stat_card`。

对 `kpi_grid`，值**必须**是数字（例如 `4.8`、`73`、`2400`）。像 `"15+"` 或 `"$4.8B"` 这样的字符串值会导致渲染报错。带字符串格式的数字请用 `stat_card`。

**叠加层规划规则：**
- **不要过度叠加。** 每分钟成片 3-6 个叠加层是甜点区。超过这个数就会分散注意力。
- **让叠加层与语音对时。** 每个叠加层都应当在说话人说到相关词句时出现，不早不晚。
- **叠加层要短。** 每个 3-5 秒。它们是给说话人做支撑，不是跟说话人抢戏。
- **类型要有变化。** 不要连着上 5 张 text_card —— 穿插图表、对比、标注。
- **在自然停顿处用叠加层。** 说话人为了强调而停顿时，正是上叠加层的好时机。
- **气质要匹配。** 专业演讲 = 干净的数据卡与图表。轻松闲聊 = 标注与醒目的关键词。

### 第 3 步：把方案呈现给用户

**强制：在继续之前，先呈现你的强化方案。**

把提案格式化清楚：

```
## Enhancement Plan for [Video Title/Topic]

**Content Summary:** [1-2 sentences about what the speaker covers]

**Proposed Overlays:**

| Time | Type | Content | Why |
|------|------|---------|-----|
| 0:05 | lower_third | "Speaker Name — Title" | Speaker intro |
| 0:22 | text_card | "Agentic AI: software that acts autonomously" | Key term definition |
| 0:45 | comparison | Traditional Software vs Agentic Software | Speaker is comparing the two |
| 1:10 | stat_card | "73% of developers..." | Statistic mentioned |
| 1:35 | bar_chart | [Framework popularity data] | Speaker references rankings |
| 2:00 | callout | "The key insight is..." | Speaker's main takeaway |

**Enhancement Chain:**
- Silence removal: ~X seconds of dead air detected
- Speed: 1.25x (user requested)
- Face + eye enhancement
- Animated captions (bottom of frame)
- Background music: [recommendation]

**Estimated final duration:** ~Xs (from Xs raw)
```

**重要：输出叠加层方案时，还要同时生成真正的 Remotion JSON props 文件（`greenscreen-bg.json`）—— 不要只用散文描述场景。** 这份 JSON props 文件应当是 Remotion TalkingHead 合成的完整、合法输入，包含全部叠加层定义、时序、颜色和内容。把它保存到 `<project>/public/demo-props/` 或该项目的 props 目录。

在继续之前等待用户审批。用户可能会：
- 原样批准
- 增加/删除叠加层
- 修改叠加层内容
- 调整强化方案

### 第 4 步：分析素材（若工具可用）

**人脸追踪** —— 若 `face_tracker` 可用，对原始素材运行它：
```
face_tracker.execute({
    "input_path": "<raw_footage>",
    "sample_fps": 5
})
```
它会输出逐帧的人脸包围盒。用这份数据来：
- 判断是否需要重新构图（例如说话人偏离中心，不适合竖屏裁切）
- 找出说话人移动幅度较大的段落（需要动态裁切）
- 记下面部位置，供 compose 阶段的 auto_reframe 使用
- **确定叠加层安全区** —— 图形放在哪里不会遮挡面部

**静音检测** —— 若 `silence_cutter` 可用，以 `mark` 模式运行：
```
silence_cutter.execute({
    "input_path": "<raw_footage>",
    "mode": "mark",
    "silence_threshold_db": -35,
    "min_silence_duration": 0.5
})
```
它会输出静音/语音片段的时间戳。用它来：
- 规划哪些片段应当被跳切或加速
- 找出空白、口误重来和长停顿
- 估算剪辑后的成片时长

### 第 5 步：规划基础场景

对 talking-head 而言，基础很简单：每个脚本 section 一个场景，类型全部是 `talking_head`。原始素材本身**就是**场景。

### 第 6 步：搭建叠加层场景

为第 3 步中每个被批准的叠加层，创建一条叠加层场景条目：
```json
{
  "id": "overlay_1",
  "type": "overlay",
  "overlay_type": "text_card",
  "start_seconds": 22.0,
  "duration_seconds": 4.0,
  "content": {
    "text": "Agentic AI",
    "subtext": "Software that acts autonomously toward goals",
    "backgroundColor": "<theme_background>",
    "accentColor": "<theme_accent>"
  },
  "position": "lower_third"
}
```

**叠加层位置选项：**
- `lower_third` —— 画面底部 30%（最安全，不遮脸）
- `upper_third` —— 画面顶部 30%（适合标题）
- `side_panel` —— 左侧或右侧 40%（用于图表/对比，说话人移到另一侧）
- `full_overlay` —— 短暂的全屏图形（最多 1-2 秒，用于戏剧性强调）

### 第 7 步：规划重新构图与剪切

若目标平台要求不同的画幅比（例如 Instagram Reels = 9:16）：
- 记下 compose 阶段应当施加 `auto_reframe`
- 把目标画幅比记入场景方案
- 若人脸追踪数据显示说话人有明显移动，记下需要动态裁切

若静音检测找到了可剪的片段：
- 把推荐的剪切模式（`remove` 或 `speed_up`）记入场景方案
- 记下留白偏好（默认 0.08 秒，避免切掉词头词尾）

### 第 8 步：搭建场景方案

把完整的场景方案组装起来，包含：
- 基础场景（每个脚本 section 一个，类型 `talking_head`）
- 叠加层场景（来自第 6 步，类型 `overlay`）
- 强化链决策（静音剪切模式、变速系数、重新构图目标）
- 音乐建议
- 预估的成片时长

### 第 9 步：自评

| 判据 | 问题 |
|-----------|----------|
| **内容理解** | 我是否真的听懂了说话人在讲什么？ |
| **叠加层相关性** | 每个叠加层是否都与那一刻正在说的内容直接相关？ |
| **叠加层密度** | 我在每分钟 3-6 个的区间内吗？不太稀，也不太挤？ |
| **叠加层多样性** | 我是否用了不同类型，而不是清一色 text_card？ |
| **时序** | 叠加层是与说话人的措辞对时的，而不是随便挑的时刻？ |
| **覆盖度** | 每个脚本 section 都有场景吗？ |
| **可行性** | 所有叠加层都能用可用的 Remotion 组件渲染出来吗？ |
| **用户已批准** | 用户批准了这份强化方案吗？ |

### 第 10 步：提交

对照 schema 校验 scene_plan，并通过检查点持久化。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
