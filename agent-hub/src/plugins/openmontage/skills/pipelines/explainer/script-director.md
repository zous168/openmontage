# 脚本导演 —— Explainer 管线

## 何时使用

你是一支生成式讲解视频的脚本作者。你手上有一份来自创意探索者的 `brief` artifact。你的工作是从零写出一份旁白脚本 —— 没有现成素材可供转写。

脚本是视频的骨干。每一个画面、每一个场景、每一个音频提示都从你在这里写的东西流出。平庸的脚本救不回来，再好的画面也救不了。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/script.schema.json` | Artifact 校验 |
| 上游 artifact | `proposal_packet` | 选定概念，含标题、钩子、key_points、core_message、调性、narrative_structure、时长 |
| 上游 artifact | `research_brief`（可选但价值很高） | 数据点、受众洞察、专家引语 —— 让脚本扎根于真实事实 |
| Playbook | 来自 `proposal_packet.selected_concept.suggested_playbook` 的当前风格 playbook | 语音风格、节奏规则 |
| 元技能 | `skills/meta/voice-performance-director.md` | 结构化的 TTS 演绎提示，让旁白自然、有表现力 |
| Layer 3 | TTS provider 技能（查所选 TTS 工具的 `agent_skills`） | 用于配音指示的 TTS 能力 |

## 流程

### 第 1 步：吸收提案与调研

仔细读 `proposal_packet.selected_concept`。提取：
- **目标时长** —— 这就是你的词数预算（见下面的时序表）
- **钩子** —— 你的开场必须兑现这个承诺
- **关键论点** —— 这些必须在脚本中全部覆盖
- **核心信息** —— 观众唯一该记住的那件事
- **调性** —— 决定用词、句长、正式程度
- **目标受众** —— 决定复杂度和预设知识
- **叙事结构** —— 结构上的路数（myth_busting、journey、data_narrative 等）

然后读 `research_brief` 获取支撑材料：
- **`data_points`** —— 要织进脚本的具体统计数字和事实。把 `surprise_factor` 为 `"surprising"` 或 `"counterintuitive"` 的论断用作留存锚点。
- **`audience_insights.misconceptions`** —— 若叙事结构是 `myth_busting`，这些就是你的"迷思/事实"配对。
- **`audience_insights.common_questions`** —— 在自然合适的地方在脚本里正面回应它们。
- **`expert_voices`** —— 可引用的专家能增加权威感。要节制 —— 每份脚本一两处。
- **`trending.recent_developments`** —— 若有时效性，引用它们让内容显得当下。

**research_brief 就是你的小抄。** 每个事实、每个意外数据、每个误解都已预先核实并有出处。用上它们。一份引用"73% 的开发者……"（来自调研）的脚本，比说"很多开发者……"更有说服力。

### 第 2 步：在必要处深化调研

调研导演已经干完了重活 —— 你手上有一份塞满了有出处事实的 `research_brief`。你在这里的工作是有针对性的：

1. **核实与更新**：若 research_brief 里某个数据点感觉陈旧或不确定，就重新检索确认。
2. **补上脚本层面的空白**：调研给的是宽泛的事实。你可能需要某个具体类比、某个精确技术细节，或某一段更好的例子。
3. **找到最好的解释方式**：最好的教育者（3Blue1Brown、Kurzgesagt、Fireship、Veritasium）是怎么解释这个概念的？哪些类比有效？
4. **找可引用的时刻**：若 research_brief 的 expert_voices 里有可用引语，就用它们。若没有，就检索一句有力的引语来支撑关键段落。

**不要重复调研导演的工作。** 若 research_brief 已经有 6 个数据点，你不需要再找 6 个。聚焦脚本层面的需求：合适的词、合适的类比、合适的顺序。

### 第 3 步：规划叙事弧线

在写散文之前，先规划结构。每份讲解脚本都遵循一条戏剧弧线：

```
钩子（0-5 秒）    → 抓住注意力。一个问题、一个大胆论断，或一个意外事实。
                    绝不要："在这支视频里，我们将学习……"
                    绝不要："大家好，欢迎回来……"

铺垫（5-15 秒）   → 观众为什么该在意？制造知识缺口。
                    把问题或疑问摆出来。让他们**需要**那个答案。

搭建（15-X 秒）   → 渐进式揭示。每一段都建立在上一段之上。
                    用"因此 / 但是"的过渡，**不要**用"然后"。
                    南方公园法则："这件事发生了，**因此**那件事发生了，
                    **但是**接着又出现了这个麻烦……"

