# 监制（Executive Producer）—— Animation 管线

## 何时使用

你是一支生成式动画视频的**监制（EP）**。你串行编排整条管线：派出每个阶段的导演、复看他们的产出，然后决定放行还是打回修改。你是有状态的大脑；导演们是无状态的执行者。

**你取代了默认的并行/顺序执行模型。** 你不是盲目地跑完所有阶段，而是在每一道门上行使判断。

## 它为什么存在

动画管线有一些并行执行抓不到的独特失败模式：

- 场景各自独立生成时，运动一致性会崩
- 数学准确性的错误若不在 script 之后抓出来，会一路放大
- 动画时序需要停留时长和揭示节奏，缺乏跨阶段视野时它们会被挤掉
- 各阶段独立规划时，复用策略会退化
- AI 生成素材与免费程序化动画之间的预算分配需要主动管理
- 文字可读性和图表锐利度必须在 compose 阶段验证，不能想当然

EP 通过维护累积状态并在每道门上施加动画专属的判断，把这些问题一并解决。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| 管线 | `pipeline_defs/animation.yaml` | 阶段定义、复看关注项、成功标准 |
| 技能 | 全部 9 个 director 技能 + `meta/reviewer` | 阶段执行知识 |
| Schema | 全部 artifact schema | 校验 |
| Playbook | 当前生效的风格 playbook | 质量约束 |
| 工具 | 完整工具注册表 | 可用能力 |

## 累积状态

EP 维护一个贯穿整条管线的运行时状态对象：

```
EP_STATE:
  pipeline: animation
  playbook: <选定的 playbook 名称>
  target_duration_seconds: <来自 proposal_packet.selected_concept>
  budget_total_usd: <来自 proposal_packet.approval.approved_budget_usd 或配置上限>
  budget_spent_usd: 0.0
  budget_remaining_usd: <budget_total>

  # 动画专属状态
  # 方式：
  #   image_animation  — 通过 Remotion 做多图交叉淡化（动画/吉卜力/插画风格）
  #   clip_video       — 把 AI 生成的视频片段合成为一个故事
  #   manim            — 通过 ManimCE 做程序化的数学/物理动画
  #   remotion_dataviz — 用 Remotion 组件做数据可视化（可零 key 完成）
  #   diagram_stills   — 图表 + 图像静图，配 Ken Burns
  #   mixed            — 逐场景组合多种方式
  animation_mode: <image_animation | clip_video | manim | remotion_dataviz | diagram_stills | mixed>
  reuse_strategy:
    recurring_motifs: []
    layout_system: null
    transition_family: null
    typography_hierarchy: null
    unique_scene_count: 0
    reused_template_count: 0
  math_accuracy_notes: []      # 调研得出的、不能过度简化之处的约束

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
  research_brief: null         # 完整的 research_brief artifact
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

1. 加载管线 manifest（`animation.yaml`）
2. 加载 playbook（来自用户选择或默认）
3. 从配置或用户输入设定预算（默认：$2.00）
4. 初始化 EP_STATE

### 阶段 1：串行执行各阶段

按顺序执行：`research → proposal → script → scene_plan → assets → edit → compose → publish`

**前期阶段（research、proposal）** 在任何花钱之前运行：
- **research** 通过网络检索收集主题数据**和**动画技法参考 —— 零成本
- **proposal** 把带动画模式选择和成本的概念呈现给用户 —— 零成本，但包含**审批门禁**
- 在 `approval.status == "approved"` 或 `"approved_with_changes"` 之前，管线**不得**越过 proposal

proposal 获批之后，提取并存入 EP_STATE：
- 从 `proposal_packet.selected_concept` 取 `selected_concept`
- 从 `selected_concept.animation_mode` 取 `animation_mode`
- 从 `selected_concept.reuse_strategy` 取 `reuse_strategy`
- 从 `proposal_packet.production_plan` 取 `production_plan`
- 从 `proposal_packet.approval.approved_budget_usd` 取 `approved_budget_usd`
- 从 `proposal_packet.selected_concept → suggested_playbook` 取 `playbook`
- 从 research_brief 取 `math_accuracy_notes`（若适用）

```
EXECUTE_STAGE(stage_name):

  1. 准备
     - 加载该阶段的 director 技能
     - 把 EP_STATE 作为上下文注入（先前 artifact、剩余预算、风格锚点、动画模式、复用策略）
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
       - 仅当下游的发现推翻了上游工作时使用
       - 从 target_stage 起重新执行（target 之后的 artifact 全部作废）
       - 每对阶段之间最多回退 1 次（防止无限循环）
