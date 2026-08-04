# 创意导演 —— Documentary Montage 管线

## 何时使用

你要把用户的一句话变成 brief artifact，而下游每一个阶段
都会读它。对本管线而言，brief 就是主题内核：这支蒙太奇
**讲的是什么**、它应当**给人什么感觉**、以及它应当**多长**。

## 运行时选择（强制 —— 把约束讲出来，不要静默选定）

锁定 `render_runtime = "remotion"`。**在 Phase 1 中，HyperFrames 在本管线上不是合法运行时** —— documentary-montage 依赖 Remotion 的 `CinematicRenderer` composition 及其 ProRes-4444 带 alpha 的片尾标签叠加栈，两者都没有 HyperFrames 的对等能力。

按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：**不要**静默取默认值。告诉用户："你的机器上有 HyperFrames 这个替代运行时，但 documentary-montage 依赖 Remotion 的 CinematicRenderer + 片尾标签叠加栈，所以这里 remotion 是唯一可行的选择 —— 可以这样推进吗？" 在 `decision_log` 中记录一条 `render_runtime_selection` 决策，`options_considered` 里列出两个运行时，并把 hyperframes 标为 `rejected_because: "CinematicRenderer + end-tag overlay parity deferred on documentary-montage"`。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/brief.schema.json` | Artifact 校验 |
| 用户输入 | 对话历史 | 原始诉求 |
| 元技能 | `skills/meta/reviewer.md` | 自评轮次 |

## 流程

### 1. 提炼那个主题性问题

一支纪录片蒙太奇回答的，是用户自己说不成一句话的那个问题。你的
工作是用**一行**把那个问题命名出来。

好的主题性问题：

- "回到家，是什么感觉？"
- "20 世纪是如何想象未来的？"
- "凌晨 4 点的城市里发生着什么？"
- "地球上所有的脚印看起来是什么样？"

差的主题性问题（太抽象或太具体）：

- "一支关于城市的视频"（太抽象 —— 没有感受）
- "一支包含 8 个特定月亮镜头的蒙太奇"（太具体 —— 那是
  一份镜头表，不是主题）

### 2. 定下调性

选定**一个**情绪基调。写下来。下游的一切
都以它为准。

本管线常见的基调：

- **哀歌式（elegiac）** —— 长停留、低饱和、慢切（失去、记忆、家）
- **紧迫（urgent）** —— 短切、硬同步、运动密集（危机、城市、当下）
- **庄重（reverent）** —— 沉稳、对称、耐心（自然、仪式、尺度）
- **戏谑（wry）** —— 反讽并置、在荒诞处下刀（消费文化、
  政治、中世纪乐观主义）
- **梦境（dreamlike）** —— 慢叠化、重复母题、非线性（童年、
  悲伤、记忆）

### 3. 选定时长与形状

时长很重要，因为它给节拍数量封了顶。

| 时长 | 节拍 | 用途 |
|----------|-------|-----|
| 30-45 秒 | 8-12 个切点 | 社交/Instagram/reel —— 一种感受，没有弧线 |
| 60-90 秒 | 15-25 个切点 | 标准短片 —— 带一个转折的迷你弧线 |
| 2-3 分钟 | 30-50 个切点 | 真正的随笔式蒙太奇 —— 可以有三幕弧线 |

形状选项：

- **单意象展开** —— 一个想法，从多个角度呈现（适合 60 秒以内的
  哀歌式作品）
- **前后对照** —— 前半段确立，后半段翻转（适合戏谑或
  紧迫的基调）
- **三幕** —— 铺陈 → 转折 → 释放（Adam Curtis 式手法，需要
  90 秒以上）
- **清单/编目** —— "所有那些……的人"式结构，没有弧线，只有
  累积（适合庄重或哀歌式）

### 4. 记下音乐意图（强制）

纪录片蒙太奇与它的音乐铺底密不可分。**本管线的音乐是强制的。**
唯一的例外是用户明确表示不要（例如
"不要音乐，我想要它是静默的"）—— 这**必须**记录为
`music_plan.source = "none"` 并附带 `music_plan.opt_out_reason` 字段。

那些在创意阶段"纯粹"得动人的静默设计，到合成时经常看起来
像被遗弃的素材。不要假定静默能自己挣来分量。若用户没提音乐，
就**假定他们想要**，并从中挑一个：

- 用户提供的曲目（把路径写进 `music_plan.source_path`），
- 从音乐库里挑（列出 `music_library/` 里有什么），
- 生成（点名工具，并用基调作为提示词种子），
- 明确弃用（`source: "none"` + `opt_out_reason`）。

**若没有任何音乐来源可用，就提醒用户。** 不要静默地
把它往后拖 —— 那会在 assets 阶段变成一个昂贵的意外。

### 5. 记下片尾标签意图（强制）

每一部 documentary-montage 影片都以一句富有哲思的片尾标签收束 —— 一句
短小、抽象、赋予整件作品意义的话。它会被渲染
成 Remotion 的片尾卡（"发光下划线标签"的调性 —— 粗体字重、
拉开字距、带动画的下划线）。

**默认模式是 `"overlay"`** —— 标签在正片素材的最后几个场景上淡入，
让它感觉像是影片的一部分，而不是结尾硬贴上去的一张
独立卡片。另一个选项是 `"concat"`，它在正片之后追加一张独立黑卡。
只有当用户明确要求一张分离的标题卡，或者最终
素材在视觉上太繁忙、文字叠上去不可读时，才用 concat。

**片尾标签是强制的。** 唯一的例外是用户明确弃用，
记录为 `end_tag_plan: null` 并附带 `end_tag_opt_out_reason` 字段。

在 brief 阶段就提出片尾标签。写 3 个选项并推荐其中一个。
预期形态：

```json
{
  "end_tag_plan": {
    "text": "WE BUILT BOTH WITH THE SAME HANDS.",
    "palette": "warm_ivory_on_black",
    "duration_seconds": 5.5,
    "render_engine": "remotion",
    "component": "EndTag",
    "mode": "overlay"
  }
}
```

字段：
- `text` —— 3-9 个词。一个论点，不是一句总结。
- `palette` —— `"cool_offwhite_on_black"` 或 `"warm_ivory_on_black"`。
- `duration_seconds` —— 标签的总屏幕时间（淡入 + 停留 + 淡出）。
  5-8 秒是甜点。
- `render_engine` —— 恒为 `"remotion"`。
- `component` —— 恒为 `"EndTag"`。
- `mode` —— `"overlay"`（默认）或 `"concat"`。
  - **overlay**：标签渲染成带 alpha 的 ProRes 4444 → 通过 FFmpeg 的 overlay
    滤镜合成到正片素材上。标签在实拍素材的最后 N 秒里淡入淡出。
    正片自身的淡出应与标签的淡出对齐。
  - **concat**：标签渲染成不透明 MP4 → 通过 FFmpeg concat 追加到正片之后。
    输出总时长 = 正片 + 标签。

### 6. 记下旁白意图（可选）

与音乐和片尾标签不同，旁白是**可选的**。若 画面 + 音乐 + 片尾标签
已经承载了基调，没有旁白也没问题。若确实要用旁白，就点名
TTS provider 和音色。若没有旁白，就显式记 `narration: "none"` ——
不要把这个字段留空。

### 7. 写下 Brief

brief 必须携带的最小字段集：

```json
{
  "topic": "A minute in the rain",
  "thematic_question": "What does rain show you about a city?",
  "tone": "elegiac",
  "duration_seconds": 90,
  "shape": "list",
  "sources_allowed": ["pexels", "pixabay_video", "coverr", "mixkit", "archive_org", "nara", "nasa"],
  "generated_clips_allowed": false,
  "narration": "none",
  "music_plan": {
    "source": "generated",
    "provider": "elevenlabs",
    "prompt_seed": "slow ambient drone in A minor, no percussion, 60s sustained swell, Max Richter register"
  },
  "end_tag_plan": {
    "text": "THE CITY KEEPS ITS OWN VIGIL.",
    "palette": "cool_offwhite_on_black",
    "duration_seconds": 5.5,
    "render_engine": "remotion",
    "component": "EndTag"
  },
  "era_mix": "any",
  "target_platform": "social_short"
}
```

`era_mix` 是纪录片专属字段："modern" 偏向
Pexels，"vintage" 偏向 Archive.org 的 Prelinger 档案，"any" 则留给
场景导演逐槽位决定。

### 8. 质量门

- 主题性问题是**一句话**。
- 调性是固定清单里的**一个**基调。
- 时长与形状是具体的数字/枚举值。
- `music_plan` 存在，并且要么点名了一个真实来源，要么带有
  `source: "none"` + `opt_out_reason`（用户的明确决定）。
- `end_tag_plan` 存在，并且要么有非空的 `text`，要么是
  `null` 并带 `end_tag_opt_out_reason`（用户的明确决定）。
- 来源清单非空，且按 preflight 中呈现的
  `corpus_builder.source_provider_menu`，至少有一个被请求的来源是
  `available`。

## 常见陷阱

- 同时陈述多个主题（"它讲的是城市**和**科技**和**失去"）。
  选一个。其余的会成为下游的联想。
- 直接跳到镜头表。brief 关心的是**意义**。镜头是下一步的事。
- 无视时长。45 秒配 50 个切点会让人反胃。3 分钟只有
  12 个切点就是幻灯片。
- 忘了问音乐。用户通常是有想法的。
- 假定静默能自己挣来分量。它挣不来。除非用户明确说不要，
  否则音乐是强制的。
- 因为"画面自己会说话"就跳过片尾标签。它们不会 ——
  片尾标签就是那个论点。每次都要提出一个。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
