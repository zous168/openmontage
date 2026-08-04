# 提案导演 —— Explainer 管线

## 何时使用

你是一支生成式讲解视频的**提案导演**。你位于调研导演与脚本导演之间。你接收一份塞满原始发现的 `research_brief`，并把它转化成一份具体、可复看的提案，供用户在任何花钱之前审批。

**这就是审批门禁。** 在用户说"走"之前，下游什么都不跑。你的工作是通过呈现清晰的选项、诚实的成本和明确的权衡，让这个决定变得容易。

把自己想象成一家在向客户提案的创意公司：你拿出有调研支撑的概念、展示花费、解释权衡，然后让客户选择。

## 运行时选择（必填字段 —— `render_runtime`）

讲解视频提案必须**同时**锁定 `renderer_family`（创意语法）和 `render_runtime`（技术引擎）。决策矩阵见 `skills/meta/animation-runtime-selector.md`，治理契约见 `AGENT_GUIDE.md` → "Present Both Composition Runtimes (HARD RULE)"。

**强制流程 —— 呈现两个运行时，不要静默取默认值：**

1. 查询 `video_compose.get_info()["render_engines"]`。若 `remotion` 和 `hyperframes` 都为 `True`，进入第 2 步。若只有一个可用，就只带这一个跳到第 4 步。
2. 结合本次 brief 的具体情况，把两个运行时呈现给用户。针对**这个**概念：
   - **Remotion** —— 一句话讲适配度（提一提适用的 React 场景栈组件），一句话讲权衡。
   - **HyperFrames** —— 一句话讲适配度（若适用，提一提 HTML/GSAP 运动、registry blocks、动态排版），一句话讲权衡。
3. 推荐其中一个，理由要与 brief 的 `delivery_promise`、`visual_approach`，以及是否需要词级字幕烧录（这一项会强制走 Remotion）挂钩。
4. 等待用户明确批准。批准之前**不要**把 `render_runtime` 写进 `proposal_packet.production_plan`。
5. 在 `decision_log` 中记录一条 `render_runtime_selection` 决策，`options_considered` 里包含**两个**运行时（若 `ffmpeg` 确实是现实选项也一并列上），用户的选择作为 `selected`，理由作为 `reason`。若某个运行时不可用，把它记为被否决，并注明 `rejected_because: "runtime not available on this machine"`。

用于给出**推荐**的适配速查（这是对话的输入，不是自动决策）：

- 现有的 React 场景栈（text_card、stat_card、bar_chart、line_chart、pie_chart、kpi_grid、callout、comparison、hero_title、字幕叠加、anime_scene）适用 → 推荐 **Remotion**。
- 动态排版、定制 HTML 动态图形、由 registry block 驱动的场景，或网页转视频 → 推荐 **HyperFrames**。
- 需要词级/卡拉 OK 式字幕 → Phase 1 中**只能用 Remotion**（字幕对等能力被推迟）。