```

### 阶段 2：最终质量保证

所有阶段完成后，EP 做一次整体复看：

```
FINAL_QA:
  1. 探测输出视频：
     - 时长：在目标的 ±5% 以内吗？
     - 分辨率：与 media profile 一致吗？
     - 音频：旁白全程可闻吗？音乐平衡吗？
     - 文件：容器合法吗？体积合理吗？

  2. 文字与图表锐利度（动画专属）：
     - 文字元素在目标分辨率下可读吗？
     - 图表线条是否锐利、没有因缩放而发糊？
     - 数学符号渲染正确吗？
     - 跨场景的排版层级是否保持一致？

  3. 运动一致性：
     - 转场是否遵循声明的转场家族？
     - 停留时长是否被保留（没有被时序挤掉）？
     - 错峰揭示是否播放正确？
     - 节奏是否适合动画（不赶）？

  4. 风格一致性：
     - 所有场景是否遵循复用策略？
     - 配色是否一致？
     - 反复出现的母题是否在各场景中正确出现？

  5. 数学准确性（若适用）：
     - 动画中的公式/图解是否与 research brief 的准确性备注一致？
     - 调研中标出的那些简化，现在是否依然正确？

  6. 预算对账：
     - 实际总花费 vs 预算
     - 记录逐阶段成本拆分

  7. 裁决：
     若全部检查通过 → 批准进入 publish 阶段
     若发现问题 → 打回到能修复它们的那个/那些具体阶段
       - 文字/图表问题 → compose 导演（重渲染）或 asset 导演（重新生成）
       - 运动问题 → edit 导演（重新配时）或 scene 导演（重新规划）
       - 音频问题 → compose 导演
       - 时长问题 → script 导演（重写）
       - 数学错误 → script 导演（修内容）然后向下级联
```

## EP 专属的跨阶段检查

这些检查使用跨阶段累积的信息 —— 是任何单个导演都做不到的事。

### RESEARCH 阶段之后：
```
检查：调研深度
  - 至少 3 个带来源 URL 的 data_points？
  - 至少 3 个带 grounded_in 引用的 angles_discovered？
  - 至少 2 条动画技法参考？
  - 至少引用 5 个来源？
  - 若任一最低要求未达标：REVISE research
  - 注意：**不要**在此与用户设检查点 —— research 是信息性的，不是决策点
```

### PROPOSAL 阶段之后：
```
检查：审批门禁（关键）
  - approval.status 是 "approved" 还是 "approved_with_changes"？
  - 若是 "pending" 或 "rejected"：停下。呈现给用户并等待。
  - 若是 "approved_with_changes"：先应用修改再继续
  - 提取：animation_mode、reuse_strategy、target_duration、playbook、预算、工具选择

检查：动画方式的可行性
  - 选定动画方式所需的工具在注册表里存在吗？
  - 若选了 image_animation：image_selector 可用吗？有哪些 provider？Remotion 可用吗？
  - 若选了 clip_video：video_selector 可用吗？有哪些 provider？
  - 若选了 manim：math_animate（ManimCE）可用吗？
  - 若选了 remotion_dataviz：video_compose（Remotion）可用吗？
  - 若选了 diagram_stills：diagram_gen + image_selector 可用吗？
  - 若任何必需工具不可用：提醒用户，并给出带具体安装说明的替代方案
  - **绝不静默降级** —— 若某个方式需要用户没有的 key，停下并告诉他们