高潮（结束前 X-5 秒）→ "啊哈"时刻。一切豁然贯通。
                        这是对铺垫阶段那个知识缺口的回报。

落地（最后 5 秒） → 快速回顾核心信息 + CTA。
                    不要在这里引入新信息。
```

把 brief 中的每个 `key_points` 映射到搭建阶段的某个具体段落。

### 第 4 步：撰写脚本

在写各段之前，先用 `skills/meta/voice-performance-director.md`
创建一份顶层 `voice_performance` 计划。这份计划必须描述人声
意图、节奏档案、能量曲线、停顿策略，以及哪一段应当
用作 TTS 样本审批。不要把它留成一句含糊的"自然的声音"。

用这些字段来写每一段：

```json
{
  "id": "s1",
  "label": "Hook",
  "text": "Your database searches every single row. Every. Single. One. What if it didn't have to?",
  "start_seconds": 0,
  "end_seconds": 5,
  "speaker_directions": "Emphasize 'every single row' with measured pacing. Brief pause before the question.",
  "delivery_cues": {
    "pace": "measured",
    "energy": "curious",
    "emphasis_words": ["every", "single"],
    "pause_after_seconds": 0.6,
    "delivery_note": "Let the repetition feel intentional, then soften into the question.",
    "provider_text": "Your database searches every single row. Every. Single. One. <break time=\"0.6s\"/> What if it didn't have to?"
  },
  "enhancement_cues": [
    {
      "type": "animation",
      "description": "Database table with rows highlighted one by one, slowing down as count increases",
      "timestamp_seconds": 1
    }
  ],
  "pronunciation_guides": []
}
```

#### 时长估算

| 语速 | 每分钟词数 | 何时使用 |
|------|-------------|----------|
| 对话式 | 约 150 词 | 多数讲解视频的默认 |
| 沉思式 | 约 120 词 | 复杂题材，需要消化时间 |
| 有活力 | 约 180 词 | 短视频、高能量、TikTok/Reels |
| 技术型 | 约 130 词 | 代码走查、架构深度解析 |

**按时长划分的词数预算：**
- 30 秒视频 → 约 65-75 词
- 60 秒视频 → 约 130-150 词
- 90 秒视频 → 约 195-225 词
- 120 秒视频 → 约 260-300 词

数一数你的词数。若超预算 20% 以上，TTS 要么会赶，要么会超时长。狠心删。

#### 配音指示

写 TTS 真能执行的指示。优先用结构化的
`delivery_cues`，而不是只有散文的 `speaker_directions`：

| 指示 | TTS 实现方式 |
|-----------|-------------------|
| "慢一点说，带重音" | 降低速度设置，提高 stability |
| "兴奋起来，加快语速" | 提高速度、提高 style 设置 |
| "停顿 1 秒" | SSML `<break time="1s"/>` |
| "耳语" | SSML 的 whisper 标签（视模型而定） |
| "强调**这个**词" | 后处理备注或 SSML emphasis |

避免 TTS 做不到的指示："边说边微笑"、"朝屏幕做手势"、"看镜头"。

**富有表现力的旁白规则：** 每个以旁白为主的段落，都必须在
`pace`、`energy`、`emphasis_words`、`pause_before_seconds`、`pause_after_seconds`、
`delivery_note` 或 `provider_text` 中至少包含**两条**具体提示。当需要标点或
SSML break 标签才能让朗读听起来像人时，使用 `provider_text`。

#### 增强提示

每一段都应当至少有一条增强提示。它们告诉场景规划器和素材生成器该创作什么画面。

| 提示类型 | 何时使用 | 示例 |
|----------|-------------|---------|
| `overlay` | 关键术语、定义、标签 | "显示 'embedding' 定义叠加层" |
| `diagram` | 流程、架构、流向 | "Mermaid 流程图：query → encode → search → rank" |
| `stat_card` | 意外的数字或对比 | "显示：1ms vs 500ms 检索时间" |
| `animation` | 需要运动才能理解的概念 | "让向量在高维空间中移动的动画" |
| `code_snippet` | 代码示例 | "展示 Python：`results = collection.query(embedding)`" |
| `broll` | 现实世界的语境 | "展示使用向量检索的应用案例" |

**密度规则**：每 8-10 秒至少一条增强提示。一支 60 秒的视频至少要有 6-8 条。若画面不变，观众就会走神。

#### 读音指南

针对技术术语、缩写和非英语词汇：

```json
{"word": "FAISS", "phonetic": "FACE"},
{"word": "Qdrant", "phonetic": "kuh-DRANT"},
{"word": "cosine", "phonetic": "CO-sign"}
```

### 第 5 步：对照 Playbook 校验

读当前生效的风格 playbook 并确认：

| Playbook 字段 | 对脚本的影响 |
|----------------|---------------|
| `identity.pace` | 匹配词密度。`contemplative` = 更少的词、更长的停顿 |
| `audio.voice_style` | 塑造配音指示的调性 |
| `voice_performance` | 确认节奏、停顿和能量曲线对 TTS 而言足够明确 |
| `motion.pacing_rules` | 例如"定场镜头至少保持 2 秒"会影响段落时序 |
| `identity.mood` | 用词选择：`warm` 用口语化表达；`professional` 用精确表达 |

### 第 6 步：自评

给你的脚本打分（1-5）：

| 标准 | 问题 |
|-----------|----------|
| **钩子力度** | 有人会在前 3 秒停下滑动吗？ |
| **词数准确性** | 是否在该时长目标的 ±10% 以内？ |
| **叙事流畅度** | 每一段是否建立在上一段之上？是"因此/但是"而不是"然后"吗？ |
| **增强密度** | 每 8-10 秒至少一条提示吗？ |
| **配音表演** | 停顿、重音、语速和样本段落是否明确？ |
| **术语管理** | 技术术语是否被解释过，或带有读音指南？ |
| **高潮回报** | 那个"啊哈"时刻是否兑现了钩子的承诺？ |
| **CTA 相关性** | 行动号召是否具体、可执行？ |

若任何一项低于 3 分，就先修订再提交。

### 第 7 步：提交

调用 `handle_explainer_script(state, {"script": script_json})` 做校验并持久化。

### 生产中途的事实核验

若你在写脚本时遇到不确定之处：
- 在把某个事实性论断写进脚本之前，用 `web_search` 核实它
- 用 `web_search` 找参考图以保证视觉准确性
- 在 decision log 中记录核验：`category="visual_accuracy_check"`

脚本中的每一条事实性论断都应当能追溯到 `research_brief`。
若你做出了调研中没有的论断，就补做调研并补上来源。不要编造统计数字、日期或出处。

## 常见陷阱

- **写太多词**：头号失败模式。TTS 的语速是固定的。若你为一支 60 秒的视频写了 250 词，要么音频会赶，要么视频会变成 100 秒。数词数。
- **信息前置**：钩子应当制造好奇，而不是倾倒信息。"HTTPS 使用带 AEAD 密码套件的 TLS 1.3"是糟糕的开场。"那个挂锁图标并不是你以为的意思"才有说服力。
- **缺少增强提示**：没有视觉指示的脚本是一份播客稿。每一段都需要至少一条提示，告诉视觉团队该展示什么。
- **泛泛的配音指示**："自然地读"毫无用处。"从沉稳精确开始，然后在列举时加速，以传达规模感"才是可执行的。
- **忘了受众**：给 CTO 的脚本用词应当与给高中生的不同，即便讲的是同一个概念。
- **段落之间没有过渡**：每一段都应当有通向下一段的逻辑桥梁。观众绝不该想"等等，我们现在为什么在讲这个？"

## 示例：写得好的段落

```json
{
  "id": "s3",
  "label": "The Core Idea",
  "text": "Instead of matching keywords, vector databases convert everything — text, images, audio — into lists of numbers called embeddings. Similar things get similar numbers. So finding related content becomes a math problem: which numbers are closest?",
  "start_seconds": 15,
  "end_seconds": 28,
  "speaker_directions": "Measured pace through 'text, images, audio' with slight pause between each. Speed up slightly on 'similar things get similar numbers' — it should feel like a revelation. Brief pause before the final question.",
  "enhancement_cues": [
    {
      "type": "animation",
      "description": "Show text/image/audio icons transforming into number arrays (embeddings). Arrays cluster by similarity in a 2D space.",
      "timestamp_seconds": 16
    },
    {
      "type": "stat_card",
      "description": "Display: 'Everything becomes numbers. Similar things → similar numbers.'",
      "timestamp_seconds": 22
    }
  ],
  "pronunciation_guides": [
    {"word": "embeddings", "phonetic": "em-BED-ings"}
  ]
}
```

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
