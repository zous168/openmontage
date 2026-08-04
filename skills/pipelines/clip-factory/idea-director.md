# 创意导演 —— Clip Factory 管线

## 何时使用

当源素材是长视频、目标是产出多条短视频交付物时使用本管线：网络研讨会片段、访谈剪辑、直播亮点、主题演讲摘录，或演示片段。

你规划的不是一支视频。你规划的是一份按优先级排序的片段组合。

## 运行时选择（强制 —— 把约束讲出来，不要静默选定）

锁定 `render_runtime = "remotion"`（用于带词级字幕的合成片段）或 `"ffmpeg"`（用于纯拼接/修剪、不做合成）。**在 Phase 1 中，HyperFrames 在本管线上不是合法运行时** —— clip-factory 依赖 Remotion 的词级字幕烧录，而 HyperFrames 尚无对等能力。

按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：**不要**静默锁定 remotion。把约束呈现给用户："你的机器上有 HyperFrames，但 clip-factory 依赖 Remotion 的字幕烧录，而 HyperFrames 还没有对等能力，所以这里 remotion 是唯一可行的选择 —— 可以这样推进吗？" 把决定记入 `decision_log`，category 为 `render_runtime_selection`，并把 hyperframes 作为被否决的选项列上（`rejected_because: "caption-burn parity deferred on clip-factory"`）。

## 参考输入

- `docs/clip-factory-best-practices.md`
- `skills/creative/short-form.md`
- `skills/creative/video-editing.md`

## 流程

### 1. 弄清源素材与目标

记录源素材的形态：

- 网络研讨会
- 访谈
- 圆桌
- 主题演讲
- 直播
- 客户故事

然后记录业务目标：

- 品牌认知
- 思想领导力
- 获取线索
- 产品教育
- 活动回顾

### 2. 选定片段组合策略

好的一批片段会混合多种片段类型，而不是反复提取同一种能量。

常见的片段族：

- `hook`：出人意料的论断或有力的冷开场
- `insight`：有用的收获或经验
- `story`：带情绪形状的叙事时刻
- `proof`：数据、案例研究、演示结果
- `opinion`：犀利观点、异议、反常识论断

用 brief 的元数据来定义这些族之间的预期配比。

### 3. 现实地设定产出量目标

参考区间：

- `15-30 分钟`：3-6 条优质片段
- `30-60 分钟`：5-10 条优质片段
- `60 分钟以上`：若源素材质量支撑得住，8-15 条优质片段

不要为了凑个整数而虚增片段数量。一批小而强，胜过一批注水的弱片段。

### 4. 在提取之前先映射平台

尽早规划平台适配：

- Shorts、Reels、TikTok 用 `9:16`
- LinkedIn 和更稳妥的信息流再利用用 `1:1`
- 当幻灯片、演示或宽画幅语境很重要时用 `16:9`

若源素材的构图明显扛不住竖屏裁剪，现在就在 brief 元数据里说明。

### 5. 构建 Brief

schema 层面的 brief 保持简洁，把更丰富的批次方案放进 `brief.metadata`。

推荐的元数据键：

- `source_type`
- `source_duration_seconds`
- `clip_target_range`
- `clip_families`
- `primary_platforms`
- `secondary_platforms`
- `selection_criteria`
- `known_visual_constraints`
- `distribution_goal`

### 6. 质量门

- 片段数量目标现实，
- 平台配比与内容相符，
- brief 在提取开始之前就定义了排序标准，
- agent 已经承认了任何明显的重新构图限制。

## 常见陷阱

- 围绕数量而非质量来规划一批片段。
- 假定每个源素材都能干净地产出竖屏片段。
- 把所有片段当成可互换的，而不是刻意做出差异。
- 还没定义清楚这一批的"好"是什么，就开始提取。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
