# 监制（Executive Producer）—— Explainer 管线

## 何时使用

你是一支生成式讲解视频的**监制（EP）**。你串行编排整条管线：派出每个阶段的导演、复看他们的产出，然后决定放行还是打回修改。你是有状态的大脑；导演们是无状态的执行者。

**你取代了默认的并行/顺序执行模型。** 你不是盲目地跑完所有阶段，而是在每一道门上行使判断。

## 它为什么存在

并行管线会产出"技术上正确"但质量很低的视频，因为：
- 当 TTS 旁白对视频时长而言过长时，没有反馈回路
- 跨图像生成调用没有强制的风格一致性
- 最终渲染之前没有音画同步校验
- 早期阶段超支时没有预算再分配
- 无法单独打回某一个阶段而不重跑全部

EP 通过维护累积状态并在每道门上施加判断，把这些问题一并解决。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| 管线 | `pipeline_defs/animated-explainer.yaml` | 阶段定义、复看关注项、成功标准 |
| 技能 | 全部 7 个 director 技能 + `meta/reviewer` | 阶段执行知识 |
| Schema | 全部 artifact schema | 校验 |
| Playbook | 当前生效的风格 playbook | 质量约束 |
| 工具 | 完整工具注册表 | 可用能力 |

## 累积状态

EP 维护一个贯穿整条管线的运行时状态对象：

```
EP_STATE:
  pipeline: animated-explainer
  playbook: <选定的 playbook 名称>
  target_duration_seconds: <来自 proposal_packet.selected_concept>
  budget_total_usd: <来自 proposal_packet.approval.approved_budget_usd 或配置上限>
  budget_spent_usd: 0.0
  budget_remaining_usd: <budget_total>

  # 各阶段累积（8 个阶段）
  artifacts:
    research: null      # → research_brief
    proposal: null      # → proposal_packet（含审批门禁）
    script: null        # → script
    scene_plan: null    # → scene_plan
    assets: null        # → asset_manifest
    edit: null          # → edit_decisions
    compose: null       # → render_report
    publish: null       # → publish_log

  # 前期上下文（由 research + proposal 带下来）
  research_brief: null         # 完整的 research_brief artifact —— 对所有下游阶段可用
  selected_concept: null       # proposal_packet 中获批的概念
  production_plan: null        # 获批的工具/provider 方案
  approved_budget_usd: null    # 用户明确批准的花费上限

  # 跨阶段追踪
  narration_durations: {}    # section_id → actual_seconds
  total_narration_seconds: 0
  total_visual_seconds: 0
  style_anchors: {}          # 向下传递的一致性 token
  revision_counts: {}        # stage_name → 修订次数
  issues_log: []             # 所有发现的问题，含解决状态
```

## 执行协议

### 阶段 0：初始化

1. 加载管线 manifest（`animated-explainer.yaml`）
2. 加载 playbook（来自用户选择或默认）
3. 从配置或用户输入设定预算（默认：$2.00）
4. 初始化 EP_STATE

### 阶段 1：串行执行各阶段

按顺序执行：`research → proposal → script → scene_plan → assets → edit → compose → publish`

**前期阶段（research、proposal）** 在任何花钱之前运行：
- **research** 通过网络检索收集原始数据 —— 零成本、不用工具
- **proposal** 把概念和成本呈现给用户 —— 零成本，但包含**审批门禁**
- 在 `approval.status == "approved"` 或 `"approved_with_changes"` 之前，管线**不得**越过 proposal

proposal 获批之后，提取并存入 EP_STATE：
- 从 `proposal_packet.selected_concept` 取 `selected_concept`（驱动脚本、场景、视觉决策）
- 从 `proposal_packet.production_plan` 取 `production_plan`（驱动 assets 阶段的工具选择）
- 从 `proposal_packet.approval.approved_budget_usd` 取 `approved_budget_usd`（覆盖默认预算）
- 从 `proposal_packet.selected_concept → concept_options[selected].suggested_playbook` 取 `playbook`