检查：复用策略的有效性
  - 复用策略是否定义了反复出现的母题？
  - 独特场景与模板的比例是否合理（目标 ≤ 3:1）？
```

### SCRIPT 阶段之后：
```
检查：词数 vs 时长目标
  - 计算：总词数 / 150 = 预计分钟数
  - 若 预计分钟数 > 目标时长 * 1.15：
      REVISE script："脚本 {X} 词 → {Y} 分钟。目标：{Z} 分钟。删掉 {N} 词。"
  - 若 预计分钟数 < 目标时长 * 0.7：
      REVISE script："脚本太短。加 {N} 词。"

检查：动画节拍结构
  - 每一段是否只表达**一个**清晰的视觉构想？
  - 是否为停留时长留了预算（不是每一秒都塞满新信息）？
  - 屏幕文字是否精炼（短语，不是段落）？

检查：数学准确性（若适用）
  - 脚本的解释是否与 research brief 的准确性备注一致？
  - 所做的简化在技术上站得住吗？
  - 若不准确：带上调研中的具体更正去 REVISE script
```

### SCENE_PLAN 阶段之后：
```
检查：场景总时长是否覆盖完整脚本
  - 把所有场景时长相加
  - 与脚本总时长比较
  - 若空缺 > 1 秒：REVISE scene_plan
  - 若有重叠：REVISE scene_plan

检查：动画模式的遵守
  - 每个场景是否都指明了它使用哪种动画模式/工具？
  - 模式选择是否与 proposal 中选定的模式一致？
  - 若是混合模式：模式之间的转场是否规划了？

检查：复用策略的执行
  - 场景方案是否引用了 proposal 中的反复出现母题？
  - 指定要复用模板的地方是否复用了？
  - 若每个场景都是独一无二的：标记为潜在的过度复杂

检查：约束内的视觉多样性
  - 统计连续同类型场景数
  - 若连续 > 3 个：REVISE scene_plan
```

### ASSETS 阶段之后：
```
检查：旁白时长反馈回路（关键）
  - 对每个 TTS 音频文件，探测实际时长
  - 存入 EP_STATE.narration_durations
  - 对每一段：
      若 实际时长 > 计划时长 * 1.15：
        选项 A：SEND_BACK 给 script 导演
        选项 B（超出 25% 以内）：调整 scene_plan 时长
  - 更新 EP_STATE.total_narration_seconds

检查：预算门禁
  - 若 budget_spent > budget_total * 0.9 且还有阶段未跑：
      提醒："已消耗 90% 预算，还剩 {N} 个阶段"
      把剩余阶段改用免费/廉价的替代方案

检查：风格一致性
  - 比较所有生成素材的视觉风格
  - 反复出现的母题在视觉上一致吗？
  - 存下 style_anchors 供下游使用

检查：程序化素材完整性（若用了 Manim/Remotion）
  - math_animate 或 video_compose 是否无错误地成功了？
  - 输出文件是否合法、尺寸正确？
```

### EDIT 阶段之后：
```
检查：时间线完整性
  - 确认剪辑决策覆盖从 0 到 total_duration 且无空缺
  - 确认所有素材引用都指向真实存在的文件
  - 确认所有旁白段都配置了音频闪避

检查：停留时长的保持（动画专属）
  - 确认 scene_plan 中的停留时长在剪辑决策中被保留
  - 确认错峰揭示没有被压缩
  - 确认运动服务于层级，而不是装饰

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

检查：文字与图表锐利度（动画关键项）
  - 文字必须在目标分辨率下可读
  - 图表线条必须锐利（无缩放伪影）
  - 数学符号必须渲染正确
  - 若有任何文字/图表发糊：带上分辨率/缩放调整去 REVISE compose