若两个运行时都可用，而 `render_runtime_selection` 决策只考虑了一个选项，这是 CRITICAL 级的 reviewer 发现。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/proposal_packet.schema.json` | Artifact 校验 |
| 上游 artifact | 来自调研导演的 `research_brief` | 原始调研发现 |
| 管线 manifest | `pipeline_defs/animated-explainer.yaml` | 阶段与工具定义 |
| 工具注册表 | `support_envelope()` 的输出 | 此刻真正可用的能力 |
| 成本追踪 | `tools/cost_tracker.py` | 成本估算数据 |
| 风格 playbook | `styles/*.yaml` | 可用的视觉风格 |
| 元技能 | `skills/meta/taste-direction.md` | 设计判读、审美旋钮、参考策略 |
| 用户输入 | 题材、已表达的任何偏好 | 创意方向 |

## 流程

### 第 0 步：检查是否有参考视频上下文

开始提案工作之前，先看这个项目是否存在 VideoAnalysisBrief。

**当存在 VideoAnalysisBrief 时 —— 感知参考的概念设计：**

**硬规则：不许照抄。** 每个概念方案**必须**：
1. 点名至少**一个**从参考视频保留的元素（节奏、结构、调性、钩子风格）
2. 点名至少**一个**改变的元素（题材角度、视觉处理、旁白路数）
3. 解释这个改变**为什么**让产出更好，而不只是不同

**差异化范式：**

| 范式 | 示例 |
|---------|---------|
| **同结构，换题材** | 参考："黑洞如何运作" → 我们："中子星如何运作"，节奏相同 |
| **同题材，换角度** | 参考："Kubernetes 讲解" → 我们："从安全工程师视角看 Kubernetes" |
| **同调性，换视觉处理** | 参考：素材片段 + 配音 → 我们：动态图形 + 配音 |
| **同内容，换平台** | 参考：10 分钟 YouTube → 我们：60 秒 Shorts 版，节奏更快 |
| **反向观点** | 参考："AI 为什么会取代工作" → 我们："AI 为什么取代不了**你的**工作" |

**强制样片协议：** 用户批准某个概念之后、进入 script 阶段
**之前**，做一段 10-15 秒的样片：
1. 开场钩子（前 5-7 秒）+ 一个有代表性的中段场景
2. 真实的 TTS 音色、真实的视觉风格、音乐铺底片段
3. 呈现时说："这是一段预览。感觉对吗？"
4. 迭代到获批，然后再进入全量生产

**当不存在 VideoAnalysisBrief 时：** 跳过这一步，正常推进。

### 第 1 步：吸收调研

通读 `research_brief`。提取：

- **`research_summary`** —— 先读这个。这是调研者最重要的那一个发现。
- **`angles_discovered`** —— 这些是你原始的概念候选，且已经有调研支撑。
- **`data_points`** —— 尤其是 `surprise_factor` 为 `"counterintuitive"` 或 `"surprising"` 的那些。它们会成为钩子。
- **`audience_insights.misconceptions`** —— 破除迷思是经过验证的互动范式。
- **`landscape.underserved_gaps`** —— 机会就在这里。我们的视频应当填补空白，而不是重复已有内容。
- **`trending`** —— 若存在时效窗口，就把它计入概念的紧迫感。

### 第 2 步：运行 Preflight

设计概念之前，先弄清有哪些工具可用：

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.support_envelope(), indent=2))"
```

同时查看能力目录：

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.capability_catalog(), indent=2))"
```

记录：
- 有哪些 TTS provider 可用 —— 跑 `registry.get_by_capability("tts")` 并检查状态
- 有哪些视频生成 provider 可用 —— 跑 `registry.get_by_capability("video_generation")` 并检查状态
- 有哪些增强工具可用
- 图像生成状态 —— 跑 `registry.get_by_capability("image_generation")` 并检查状态
- **Remotion 渲染引擎状态** —— 检查 `video_compose.get_info()["render_engines"]["remotion"]`。若为 `true`，Remotion 就可用于动画文字卡、数据卡、图表、弹簧物理转场和图像转视频渲染。相比 Ken Burns 的平移缩放，这是一次重大的质量升级。

这直接影响你在制作计划里能承诺什么。**不要提出一个需要你没有的工具的概念。**

**安装提议：** 若关键工具 UNAVAILABLE 但只需简单配置就能修好，就从注册表读取每个工具的 `install_instructions`，在围绕这个限制去设计之前先向用户提供安装帮助。做法见 AGENT_GUIDE.md 的 "Provider Menu" 协议。把共用同一个环境变量依赖的相关工具分组。

### 第 2c 步：情绪板（先于概念）

在展开完整概念之前，先给一份快速情绪板，好尽早发现方向不匹配：

- **3-5 张参考图**（来自网络检索、素材库，或快速生成）
- **配色方向**（从候选 playbook 派生出的 2-3 个选项）
- **调性参照**（"想象一下：Kurzgesagt 遇上 Vice"，或"想象一下：苹果产品片遇上 TED-Ed"）
- **1-2 个音乐情绪参照**（曲风 + 能量水平，不是具体曲目）

问：**"这个**感觉**是不是你想象中的样子？有哪个跑偏了吗？"**

这比先做出 3 个完整概念便宜，也能在方向错位变得昂贵之前抓出来。若用户说"太企业了"或"再俏皮一点"，你就省下了一整轮概念。

若用户确认了方向，就继续。若他们改了方向，就调整你的概念设计去匹配。

### 第 3 步：设计概念方案

构建**至少 3 个真正不同的概念**。从 research brief 的 `angles_discovered` 出发，但要把它们提升为完整的制作概念。

对每个概念，写明 `proposal_packet.concept_options` schema 的全部字段：

#### 3a：标题与钩子

标题和钩子是最重要的两行。它们决定用户是兴奋起来还是划走。

**钩子构造范式**（用调研内容去填充它们）：

| 范式 | 模板 | 何时使用 |
|---------|----------|-------------|
| **意外数据** | "[反直觉的数字]。原因在这里。" | 当你有一个意外程度很高的数据点时 |
| **误解翻转** | "你被告知 [迷思]。事实是 [真相]。" | 当 audience_insights.misconceptions 里有一条很有力的条目时 |
| **时效性** | "[某事] 刚刚改变了关于 [题材] 的一切。看看发生了什么。" | 当 trending.recent_developments 里有一个及时的事件时 |
| **提问** | "为什么 [人人都经历过的事] 实际上会发生？" | 当 audience_insights.common_questions 里有一条很有力的条目时 |
| **对比** | "[事物 A] 需要 [大数字]。[事物 B] 只需 [小数字]。诀窍在这里。" | 当 data_points 里有对比数据时 |
| **内行知识** | "关于 [题材]，那件没人解释过的事。" | 当 landscape.underserved_gaps 揭示了一个明显空白时 |

**规则：**
- 钩子必须少于 20 词
- 钩子必须制造信息缺口 —— 观众需要看下去才能补上
- 钩子必须扎根于某个具体的调研发现（在 `grounded_in` 中引用它）
- 绝不要用："在这支视频里我们将……"、"大家好……"、"让我来解释……"

#### 3b：叙事结构

选择最贴合调研发现的结构：

| 结构 | 何时最合适 | 调研信号 |
|-----------|-----------|-----------------|
| `myth_busting` | 发现了强烈的误解 | `audience_insights.misconceptions` 有 2 条以上 |
| `problem_solution` | 痛点清晰 | `audience_insights.pain_points` 内容丰富 |
| `data_narrative` | 有强烈的意外数据 | 多个高 surprise_factor 的 data_points |
| `comparison` | 有两种做法可比 | data_points 中含对比数据 |
| `timeline` | 题材有演进/历史 | 格局显示这个题材随时间在变化 |
| `journey` | 复杂题材需要渐进揭示 | `audience_insights.knowledge_level` 显示存在大缺口 |
| `analogy` | 抽象题材需要落地 | 受众非技术背景 |
| `debate` | 社区意见分裂 | `trending.active_discussions` 显示存在分歧 |
| `tutorial` | 受众想**动手做**某事 | `audience_insights.common_questions` 都是操作类问题 |
| `story` | 存在人情味切入角度 | 有专家声音或真实案例可用 |

#### 3c：视觉识别 —— 去**设计**它，而不是去**挑**它

**你的工作是为**这支**视频设计一套视觉识别，而不是从预设菜单里挑一个。**

现有的 playbook（`clean-professional`、`flat-motion-graphics`、`minimalist-diagram`）是起点，不是终点。多数视频都应当获得一套由题材、受众和调性推导出来的**定制视觉识别**。一支关于咖啡的视频应当有温暖、可触摸的感觉。一支关于网络安全的视频应当有技术感和紧迫感。一支关于海洋生物的视频应当有深邃、流动的感觉。

在选择或生成 playbook 之前，先读 `skills/meta/taste-direction.md` 并写一份紧凑的 `production_plan.taste_profile`。这份审美档案记录设计判读、`visual_variance`、`motion_intensity`、`information_density`、参考策略和反模式。用它来解释为什么选定的 playbook、`composition_mode` 和素材策略贴合这个 brief。

**如何设计视觉识别：**

1. **从内容出发。** 这个题材天然唤起什么颜色？什么质感、材质、光照？一支关于火山的视频，在颜色、运动速度、字重和转场风格上，都应当与一支关于冥想的视频不同。

2. **考虑受众。** Z 世代的 TikTok 受众期待醒目、高对比、快速的运动。企业培训受众期待克制、专业、易读。儿童教育受众期待明亮、俏皮、有弹性。

3. **考虑调性。** 用户的情绪板和创意需求收集应当指导这一点。"电影感"意味着与"俏皮"不同的颜色/运动，而"俏皮"又与"临床感"不同。

4. **从题材出发构建配色。** 不要默认用蓝色。挑 2-3 个服务于内容的颜色：
   - 主色：占主导的品牌/氛围色
   - 强调色：用于强调、数据、高亮
   - 背景色：奠定整体情绪（浅 = 亲和，深 = 戏剧化/技术感）

5. **只有当预设 playbook 真的合适时才用它。** 若这支视频就是一个直白的企业讲解，`clean-professional` 没问题。但若题材有它自己的视觉世界（自然、太空、食物、音乐、体育、历史），就去设计一套定制识别。

6. **预设都不匹配时就生成一个自定义 playbook。** 用 `lib/playbook_generator.py` 从你的设计决策生成一个。Remotion 的主题系统会自动从你创建的任何 playbook（包括自定义的）中派生颜色、字体和运动。

**把你的视觉识别选择记入 proposal_packet：**
- `production_plan.playbook`：预设名称，或 "custom"
- `production_plan.taste_profile`：设计判读、审美旋钮、参考策略和反模式
- 若是自定义，把颜色选择和字体选择写进该概念的 `visual_approach`
- 附上理由："用温暖的琥珀色配色，因为题材是咖啡手艺"
- 记入决策：`category: "playbook_selection"`

**检查 Remotion 可用性** —— 若 `video_compose` 报告 `render_engines.remotion: true`，就为动画组件（文字卡、数据卡、图表、弹簧转场）来设计。这是一次重大的质量升级。

**可用的 Remotion 组件**（当 Remotion 引擎启用时）：
- `text_card` —— 带弹簧入场的动画文字
- `stat_card` —— 数字 + 标签，配数字滚动动画
- `callout` —— 高亮的说明框
- `comparison` —— 并排对照，带动画揭示
- `progress` —— 动画进度条
- `chart` —— 柱状、折线、饼图，带数据入场动画
- `kpi_grid` —— 多指标的仪表盘版式

**重要：** 当 Remotion 可用时，**始终为 Remotion 组件场景做设计**，而不是用静态 AI 生成图像加 Ken Burns 平移。这就是专业动态图形视频与幻灯片之间的差别。

#### 3d：时长与平台

根据平台和内容深度设定现实的时长：

| 平台 | 时长区间 | 词数预算（150 词/分钟） |
|----------|---------------|----------------------|
| TikTok | 30-60 秒 | 65-150 词 |
| Instagram Reels | 30-90 秒 | 65-225 词 |
| YouTube Shorts | 30-60 秒 | 65-150 词 |
| YouTube | 60-180 秒 | 150-450 词 |
| LinkedIn | 60-120 秒 | 150-300 词 |

#### 3e：何时打破这些范式

上面的钩子范式和叙事结构是起点，不是模板。以下这些迹象说明你应当发明一些新东西：

**你的概念只是表面多样、实则概念雷同的迹象：**
- 三个钩子制造的是同一类好奇缺口
- 把钩子在概念之间对调，几乎不会有任何变化
- 若你蒙着眼睛写，这三个会产出大致相同的脚本
- 视觉路数是"暗 vs 亮 vs 彩色"，但内容结构完全相同

**反公式规则：** 先用你自己的话把钩子写出来。然后再看某个范式能否帮你把它磨得更锋利。若你**从**范式出发，你会产出被范式塑形的内容，而不是被调研塑形的内容。

**何时偏离这 6 个钩子模板：**
- 调研揭示了一种不适配任何模板的独特框架
- 受众足够老练，以致模板式钩子显得居高临下
- 这个题材最好的角度是情绪性的，而不是信息性的
- 你找到了一句具体的引语、一段轶事或一个事件，它本身**就是**钩子

#### 3f：概念多样性门禁

这是两项检查，不是一项：

**结构多样性（必要但不充分）：**
- [ ] 没有两个概念使用相同的叙事结构
- [ ] 没有两个概念使用相同的钩子范式
- [ ] 每个概念的 `grounded_in` 引用的是不同的调研发现

**概念多样性（真正的考验）：**
- [ ] 每个概念提供的是真正不同的**洞察**，而不只是同一洞察的另一个标题
- [ ] 至少一个概念冒了创意上的风险（不寻常的结构、出人意料的角度、有挑衅性的框架）
- [ ] 若你把标题和钩子拿掉，这些概念仍然能凭内容结构被区分开
- [ ] 这些概念**不是**可互换的 —— 每个都服务于不同的受众需求或好奇心

若你的概念没通过概念多样性测试，就回到 research brief。问题通常在于：你是从**一个**角度出发去变换表面，而不是从**不同的**角度分别出发。

#### 3g：Playbook 违规预算

最终视频中最多 20% 的场景，可以为了创意冲击而有意偏离 playbook。呈现概念时，注明哪些时刻可能受益于视觉上的意外（一次色彩转变、一种不同的排版处理、一个出人意料的转场）。这些偏离必须在 decision log 中记为 `playbook_override` 决策。

#### 3h：配音选择

在提案时就把配音/TTS 决策摆出来：
- 会用哪个配音 provider 和哪个音色 ID
- 为什么这个音色贴合这个概念的调性
- 成本影响
- 主镜头时刻是否适合做音色变化

### 第 4 步：渐进式披露与概念选定

不要一次性倒出完整提案。逐步建立共识：

**4a. 调研摘要**（2-3 句）："这是我发现的……"
→ 用户做出反应，必要时纠偏。

**4b. 情绪板**（来自第 2c 步 —— 已呈现）
→ 用户确认感觉。

**4c. 概念方案**（3 个以上方向）：

对每个概念，展示：
1. **标题**与**钩子** —— 创意卖点
2. **它为什么奏效** —— 一句话的调研支撑
3. **它看起来会是什么样** —— 用平实语言描述视觉路数
4. **时长** —— 视频会有多长

**4d. 邀请混搭：**

呈现完概念之后，始终说一句类似这样的话：
> "你也可以混搭 —— 比如概念 A 的钩子配概念 C 的视觉路数。哪种更打动你？"

若用户做了混搭，就在 proposal_packet 中创建一个新的混合概念条目，并清楚注明出处："钩子来自概念 A，视觉路数来自概念 C，叙事结构来自概念 B。"

让用户：
- 原样选一个
- 从多个概念中组合元素（混合）
- 提出修改
- 描述一个完全不同的方向（这种情况下，用调研去把它做强）

**4e. 选定概念的制作计划**（工具、成本、时间线）：
→ 用户批准预算和方式。

每一步都是让用户在下一步基于它继续之前纠偏的机会。这能防止"我批准了一份提案，然后视频却不是我预期的样子"这种失败模式。

把选择连同理由和任何修改记入 `selected_concept`。

### 第 5 步：构建制作计划

为选定的概念设计逐阶段的制作计划。

对管线 manifest（`animated-explainer.yaml`）中的每个阶段，写明：

1. **会用哪些工具** —— 具体的 provider 名称，而不只是 selector
2. **每个工具是否可用** —— 来自 preflight 检查
3. **每个工具的成本估算** —— 来自该工具的成本元数据
4. **为什么选这个 provider** —— 解释这个选择（"旁白用 ElevenLabs，因为这个题材对音色质量要求很高"，或"用 Piper TTS，因为只跑本地且免费"）
5. **不可用时的兜底** —— 主工具挂了会怎样

**工具选择的理由必须诚实：**
- 若因为云端工具不可用而使用免费/本地工具，就说出来
- 若在本地已有替代方案的情况下仍用云端工具，就解释质量上的权衡
- 若某项能力完全缺失，就说清这支视频会缺什么

#### 质量/成本权衡矩阵

对每个有实质意义的选择，把权衡摆出来：

```
权衡：TTS Provider
├── 高端：ElevenLabs（$0.18-0.30）—— 音色自然，有情绪演绎
├── 标准：OpenAI TTS（$0.05-0.15）—— 质量不错，表现力略弱
└── 免费：Piper 本地（$0.00）—— 机械但能离线用

权衡：视觉素材
├── 高端：AI 视频片段（每段 $0.10-0.50）—— 有运动，有动感
├── 标准：AI 图像（每张 $0.02-0.04）—— 静态，稳定
└── 免费：图表/代码（$0.00）—— 以文本为主，技术感

权衡：渲染路径（检查 video_compose 的 render_engines）
├── Remotion（$0.00，本地）：动画文字卡、数据卡、图表、
│   弹簧物理转场、基于组件的场景。专业的
│   动态图形观感。需要 Node.js。
└── FFmpeg（$0.00，本地）：图像上的 Ken Burns 平移缩放、视频
    拼接。功能可用，但对讲解内容而言吸引力较弱。
```

**若 Remotion 可用：** 围绕 Remotion 的组件类型（text_card、stat_card、chart 等）来设计场景方案，而不是为每个场景生成 AI 图像。这样既更便宜（图像生成调用更少），质量也更高（动态图形 vs 带平移的静图）。

同时呈现**替代制作路线** —— 不同价位的完整方案包：

| 路线 | 质量 | 成本 | 有什么变化 |
|------|---------|------|-------------|
| 高端 | 最好的 TTS + 视频片段 + 音乐 | 约 $1.50-2.50 | 完整的制作水准 |
| 标准 | 不错的 TTS + 图像 + 音乐 | 约 $0.50-1.00 | 静态视觉，但依然专业 |
| 省钱 | 本地 TTS + 图像 | 约 $0.05-0.15 | 机械音色，只有图像 |
| 免费 | 本地 TTS + 图表 | $0.00 | 功能可用但很简朴 |

### 第 5b 步：音乐方案（必备）

音乐是视频观感中至关重要的一部分。**在提案时就把音乐的情况呈现给用户** —— 不要静默地把它推迟到 assets 阶段，那时出问题的代价会很高。

**按此顺序检查音乐可用性：**

1. **用户音乐库（`music_library/`）：** 检查这个目录是否存在、是否有曲目。若有，列出可用曲目及时长，让用户来挑。
2. **音乐生成 API：** 通过注册表检查有哪些音乐工具可用（`registry.get_by_capability("music_generation")`）。如实报告其状态。
3. **素材音乐来源：** 若有任何 provider 提供素材音乐，就注明。

**呈现给用户：**

```
音乐方案
├── 你的音乐库：3 首可用
│   ├── cosmic_interstellar_space.mp3（3:13）—— 氛围、宇宙感
│   ├── cinematic_epic.mp3（2:45）—— 戏剧、渐强
│   └── lofi_beat.mp3（4:00）—— 慵懒、电子
├── AI 生成：music_gen（ElevenLabs）—— 不可用（套餐额度用尽）
└── 推荐：使用你音乐库里的 "cosmic_interstellar_space.mp3"
    或在素材生成之前提供另一首曲子

你想要：
  (a) 用音乐库里的一首（哪一首？）
  (b) 自己提供一首（放进 music_library/）
  (c) 通过 API 生成（若可用）
  (d) 不用音乐继续
```

**若没有任何音乐来源可用：** 明确告诉用户。不要让它在 assets 阶段变成意外。给出 `music_library/` 这条路，让他们能在生产开始前放一首曲子进去。

**规则：**
- 始终先检查 `music_library/` —— 用户自带的音乐既免费又是有意为之
- 始终报告音乐 API 的状态（可用、不可用，若能查到还包括剩余额度）
- 把音乐决定记入 `proposal_packet.production_plan.music_source`
- 若用户选了音乐库里的曲目，就为素材导演记下它的路径

### 第 6 步：构建成本估算

把每一项付费操作逐条列出：

```
成本估算
├── TTS 旁白：tts_selector × 1 次（约 150 词）       $0.18
├── 图像生成：image_selector × 6 个场景                  $0.24
├── 音乐：music_gen × 1 首（30 秒）                        $0.10
├── 视频生成：video_selector × 2 段（可选）   $0.00（本地）
├── 音频增强：audio_enhance × 1 遍               $0.00（本地）
└── 合计估算                                         $0.52
    预算上限：$2.00
    结论：within_budget ✓
    余量：$1.48 供修订/重新生成使用
```

**规则：**
- 始终展示逐项成本，而不只是总额
- 始终展示与预算上限的对比
- 若超预算，列出具体的省钱选项（例如"换一个更便宜的 TTS provider：省 $0.18" —— 通过注册表查各 provider 的 `estimate_cost`）
- 附上余量说明 —— 应当留一部分预算给修订

### 第 7 步：组装审批门禁

审批小节是用户做出承诺的地方。把它呈现为一个清晰的决策点：

```
────────────────────────────────────────
提案已就绪，待审批

概念：[选定标题]
时长：面向 [平台] 的 [X] 秒
成本估算：$[X.XX]，预算 $[budget]
制作路线：[高端/标准/省钱/免费]

继续吗？（批准 / 有条件批准 / 否决）
────────────────────────────────────────
```

在 artifact 中把 `approval.status` 设为 `"pending"`。EP 或用户会在管线继续之前把它更新为 `approved`。

**关键规则：** 未经明确批准，管线**不得**越过这个阶段。这是最后一个免费的退出口。这之后的一切都要花钱和时间。

### 第 8 步：提交

按 `schemas/artifacts/proposal_packet.schema.json` 校验 `proposal_packet` artifact 并提交。

## 它如何连接下游

| 下游阶段 | 它从 proposal_packet 中取什么 |
|------------------|------------------------------------|
| 脚本导演 | `selected_concept`（标题、钩子、key_points、core_message、调性、narrative_structure）+ research_brief 的数据点 |
| 场景导演 | `selected_concept.visual_approach` + `production_plan.playbook` |
| 素材导演 | `production_plan.stages[assets].tools` —— 确切知道该用哪些 provider |
| 监制 | `cost_estimate` —— 初始化预算追踪 |
| 所有阶段 | `approval.approved_budget_usd` —— 硬性花费上限 |

proposal_packet 中的 `selected_concept` 实际上取代了旧的 `brief` artifact —— 但它有调研作根基，并且附带一份明确的制作计划。

## 常见陷阱

- **呈现没有调研支撑的概念**：每个概念的 `why_this_works` 都必须引用具体的调研发现。"这是个热门题材"不算支撑。"Cloudflare Radar 显示 13.5% 的 DNS 查询命中 1.1.1.1，这与'Google DNS 占主导'的普遍认知相矛盾"才算支撑。
- **隐瞒成本**：要透明。若 ElevenLabs 要花 $0.30，就说 $0.30。不要往下取整或漏项。你越诚实，用户越信任你。
- **过度承诺工具可用性**：若 preflight 显示只有 Piper TTS 可用，就不要设计一个依赖富有表现力的配音演绎的概念。要围绕约束来设计。
- **同一个概念的三个版本**："Kubernetes Explained"、"Understanding Kubernetes" 和 "Kubernetes Guide" 不是三个概念。它们是同一个概念的三个标题。结构多样性意味着不同的叙事结构、不同的钩子、不同的受众。
- **跳过审批门禁**：这就是前期工作的全部意义。没有捷径。
- **不展示替代方案**：用户始终应当看到至少 2 条不同价位的制作路线。让他们做知情的选择。

## 示例：完整提案流程

### 输入：关于"HTTPS 如何工作"的 research_brief

**概念 1："The 200ms Journey"（data_driven）**
- 钩子："Every website you visit starts with a 200-millisecond treasure hunt across the internet."
- 结构：journey —— 逐步跟随一次 DNS 查询
- 视觉：定制的信号地图识别 —— 午夜色背景、电光路径轨迹、数据包流动的运动语言
- 时长：90 秒（YouTube）
- 支撑：递归解析的时序数据、受众对多步骤流程的认知缺口
- 它为什么奏效：多数观众以为 DNS 是瞬时且单次的。展示真实的旅程就是那个"啊哈"时刻。

**概念 2："Your ISP Knows Everything"（contrarian）**
- 钩子："Your internet provider logs every website you visit. Here's the 40-year-old system that makes it possible."
- 结构：myth_busting —— 挑战"隐私浏览 = 隐私"的信念
- 视觉：定制的监控黑色电影识别 —— 低调对比、隐私警示色、克制的排版
- 时长：75 秒（YouTube）
- 支撑：DNS 隐私误解（受众调研）、DoH 的热度信号
- 它为什么奏效：隐私自带情绪张力。"HTTPS = 完全隐私"这个误解非常普遍。

**概念 3："The Internet's Phone Book"（analogy）**
- 钩子："DNS is a phone book designed in 1983 that somehow still runs the modern internet."
- 结构：analogy —— 用电话簿隐喻贯穿历史演进
- 视觉：定制的复古系统识别 —— 米白纸质底、档案感字体、当代节拍用霓虹现代感做反差
- 时长：60 秒（LinkedIn）
- 支撑：受众对 DNS 年龄的认知缺口、格局空白（没找到历史视角的内容）
- 它为什么奏效：对非技术受众而言门槛最低。"用了 40 年还在跑"这个角度本身就令人意外。

**制作计划（选定概念 1，Remotion 可用）：**
```
script   → 无工具，无成本
scene    → 无工具，无成本 —— 设计 4 个 Remotion 组件场景 + 4 个 AI 图像场景
assets   → tts_selector（$0.22）、image_selector × 4（$0.16）、music_gen（$0.10）
edit     → 无工具，无成本
compose  → video_compose/Remotion 渲染（免费）—— 动画文字卡、数据卡、
           弹簧转场、带动画的图像场景。**不是** Ken Burns。
publish  → 无工具，无成本
合计：$0.48，预算 $2.00（因为文字/数据场景改用 Remotion 组件而不是生成图像，
       省下了 $0.16）
```

**制作计划（选定概念 1，只有 FFmpeg）：**
```
script   → 无工具，无成本
scene    → 无工具，无成本
assets   → tts_selector（$0.22）、image_selector × 8（$0.32）、music_gen（$0.10）
edit     → 无工具，无成本
compose  → video_compose/FFmpeg（免费）—— 图像上的 Ken Burns 平移缩放
publish  → 无工具，无成本
合计：$0.64，预算 $2.00
```

**替代路线：**
- 高端（Remotion）：可用的最好 TTS + 4 张 AI 图像 + 4 个 Remotion 动画场景 = $0.48
- 标准：中档 TTS + 图像 = $0.40
- 免费：本地 TTS + 仅 Remotion 组件场景 = $0.00（无图像，纯动态图形）


## 当你不知道该怎么做时

若你遇到一种拿不准的生成技法、provider 行为或提示词范式：

1. **上网检索**当前最佳实践 —— 模型和 API 变动频繁，agent 的训练数据可能已经过时
2. **查 `.agents/skills/`** 中已有的 Layer 3 知识（provider 专属提示词指南、API 范式）
3. **若两者都无济于事**，在 `projects/<project-name>/skills/<name>.md` 写一份项目作用域的技能，记录你学到的东西
4. 在技能中**引用来源 URL**，让知识可追溯
5. 在 decision log 中**记录它**：`category: "capability_extension"`、`subject: "learned technique: <name>"`

这对以下情况尤其重要：
- **视频生成提示词** —— 模型响应的是随版本变化的特定词汇
- **图像模型参数** —— FLUX、GPT Image、Imagen 的最优设置各不相同且在演进
- **音频 provider 的怪癖** —— 音色克隆、音乐生成和 TTS 各有其模型专属的最佳实践
- **Remotion 组件范式** —— 随框架演进会出现新的合成技法

不要依赖过时的知识。拿不准就先检索。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