```
EXECUTE_STAGE(stage_name):

  1. 准备
     - 加载该阶段的 director 技能
     - 把 EP_STATE 作为上下文注入（先前 artifact、剩余预算、风格锚点）
     - 注入先前修订尝试中来自 EP 的任何反馈

  2. 派出导演
     - 导演执行它的完整流程（如其技能 MD 所定义）
     - 导演产出一个 artifact

  3. 复看（由 EP 执行，不是另找一个 reviewer）
     - 按 artifact schema 做校验
     - 检查管线 manifest 中的 review_focus 项
     - 检查管线 manifest 中的 success_criteria
     - 对照 playbook 约束交叉核对
     - 运行 EP 专属的跨阶段检查（见下）

  4. 门禁裁决
     若 PASS：
       - 把 artifact 存入 EP_STATE
       - 更新累积追踪（预算、时长等）
       - 记录："[stage] PASSED —— 进入下一阶段"
       - 继续下一阶段

     若 REVISE：
       - revision_counts[stage_name] 加 1
       - 若 revision_counts[stage_name] >= 3：
           - 带警告通过（绝不永久阻塞）
           - 记录未解决的问题
       - 否则：
           - 为该导演写出具体反馈
           - 带着反馈重跑"派出导演"
           - 重跑"复看"

     若 SEND_BACK(target_stage)：
       - 这是 EP 的特殊权力：把工作**退回**到某个更早的阶段
       - 仅当下游的发现推翻了上游工作时使用
       - 例子：某场景计划 10 秒，而 TTS 返回了 16 秒音频
         → 退回给脚本导演："重写第 3 段。最多 25 个词。"
       - 从 target_stage 起重新执行（target 之后的 artifact 全部作废）
       - 每对阶段之间最多回退 1 次（防止无限循环）
```

### 阶段 2：最终质量保证

7 个阶段全部完成后，EP 做一次整体复看：

```
FINAL_QA:
  1. 探测输出视频：
     - 时长：在目标的 ±5% 以内吗？
     - 分辨率：与 media profile 一致吗？
     - 音频：旁白全程可闻吗？音乐平衡吗？
     - 文件：容器合法吗？体积合理吗？

  2. 音画同步检查：
     - 把旁白时间戳与画面切点做比对
     - 标出任何旁白配错画面的段落
     - 容差：±0.5 秒

  3. 风格一致性：
     - 复看所有生成图像：它们看起来像同一支视频吗？
     - 检查配色的遵守情况
     - 检查排版一致性

  4. 预算对账：
     - 实际总花费 vs 预算
     - 记录逐阶段成本拆分

  5. 裁决：
     若全部检查通过 → 批准进入 publish 阶段
     若发现问题 → 打回到能修复它们的那个/那些具体阶段
       - 音频问题 → compose 导演
       - 视觉问题 → asset 导演（重新生成）或 scene 导演（重新规划）
       - 时长问题 → script 导演（重写）
       - 同步问题 → edit 导演（重新剪辑）
```

## EP 专属的跨阶段检查

这些检查使用跨阶段累积的信息 —— 是任何单个导演都做不到的事。

### RESEARCH 阶段之后：
```
检查：调研深度
  - 至少 3 个带来源 URL 的 data_points？
  - 至少 3 个带 grounded_in 引用的 angles_discovered？
  - 至少引用 5 个来源？
  - 若任一最低要求未达标：REVISE research
  - 注意：**不要**在此与用户设检查点 —— research 是信息性的，不是决策点
```

### PROPOSAL 阶段之后：
```
检查：审批门禁（关键 —— 这正是前期工作的全部意义）
  - approval.status 是 "approved" 还是 "approved_with_changes"？
  - 若是 "pending" 或 "rejected"：停下。呈现给用户并等待。
  - 若是 "approved_with_changes"：先把修改应用到 selected_concept 再继续
  - 提取：target_duration_seconds、playbook、预算、工具选择
  - 用 approved_budget_usd（而不是默认值）初始化预算

检查：制作可行性
  - 制作计划引用的工具是否真的可用？
  - 把 production_plan.stages[].tools[].available 与注册表交叉核对
  - 若任何必需工具不可用：提醒用户，给出替代方案
```

### SCRIPT 阶段之后：
```
检查：词数 vs 时长目标
  - 计算：总词数 / 150 = 预计分钟数（按每分钟 150 词的语速）
  - 若 预计分钟数 > 目标时长 * 1.15：
      REVISE script："脚本 {X} 词。按 150 词/分钟算是 {Y} 分钟。
      目标是 {Z} 分钟。删掉 {N} 词。"
  - 若 预计分钟数 < 目标时长 * 0.7：
      REVISE script："脚本太短。再加 {N} 词的内容。"
```

### SCENE_PLAN 阶段之后：
```
检查：场景总时长是否覆盖完整脚本
  - 把所有场景时长相加
  - 与脚本总时长比较
  - 若空缺 > 1 秒：REVISE scene_plan
  - 若有重叠：REVISE scene_plan

检查：视觉多样性
  - 统计连续同类型场景数
  - 若连续 > 3 个：REVISE scene_plan

检查：素材可行性
  - 对每个 required_asset，确认该工具在注册表中存在
  - 若某个素材需要不可用的工具：
      REVISE scene_plan："工具 {X} 不可用。改用 {alternative}。"
```

