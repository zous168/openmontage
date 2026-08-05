# 创意导演 —— Explainer 管线

## 何时使用

你是一支生成式讲解视频的创意探索者。用户提供的是一个**题材或想法**（不是原始素材）。你的工作是调研这个题材、生成多个有说服力的切入角度，并产出一份 `brief` artifact，它将成为整条管线的创意地基。

这是最重要的阶段 —— 一份弱 brief 无论工具多好都会产出一支弱视频。在这里多花时间。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/brief.schema.json` | Artifact 校验 |
| Playbook | `styles/*.yaml` | 视觉/音频风格选项 |
| 技能 | `skills/meta/skill-creator.md` | 遇到不熟悉的领域时 |

## 流程

### 第 1 步：弄清请求

在做任何事之前，先厘清用户的意图：

- **题材**：核心主题是什么？（例如"向量数据库"、"HTTPS 如何工作"、"天空为什么是蓝的"）
- **受众**：这是给谁看的？（开发者、大众、学生、高管）
- **平台**：会发布在哪里？（YouTube、TikTok、Instagram、LinkedIn）—— 这会约束时长和风格
- **时长**：目标长度。各平台默认值：TikTok 30-60 秒、Instagram Reels 60-90 秒、YouTube 60-180 秒、LinkedIn 60-120 秒
- **调性**：随意、专业、教育、有挑衅性、俏皮

若用户的请求含糊（例如"做个关于 AI 的视频"），就问有针对性的问题。能问就别猜。

### 第 2 步：调研题材

**这一步是强制的。** 不要跳过。调研档案正是把一支泛泛的讲解视频与一支有说服力的讲解视频区分开的东西。

用网络检索去调查：

1. **现有内容格局**：在 YouTube 和博客上检索这个题材已有的讲解视频。哪些角度已经被覆盖？缺什么？什么已经被做烂了？
2. **热门讨论**：在 Reddit、X/Twitter、Hacker News、Stack Overflow 上检索人们当下在问什么、在争论什么。存在哪些误解？什么让人意外？
3. **关键事实与数据**：找 3-5 个能支撑这支视频的、令人意外的统计数字、引语或事实。标注来源。
4. **视觉灵感**：最好的创作者是如何把这个概念可视化的？哪些类比有效？常用哪些图解？
5. **受众的知识缺口**：多数人对这个题材搞错了什么？"啊哈时刻"藏在哪里？

**本步骤的产出**：一份存在脑子里的调研档案。你不需要把它全部写下来，但要在你的角度方案中引用具体发现。

### 第 3 步：生成角度方案

生成**至少 3 个真正不同的角度**。不是换个说法 —— 而是对同一题材结构上就不同的路数。

对每个角度，写明：

| 字段 | 是什么 | 质量底线 |
|-------|------|-----------|
| `name` | 简短标题（5-8 词） | 要具体，不要泛泛。写"Why Vector Search Beats SQL LIKE"，不要写"About Vector Databases" |
| `hook` | 开场句/提问（15 词以内） | 必须用一句话制造好奇或意外 |
| `narrative_structure` | 故事如何展开 | 从中选一个：类比、问题-解决、旅程、辩论、破除迷思、时间线、对比 |
| `visual_approach` | 主要视觉风格 | 例如 "animated diagrams with vector space visualizations" |
| `suggested_playbook` | 最匹配的风格剧本 | 引用 `styles/` 中现有的 playbook |
| `target_audience` | 这个角度最适合谁 | 要具体："正在评估数据库的中级开发者"，而不是"开发者" |
| `why_this_works` | 理由 | 引用你的调研 —— 这个角度此刻为什么有说服力？ |

**角度多样性检查清单：**
- [ ] 至少一个角度偏技术/细致
- [ ] 至少一个角度偏直觉/易懂（用类比或故事）
- [ ] 至少一个角度有挑衅性/出人意料（挑战既有假设）
- [ ] 没有两个角度使用相同的叙事结构
- [ ] 每个角度都提出了不同的视觉路数

### 第 4 步：呈现给用户并选定

清晰地呈现所有角度方案。让用户：
- 原样选一个
- 让你把多个角度的元素组合起来
- 完全描述一个自定义方向

若用户给出自定义方向，就照做 —— 但要把第 2-3 步的调研和质量底线套上去。

### 第 5 步：组装 Brief

用全部必填字段和相关的可选字段构建 `brief` artifact：

```json
{
  "version": "1.0",
  "title": "...",
  "hook": "...",
  "key_points": ["...", "...", "..."],
  "core_message": "...",
  "cta": "...",
  "tone": "...",
  "style": "...",
  "target_audience": "...",
  "target_platform": "youtube|instagram|tiktok|linkedin|generic",
  "target_duration_seconds": 60,
  "reference_material": ["..."],
  "angle_options": [
    {"name": "...", "description": "..."},
    {"name": "...", "description": "..."},
    {"name": "...", "description": "..."}
  ],
  "selected_angle": "..."
}
```

**字段的质量底线：**

| 字段 | 优秀 | 平庸 |
|-------|-----------|----------|
| `title` | "How Vector Databases Find Your Data in 1ms" | "Vector Databases Explained" |
| `hook` | "Your database searches every single row. What if it didn't have to?" | "Today we'll learn about vector databases" |
| `key_points` | 视频将要证明的具体、明确的论断 | "它如何工作"这类含糊的话题 |
| `core_message` | 观众明天还该记得的一句话 | 缺失或太宽泛 |
| `cta` | 可执行且相关："Try building a similarity search with 10 lines of Python" | 泛泛："点赞订阅" |
| `tone` | 与受众和平台相匹配 | 不匹配（例如在 TikTok 上用企业腔） |

### 第 6 步：自评

提交之前，按这份评分表给你的 brief 打分（每项 1-5）：

| 标准 | 问题 |
|-----------|----------|
| **钩子强度** | 有人会为它停下滑动吗？它制造了信息缺口吗？ |
| **具体性** | key_points 是具体论断，而不是含糊话题吗？ |
| **调研深度** | brief 是否引用了第 2 步中真实的数据、趋势或洞察？ |
| **受众匹配** | 调性、复杂度和时长对目标受众合适吗？ |
| **Playbook 匹配** | 选定的风格是否真的贴合内容？ |
| **独特性** | 这个角度是否提供了现有内容格局中没有的东西？ |

若任何一项低于 3 分，就先迭代再提交。reviewer 会检查同样的标准。

### 第 7 步：提交

调用 `handle_explainer_idea(state, {"brief": brief_json})` 做校验并持久化。

## Playbook 选择指南

| 内容类型 | 推荐 Playbook | 理由 |
|--------------|----------------------|-----|
| 技术架构 | `minimalist-diagram` | 干净的图解，白板感 |
| 商业/SaaS 概念 | `clean-professional` | 精致、可信 |
| 社交媒体 / 快速讲解 | `flat-motion-graphics` | 抓眼球、数据驱动 |
| 故事 / 叙事 | 温暖类 playbook（吉卜力、水彩） | 建立情感连接 |
| 开发者教程 | `minimalist-diagram` 或自定义 | 聚焦代码/图解 |

若没有现成 playbook 合适，就在 `brief.style` 中描述期望的风格，管线之后可以创建一个自定义 playbook。

## 常见陷阱

- **跳过调研**：头号失败模式。没有调研，角度就是泛泛的，钩子就是弱的。
- **换汤不换药的角度**：三个"解释 X 如何工作"的变体不算三个角度。要改变叙事结构。
- **平台与时长不匹配**：3 分钟的讲解在 TikTok 上行不通。30 秒的视频讲不清 Kubernetes。
- **无视受众**：给 CTO 看的视频和给初级开发者看的视频，即便题材相同，框定方式也不同。
- **含糊的 key_points**："向量数据库如何工作"是一个话题，不是一个关键论点。"向量数据库用高维数学在毫秒级找到相似项"才是关键论点。

## 示例

### 好的角度组（题材："HTTPS 如何工作"）

**角度 1：间谍类比**
- 钩子："Every time you visit a website, you're having a secret conversation. Here's how."
- 结构：类比（间谍/谍报隐喻）
- 画面：动画角色传递密信
- Playbook：`flat-motion-graphics`
- 受众：大众、非技术人群

**角度 2：握手深度解析**
- 钩子："The TLS handshake takes 100 milliseconds and involves 4 messages. Here's what each one does."
- 结构：时间线/流程走查
- 画面：带数据包动画的技术图解
- Playbook：`minimalist-diagram`
- 受众：计算机专业学生、初级开发者

**角度 3：破除迷思**
- 钩子："The padlock icon doesn't mean what you think it means."
- 结构：破除迷思（先挑战既有假设，再揭示真相）
- 画面：分屏的误解前后对照
- Playbook：`clean-professional`
- 受众：商务专业人士、有安全意识的用户

### 差的角度组（同一题材）

- 角度 1："HTTPS Explained" —— 泛泛，没有钩子
- 角度 2："How HTTPS Works" —— 同一件事，换了说法
- 角度 3："Understanding HTTPS" —— 还是同一件事，结构上没有差别

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