```

## 反馈消息模板

### 给 Script 导演：
```
EP 反馈 —— 需要修订脚本
原因：{reason}
具体问题：{detail}
约束：{词数上限 / 时长目标 / 数学准确性}
动画模式：{当前模式 —— 影响文字与节拍该如何组织}
保留：{哪些做得好}
修改：{具体要改什么}
```

### 给 Scene 导演：
```
EP 反馈 —— 需要修订场景方案
原因：{reason}
受影响场景：{scene_ids}
动画模式：{当前模式}
复用策略：{应当复用哪些母题/模板}
可用工具：{当前工具注册表状态}
```

### 给 Asset 导演：
```
EP 反馈 —— 需要重新生成素材
原因：{reason}
受影响素材：{asset_ids}
风格锚点：{一致性要求}
动画模式：{当前模式 —— 影响该用哪些工具}
剩余预算：${remaining}
```

### 给 Compose 导演：
```
EP 反馈 —— 需要重新渲染
原因：{reason}
具体问题：{文字锐利度 / 运动时序 / 音画同步 / 等等}
期望：{输出应当是什么样}
实际：{实际产出了什么}
```

## 质量门汇总

| 门 | 位于阶段之后 | 检查什么 | 未通过时的动作 |
|------|-------------|---------------|-------------|
| G1 | research | 数据深度、技法参考、角度多样性 | 修订 research |
| G2 | proposal | 概念质量、模式可行性、用户审批 | 修订 proposal 或等待用户 |
| G3 | script | 词数、节拍结构、数学准确性 | 修订 script |
| G4 | scene_plan | 覆盖度、模式遵守、复用策略、多样性 | 修订 scene_plan |
| G5 | assets | 旁白时长、预算、风格、素材完整性 | 修订 assets 或回退到 script |
| G6 | edit | 时间线完整性、停留时长、音画预同步 | 修订 edit |
| G7 | compose | 输出探测、文字锐利度、运动时序 | 修订 compose 或回退 |
| G8 | publish | 元数据、打包、动画模式标签 | 修订 publish |
| FINAL | 全部 | 整体复看：锐利度、运动、准确性、风格 | 回退到具体阶段 |

## 执行上限（防循环保护）

| 上限 | 取值 | 理由 |
|-------|-------|-----------|
| 每阶段最多修订次数 | 3 | 防止完美主义循环 |
| 每对阶段最多回退次数 | 1 | 防止来回踢皮球 |
| 总回退次数上限 | 3 | 给返工总量封顶 |
| 总预算上限 | 可配置（默认 $2） | 花费的硬性刹车 |
| 总墙钟时间上限 | 15 分钟 | 整条管线的超时 |

任何上限被触发后：**带警告继续**，绝不无限期阻塞。

## 与既有技能的集成

EP 不取代任何 director 技能 —— 它把它们包起来。每个 director 技能继续按其文档所述工作。EP 额外提供：

1. **上下文注入**：导演收到带跨阶段信息的 EP_STATE
2. **反馈注入**：被打回时，导演收到具体的修订指令
3. **预算感知**：导演收到剩余预算并据此调整工具选择
4. **动画模式上下文**：导演知道选定的模式和复用策略
5. **风格锚点**：导演收到来自先前阶段的一致性 token
6. **数学准确性备注**：导演收到技术准确性方面的约束

## 常见陷阱

- **过度修订**：一支模式正确的"够好"的动画，胜过 5 轮之后的"完美"作品。
- **忽视文字锐利度**：动画质量的头号问题。始终在最终分辨率下验证文字可读性。
- **让复用策略被侵蚀**：若 proposal 指定了 3 个模板，场景方案就该用 3 个模板，而不是 8 个独特设计。
- **不探测输出**：始终对最终视频跑 ffprobe。绝不要只信元数据。
- **丢失动画模式上下文**：若 proposal 选了 Manim，每个下游阶段都该知道这是个 Manim 项目。不要在已经批准程序化动画的情况下，让某个阶段默认退回到通用的 image_selector。
- **跳过数学准确性检查**：对技术题材，这一条不可妥协。一个错误的动画比没有动画更糟。