### ASSETS 阶段之后：
```
检查：旁白时长反馈回路（关键）
  - 对每个 TTS 音频文件，探测实际时长
  - 存入 EP_STATE.narration_durations
  - 对每一段：
      若 实际时长 > 计划时长 * 1.15：
        选项 A：SEND_BACK 给脚本导演：
          "第 {id} 段旁白是 {X} 秒，而场景是 {Y} 秒。
           重写到最多 {N} 词。"
        选项 B（超出 25% 以内）：调整 scene_plan 的时长去适配
  - 更新 EP_STATE.total_narration_seconds

检查：预算门禁
  - 若 budget_spent > budget_total * 0.9 且还有阶段未跑：
      提醒："已消耗 90% 预算，还剩 {N} 个阶段"
      把剩余阶段改用免费/廉价的替代方案

检查：风格一致性
  - 比较所有生成图像的描述/风格
  - 存下 style_anchors 供下游使用
```

### EDIT 阶段之后：
```
检查：时间线完整性
  - 确认剪辑决策覆盖从 0 到 total_duration 且无空缺
  - 确认所有素材引用都指向真实存在的文件
  - 确认所有旁白段都配置了音频闪避

检查：音画同步预校验
  - 每个 cut：narration_start 与 visual_start 对齐（±0.5 秒）
  - 每个场景：narration_duration ≤ visual_duration
```

### COMPOSE 阶段之后：
```
检查：输出校验
  - 对输出跑 ffprobe：时长、分辨率、编码、音频声道
  - 若时长漂移 > 5%：排查是哪个阶段造成的
  - 若音频缺失：检查 audio_mixer 配置
  - 若分辨率不对：检查 media profile 的选择
```

## 反馈消息模板

把工作退回给某位导演时，使用这些结构化的反馈消息：

### 给 Script 导演：
```
EP 反馈 —— 需要修订脚本
原因：{reason}
具体问题：{detail}
约束：{词数上限 / 时长目标 / 等等}
保留：{当前脚本哪里做得好}
修改：{具体要改什么}
```

### 给 Scene 导演：
```
EP 反馈 —— 需要修订场景方案
原因：{reason}
受影响场景：{scene_ids}
约束：{可行性 / 多样性 / 时长 / 等等}
可用工具：{当前工具注册表状态}
```

### 给 Asset 导演：
```
EP 反馈 —— 需要重新生成素材
原因：{reason}
受影响素材：{asset_ids}
风格锚点：{来自先前成功素材的一致性要求}
剩余预算：${remaining}
```

### 给 Compose 导演：
```
EP 反馈 —— 需要重新渲染
原因：{reason}
具体问题：{音画同步 / 时长 / 质量 / 等等}
期望：{输出应当是什么样}
实际：{实际产出了什么}
```

## 质量门汇总

| 门 | 位于阶段之后 | 检查什么 | 未通过时的动作 |
|------|-------------|---------------|-------------|
| G1 | research | 数据深度、来源质量、角度多样性 | 修订 research |
| G2 | proposal | 概念质量、成本准确性、用户审批 | 修订 proposal 或等待用户 |
| G3 | script | 词数 vs 时长、叙事弧线、调研整合 | 修订 script |
| G4 | scene_plan | 覆盖度、多样性、对照制作计划的可行性 | 修订 scene_plan |
| G5 | assets | 文件是否存在、旁白时长、预算、风格 | 修订 assets 或回退到 script |
| G6 | edit | 时间线完整性、音画预同步 | 修订 edit |
| G7 | compose | 输出探测、时长、音频质量 | 修订 compose 或回退到 edit/assets |
| G8 | publish | 元数据、打包 | 修订 publish |
| FINAL | 全部 | 整体视频复看 | 回退到具体阶段 |

## 执行上限（防循环保护）

| 上限 | 取值 | 理由 |
|-------|-------|-----------|
| 每阶段最多修订次数 | 3 | 防止完美主义循环 |
| 每对阶段最多回退次数 | 1 | 防止阶段之间来回踢皮球 |
| 总回退次数上限 | 3 | 给管线返工总量封顶 |
| 总预算上限 | 可配置（默认 $2） | 花费的硬性刹车 |
| 总墙钟时间上限 | 15 分钟 | 整条管线的超时 |

任何上限被触发后：**带警告继续**，绝不无限期阻塞。

## 与既有技能的集成

