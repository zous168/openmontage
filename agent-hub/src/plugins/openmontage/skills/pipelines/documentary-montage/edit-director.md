# 剪辑导演 —— Documentary Montage 管线

## 何时使用

每个槽位都有了片段。你现在得把一堆片段变成
一件**作品**。本阶段决定入点、出点、转场、音乐
同步，以及片段实际的播放顺序。产出是一份
带具体时间线的 `edit_decisions` artifact。

纪录片的技法就活在这里。若素材导演干好了它的活，
你手上有的是原材料。剪辑才是思考。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["assets"]["asset_manifest"]` | 选中的片段 + 音乐铺底 |
| 上游 artifact | `state.artifacts["scene_plan"]["scene_plan"]` | 槽位顺序、hero 标记、目标停留 |
| 上游 artifact | `state.artifacts["idea"]["brief"]` | 调性基调、时长、形状 |
| 工具（可选） | `video_analyzer` | 需要复核时探测某个片段的运动量 |

## 心智模型

纪录片蒙太奇活在你必须平衡的四个维度里：

1. **律动** —— 每次停留有多长，以及各次停留之间的关系。
2. **并置** —— 哪个画面接在哪个画面之后，以及它意味着什么。
3. **音乐同步** —— 剪辑点落在节拍上，抽空处挣得分量。
4. **基调的连续性** —— 颗粒、色彩和年代不会剧烈摇摆，
   除非这种摇摆本身就是重点。

敌人是"幻灯片" —— 一串停留时长相同、没有声音设计的片段
一个接一个播。若它感觉像幻灯片，剪辑就失败了，
无论片段本身多好。

本阶段还会锁定渲染语法。对纪录片蒙太奇，把
`renderer_family` 设为 `documentary-montage`，好让 compose 留在
已获批的 Remotion 优先路径上。

## 流程

### 0. 护栏 —— 不许静默做重大变更

在动时间线之前，重读 brief。若下面任何一条
成立，就**停下**并按决策沟通
契约向用户呈现：

- brief 批准了"不要旁白"，但剪辑感觉需要
  配音。旁白是**重大**变更。
- brief 批准了某首音乐曲目，而剪辑导演现在想
  替换掉它。换音乐是**重大**变更。
- brief 批准了 90 秒时长，但自然的剪辑想要 2 分 30 秒。
  拉长时长是**重大**变更。

去把剪辑修好，不要拿它糊墙。若剪辑确实需要
其中之一，那就去问。

### 1. 设定律动网格

读 `brief.tone` 和 `brief.duration_seconds`。按场景导演的
调性表算出停留表：

| 调性 | 基准停留 | 最短停留 | 最长停留 |
|------|-----------|----------|----------|
| elegiac（哀歌） | 4.0 秒 | 2.5 秒 | 7.0 秒 |
| reverent（庄重） | 3.5 秒 | 2.0 秒 | 6.0 秒 |
| dreamlike（梦境） | 3.0 秒 | 1.5 秒 | 5.5 秒 |
| wry（戏谑） | 2.0 秒 | 1.0 秒 | 4.0 秒 |
| urgent（紧迫） | 1.2 秒 | 0.5 秒 | 2.5 秒 |

**主槽位取最长停留。** 中段的切出镜头取基准。快速
转场取最短。

停留总时长必须落在 `brief.duration_seconds` 的 ±10% 以内。
若超了，先压缩非主槽位的停留 —— 绝不为了凑时长而
削短主槽位。

### 2. 按叙事节拍编排，不按分数

场景导演给了你一个槽位顺序。那个顺序就是意图。
不要按 CLIP 分数、运动分数或分辨率去重排它。

在以下情况你**可以**重排槽位：

- 音乐铺底在某个已知时间点有重拍，重排两个槽位
  能让一个主镜头落在拍上（见第 4 步）。
- 相邻两个槽位在视觉上一模一样，换掉一个能打破
  单调（但见第 7 步 —— diversify 本应已经抓到这一点）。
- 最后一个画面没有落住。最后 5-10 秒承载着
  不成比例的分量；若场景导演选的那个撑不住，就把
  更强的候选挪到片尾。

始终把重排连同理由记入
`edit_decisions.metadata.reorder_notes`。

### 3. 把每个片段修到它的节拍

对每个选中的片段，决定 `in_seconds` 和 `out_seconds`。三条
规则：

- **找出最好的那一小段，而不是整段片段。** 一段 12 秒的 Pexels
  片段通常只有 3 秒配得上这次停留，其余 9 秒是起势/收势。
  把那一刻找出来。
- **在动作自然结束**之前**下刀。** 结束在一个眼神上，而不是在人物
  走出画面之后。这样的剪辑显得有意图，而不是精疲力竭。
- **两端各留一点余量。** 留 4-6 帧余头，好让合成时能施加
  淡变或叠化而不切掉那个瞬间。

若某个片段太短、填不满它的目标停留，那就：

- 放慢它（速度 0.5-0.75，对偏静态的素材没问题，对任何有同步
  运动或人物说话的素材都很糟），
- 让它提前切掉，把剩余时长从下一个槽位的停留里借，
- 或者从 rejected-picks 记录里换成第 2 名候选。

**不要**停在最后一帧定格。纪录片蒙太奇里的定格帧
读起来像技术失误。

### 4. 与音乐铺底同步

从 `asset_manifest` 读音乐素材并载入它的时长。
纪录片蒙太奇的情绪分量来自剪辑点落在
音乐事件上。三种同步动作：

- **重拍剪辑。** 若你有小节和节拍元数据（来自用户提供的
  曲目）或者能听出来，就把主剪辑点放在重拍上。
  若没有，对 60bpm 的铺底而言，按 4 秒等距下刀是
  安全的默认。
- **一次刻意的静默。** 在作品的情绪中心把音乐抽掉约 2 秒。
  静默是一件工具。只用一次。要用得狠。
- **尾部淡出。** 音乐在最后 3-5 秒淡到画面之下，好让最后一个画面
  能呼吸，不被音乐的收束抢戏。

把音乐配置记入 `edit_decisions.audio.music`：

```json
{
  "asset_id": "asset_music_bed",
  "volume": 0.7,
  "fade_in_seconds": 1.0,
  "fade_out_seconds": 4.0,
  "ducking": false
}
```

本管线默认 `ducking: false` —— 没有旁白需要闪避。
若用户批准了旁白轨，就把 ducking 设为 true，让它在
旁白段落下压。

### 5. 从一个很小的词汇表里选转场

一支纪录片蒙太奇整件作品加起来大概只用四种转场：

| 转场 | 用途 |
|------------|-----|
| `cut`（硬切） | 默认。绝大多数剪辑点都是硬切。 |
| `dissolve`（0.5-1.0 秒） | 情绪上互为姊妹的片段、时间流逝 |
| `fade_to_black`（0.5 秒，再升起来） | 三幕结构里的幕间，或临近结尾处用一次 |
| `fade_in`（第一个镜头）/ `fade_out`（最后一个镜头） | 0.5-1.0 秒的首尾书挡 |

**不要使用：**

- 划像，
- 推入/滑动转场，
- 缩放模糊，
- RGB 分离，
- 漏光，
- 故障特效。

这些读起来是社交媒体的剪辑语言，会破坏
纪录片的基调。若作品变得无聊，那就去修片段
选择或节奏，不要靠加转场特效。

按 schema 记录每个剪辑点的 `transition_in` / `transition_out`。
多数剪辑点默认 `transition_in: "cut"`。

### 6. 施加基调连续性

年代混杂的素材库看起来差异极大。Pexels 2023 干净、锐利、
调过色。Prelinger 1962 有颗粒、偏暖、画幅方正。
NASA 档案常常低分辨率还带文字叠加。若你把它们生生
糅在一起，作品看起来会像一篇维基百科词条。

你有两件工具来抹平它：

1. **裁剪到统一画幅比。** 挑一个：主作品用 16:9 电影感
   （上下加 `2.35:1` 黑边），社交用 9:16。在每个 cut 的
   `transform.crop` 字段里强制执行。
2. **给整件作品标记出在合成时统一调色的需求。** 在
   `edit_decisions.metadata` 里放一个 `grade_profile` 提示。合成
   导演会在整条时间线上应用一个 LUT。

不要在这里逐片段调色。那是合成阶段的事。你的
工作是把这个需求标出来。

### 7. 再执行一次相邻多样性检查

成对地走一遍时间线。对每一组相邻的 (cut_n, cut_n+1)：

- 它们是同一主体、同一景别吗？若是，你就有一个
  幻灯片时刻。把其中一个换成不同景别的片段（全景 vs 特写）。
- 它们配色相同吗（两个夜蓝色片段挨在一起）？若是，
  至少每 4 个剪辑点打破一次这种规律。
- 它们运动方向相同吗（两个从左到右的横摇）？若
  是，把第二个水平镜像，或者重排。

把你做过的所有替换记入 `metadata.diversity_swaps`。

### 8. L-Cut 手法（可选但很有力）

对于任何一处转场，若切出的那个片段有强烈的环境
音（雨、脚步、车流），就让那段音频在切入片段之下再延续
0.5-1.5 秒。这就是 L-cut，它把两个镜头焊在一起的力度
胜过任何视觉转场。

在 schema 中的实现方式是：用一个很短的 `dissolve` 转场，**或者**
把切出片段的音频作为一条 SFX 条目分层放进
`edit_decisions.audio.sfx`，并让它延后结束。

带 L-cut 的纪录片蒙太奇，比不带的连贯度高出约 50%。
在整件作品中最难处理的那 3-4 处转场上使用它们。

### 8b. 放置片尾标签叠加层

若 `brief.metadata.end_tag_plan.mode == "overlay"`（默认值），片尾
标签会在合成时被叠到正片素材之上。
剪辑导演的工作是决定这个标签**何时**出现。

计算偏移量：`offset_seconds = 正片时长 - 标签时长`。
这样标签的淡出就能与正片收尾的淡出对齐
（最后一个 cut 的 `transition_out: fade_out`）。若最后一个 cut 的停留
短于标签时长，就让标签更早开始，使它也覆盖
倒数第二个 cut —— 这没问题，而且往往更好看。

记入 `edit_decisions.end_tag`：

```json
{
  "end_tag": {
    "offset_seconds": 84.5,
    "notes": "Tag starts at body_duration - tag_duration. Aligns tag fade-out with final cut fade-out."
  }
}
```

若 `mode == "concat"`，就省略这一节 —— 合成导演会在正片之后
追加标签，不需要时间偏移。

### 9. 产出剪辑决策

本管线的规范形态：

```json
{
  "version": "1.0",
  "renderer_family": "documentary-montage",
  "cuts": [
    {
      "id": "cut_01",
      "source": "asset_slot_01",
      "in_seconds": 1.2,
      "out_seconds": 5.2,
      "layer": "primary",
      "transform": { "scale": 1.0, "position": "center" },
      "transition_in": "fade_in",
      "transition_out": "cut",
      "transition_duration": 0.8,
      "reason": "opening hero — raindrop on asphalt, 4s hold, slow-motion streetlamp glow"
    },
    {
      "id": "cut_02",
      "source": "asset_slot_02",
      "in_seconds": 2.0,
      "out_seconds": 5.5,
      "layer": "primary",
      "transition_in": "cut",
      "transition_out": "cut",
      "reason": "umbrella opening in doorway, hard cut from raindrop → street"
    }
  ],
  "audio": {
    "music": {
      "asset_id": "asset_music_bed",
      "volume": 0.7,
      "fade_in_seconds": 1.0,
      "fade_out_seconds": 4.0,
      "ducking": false
    }
  },
  "end_tag": {
    "offset_seconds": 84.5,
    "notes": "Tag starts at body_duration - tag_duration. Aligns tag fade-out with final cut fade-out."
  },
  "metadata": {
    "pipeline": "documentary-montage",
    "tone": "elegiac",
    "shape": "list",
    "total_duration_seconds": 90.0,
    "hold_table_used": { "base": 4.0, "min": 2.5, "max": 7.0 },
    "grade_profile": "warm_film_100",
    "reorder_notes": [],
    "diversity_swaps": [
      { "at": "cut_07-cut_08", "reason": "two wide rooftops-in-rain adjacent, swapped 08 for #2 pick" }
    ],
    "silence_window": { "start_seconds": 54.0, "end_seconds": 56.0 },
    "l_cuts": [
      { "from_cut": "cut_05", "to_cut": "cut_06", "carry_seconds": 1.2, "channel": "ambient_rain" }
    ]
  }
}
```

### 10. 质量门

- `sum(out - in for cut in cuts)` 落在
  `brief.duration_seconds` 的 ±10% 以内。
- `renderer_family = "documentary-montage"` 存在且未被更改。
- 主槽位拥有最长的停留。
- 没有任何两个相邻剪辑点同时共享主体**和**景别。
- 转场词汇最多 4 种不同取值。
- 音乐配置存在（或 brief 明确说了不要音乐）。
- 60 秒及以上的作品至少有一条 `silence_window` 条目。
- 每个剪辑点都有一行 `reason` —— 若你写不出来，
  这一刀就是随意的，应当重新考虑。
- `metadata.total_duration_seconds` 与各 cut 时长之和一致。

## 常见陷阱

- **按信息密度而不是按律动下刀。** 纪录片
  蒙太奇不是维基百科词条。"但我得把这个展示出来"不是
  理由 —— 若这个画面撑不住一次停留，它就不属于这里。
- **叠化用得太多。** 每一刀都叠化等于在说"我下不了决心"。
  下决心。
- **把音乐铺底拖到最后才考虑。** 音乐不是你在合成时
  加的甜味剂。它是你据以下刀的时序网格。
- **让最后一个画面是个弱镜头。** 最后一帧会被
  不成比例地记住。若它弱，就换掉 —— 场景
  导演的槽位顺序是强建议，不是契约。
- **定格帧结尾。** 读起来像技术失误。改用
  淡入黑场结束。
- **因为剪辑感觉单薄就悄悄加旁白。** 这是重大
  变更。去问。
- **在 cut 里隐藏片段的 provider。** 每个 `cut.source` 都必须是
  一个 `asset_manifest` 的 asset_id，好让来源信息延续下来。
- **前 15 秒里出现三种不同的转场类型。**
  观众会感觉到剪辑在"用力"。克制才是这个类型的品牌。

## 完整节奏示例 —— "雨中的一分钟"

90 秒，哀歌式，清单形状，15 个带 hero 标记的槽位。

- 基准停留 4.0 秒 × 15 = 60 秒。差 30 秒。
- 把 30 秒加到 3 个主槽位（1、11、15）上，每个 +10 秒：
  hero_1 = 5.5 秒，hero_11 = 6.0 秒，hero_15 = 7.0 秒。
- 把槽位 4、7、13 各收紧到 3.0 秒（小型切出镜头）。
- 在 54.0-56.0 秒处插入 silence_window（就在 hero_11 之前）。
- 对 slot_10（水洼里的雨靴）→ slot_11（街对面亮灯的
  窗）做 L-cut，把雨打玻璃的环境声延续 1.2 秒。
- 第一个 cut `fade_in` 1.0 秒，最后一个 cut `fade_out` 1.5 秒。
- 其余全部硬切。
- 音乐淡入 1.0 秒，在 hero_15 + 黑场之下淡出 4.0 秒。

这样得到一支 90 秒的作品：有 3 个呼吸点（淡入、静默、
淡出）、一条清晰的主镜头弧线（槽位 1 → 11 → 15），并且没有相邻
景别撞车。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