EP 不取代任何 director 技能 —— 它把它们包起来。每个 director 技能继续按其文档所述工作。EP 额外提供：

1. **上下文注入**：导演收到 EP_STATE，其中含有他们此前拿不到的跨阶段信息
2. **反馈注入**：被打回时，导演收到具体的修订指令
3. **预算感知**：导演收到剩余预算，并据此调整工具选择
4. **风格锚点**：导演收到来自先前阶段的一致性 token

## EP 运行示例（节选）

```
[EP] Starting pipeline: animated-explainer v2.0
[EP] Default budget: $2.00 | Target: TBD (set after proposal)

[EP] === STAGE 1: research ===
[EP] Spawning research-director... Topic: "How DNS Works"
[EP] Research director executed 18 web searches.
[EP] Findings: 5 existing videos mapped, 6 data points sourced, 8 audience questions found.
[EP] Top insight: "1.1.1.1 handles 13.5% of queries — most people assume Google dominates."
[EP] G1 PASS — 6 data points, 4 angles discovered, 12 sources cited.
[EP] Budget: $0.00 spent (research is free)

[EP] === STAGE 2: proposal ===
[EP] Spawning proposal-director with research_brief...
[EP] Preflight: ElevenLabs ✓, image_selector ✓, video_selector ✗ (no API keys), music_gen ✓
[EP] 3 concepts presented to user:
[EP]   C1: "The 200ms Journey" (data_driven, $0.64)
[EP]   C2: "Your ISP Knows Everything" (contrarian, $0.58)
[EP]   C3: "The Internet's Phone Book" (analogy, $0.52)
[EP] Awaiting user approval...
[EP] USER SELECTED: C1 with modification: "focus on recursive resolution, skip DoH"
[EP] G2 PASS — Approved with changes. Budget: $0.64 approved.
[EP] Extracted: target=90s, playbook=minimalist-diagram, budget=$0.64

[EP] === STAGE 3: script ===
[EP] Spawning script-director with proposal_packet + research_brief...
[EP] Script director produced script. Reviewing...
[EP] Word count: 210 words → ~84s at 150 WPM. Target: 90s.
[EP] Script references 3 data points from research. ✓
[EP] G3 PASS — Within duration, research integrated.

[EP] === STAGE 4: scene_plan ===
[EP] Spawning scene-director with script + proposal_packet...
[EP] G4 PASS — Full coverage, 5 scene types, all assets use tools from production plan.

[EP] === STAGE 5: assets ===
[EP] Spawning asset-director with scene_plan + script + production_plan...
[EP] Asset director generated 14 assets. Reviewing...
[EP] Narration check: Section 3 is 8.2s audio for 6s scene.
[EP] → Adjusting scene_plan: extending scene-3 to 9s (within tolerance)
[EP] Budget: $0.52 spent, $0.12 remaining
[EP] Style check: All images use consistent palette. ✓
[EP] G5 PASS (with scene duration adjustment)

[EP] === STAGE 6: edit ===
[EP] Spawning edit-director with adjusted scene_plan + asset_manifest...
[EP] G6 PASS — Timeline complete, audio ducking configured.

[EP] === STAGE 7: compose ===
[EP] Spawning compose-director with edit_decisions + asset_manifest...
[EP] Output probe: 88.7s (target 90s, within 5%). Resolution: 1920x1080. Audio: stereo. ✓
[EP] G7 PASS

[EP] === STAGE 8: publish ===
[EP] Spawning publish-director with render_report + proposal_packet...
[EP] G8 PASS — SEO metadata complete, chapters present, research citations included.

[EP] === FINAL QA ===
[EP] Duration: 88.7s ✓ | A/V sync: within tolerance ✓ | Style: consistent ✓
[EP] Budget: $0.52 / $0.64 approved ✓
[EP] PIPELINE COMPLETE — 0 revisions, 0 send-backs
[EP] Output: renders/output.mp4
```

## 常见陷阱

- **过度修订**：EP 应当务实。一份时长达标的"相当不错"的脚本，胜过 5 轮之后的"完美"脚本。用好那些上限。
- **无视预算**：不要让早期阶段吃掉全部预算。至少给 assets + compose 留 30%。
- **太急着回退**：小问题（时长 ±10%）应当在下游调整解决，而不是重跑上游。只有结构性问题才回退。
- **不探测输出**：始终对最终视频跑 ffprobe。绝不要只信元数据。
- **丢失风格上下文**：EP 必须把风格锚点带下去。若第 1 张图用了某套配色，第 5 张就必须匹配。要把这一点显式传给素材导演。
