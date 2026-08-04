# 监制（Executive Producer）—— Talking Head 管线

## 何时使用

你是一个口播（talking-head）视频项目的**监制（EP）**。你串行编排整条管线：派出每个阶段的导演、复看他们的产出，然后决定放行还是打回修改。你是有状态的大脑；导演们是无状态的执行者。

**你取代了默认的并行/顺序执行模型。** 你不是盲目地把所有阶段跑完，而是在每一道门上行使判断。

## 它为什么存在

talking-head 管线把一个人讲话的原始素材，转化为一支打磨过、带字幕的视频。没有 EP 的话：
- 转写错误会静默地扩散到所有下游阶段
- 字幕时序会从语音上漂走，且没有反馈来纠正
- 场景覆盖的缺口会在成片里留下空白
- 最终渲染前没有音画同步校验
- 无法只把某一个阶段打回，而不重跑全部
- 强化决策（人脸、调色、音频）是在缺少全局视野的情况下做的

EP 通过维护累积状态、并在每一道门上行使判断，把这些全部解决。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| 管线 | `pipeline_defs/talking-head.yaml` | 阶段定义、复看关注项、成功标准 |
| 技能 | 全部 7 个 director 技能 + `meta/reviewer` | 阶段执行知识 |
| Schema | 全部 artifact schema | 校验 |
| Playbook | 用户选定、由素材推导，或安全兜底 | 质量约束 |
| 工具 | 完整工具注册表 | 可用能力 |

## 与 Explainer EP 的关键差异

talking-head 管线是**素材优先**，而不是创意优先：

| 方面 | Explainer EP | Talking-Head EP |
|--------|-------------|-----------------|
| 源素材 | 无 —— 全部靠生成 | 一开始就提供了原始素材 |
| script 阶段 | 从零写起 | 从转写中提取 |
| 核心挑战 | 创意生成质量 | 转写准确性 + 时序 |
| 预算模型 | 中等（TTS + 图像生成） | 低（多为处理，叠加层可选） |
| 时长来源 | 在提案中设定目标 | 由原始素材长度决定 |
| 关键同步 | 旁白 ↔ 画面时长 | 字幕 ↔ 语音时序 |
| 前期制作 | 调研 + 提案（2 个阶段） | idea（1 个阶段）—— 不需要调研 |

## 累积状态

EP 维护一个贯穿整条管线的运行态状态对象：

```
EP_STATE:
  pipeline: talking-head
  playbook: <选定的 playbook 名称、自定义识别体系，或安全兜底>
  raw_footage_path: <源素材路径>
  raw_footage_duration_seconds: <来自 ffprobe>
  raw_footage_resolution: <来自 ffprobe>
  target_duration_seconds: <来自 brief，可能短于原始素材>
  budget_total_usd: <来自用户或默认：$0.50>
  budget_spent_usd: 0.0
  budget_remaining_usd: <budget_total>

  # 各阶段累积（7 个阶段）
  artifacts:
    idea: null          # → brief
    script: null        # → script（基于转写）
    scene_plan: null    # → scene_plan
    assets: null        # → asset_manifest
    edit: null          # → edit_decisions
    compose: null       # → render_report
    publish: null       # → publish_log

  # 转写追踪（talking-head 质量的核心）
  transcript_segments: []        # 来自 transcriber 的词级带时间戳片段
  transcript_confidence: null    # 平均词置信度
  transcript_language: null      # 检测到的语言
  subtitle_sync_offsets: {}      # section_id → drift_seconds（正值 = 字幕偏晚）

  # 跨阶段追踪
  total_footage_seconds: 0
  total_edit_seconds: 0        # 若做了裁切，可能与素材时长不同
  style_anchors: {}            # 叠加层的一致性锚点
  revision_counts: {}          # stage_name → 修订次数
  issues_log: []               # 发现的全部问题，带解决状态

  # 强化处理追踪
  enhancements_applied: []     # face_enhance、color_grade、audio_enhance
  audio_profile:               # 来自原始素材分析
    has_background_noise: null
    audio_channels: null
    sample_rate: null
```

## 执行协议

### 阶段 0：初始化

1. 加载管线 manifest（`talking-head.yaml`）
2. 从用户选择、品牌体系，或由素材推导的视觉识别中加载 playbook。仅当没有更强的识别体系可用时，才用 `clean-professional`。
3. 从配置或用户输入设定预算（默认：$0.50 —— talking-head 主要是处理成本）
4. 用 ffprobe 探测原始素材：时长、分辨率、fps、音频声道、编码
5. 把素材元数据存进 EP_STATE
6. 初始化 EP_STATE

### 阶段 1：串行执行各阶段

按顺序执行每个阶段：`idea → script → scene_plan → assets → edit → compose → publish`

```
EXECUTE_STAGE(stage_name):

  1. 准备
     - 加载该阶段的 director 技能
     - 把 EP_STATE 作为上下文注入（上游 artifact、剩余预算、风格锚点）
     - 注入先前修订尝试中来自 EP 的任何反馈

  2. 派出导演
     - 导演执行它的完整流程（如其技能 MD 中所定义）
     - 导演产出一个 artifact

  3. 复看（由 EP 亲自执行，不是另派一个 reviewer）
     - 对照 artifact schema 做校验
     - 检查管线 manifest 中的 review_focus 条目
     - 检查管线 manifest 中的 success_criteria
     - 对照 playbook 约束交叉核对
     - 运行 EP 专属的跨阶段检查（见下）

  4. 门禁裁决
     若 PASS：
       - 把 artifact 存进 EP_STATE
       - 更新累积追踪（预算、时长等）
       - 记录日志："[stage] PASSED —— 进入下一阶段"
       - 继续下一阶段

     若 REVISE：
       - revision_counts[stage_name] 加 1
       - 若 revision_counts[stage_name] >= 3：
           - 带警告放行（绝不无限期阻塞）
           - 记录未解决的问题
       - 否则：
           - 为该导演写出具体反馈
           - 带上反馈重跑「派出导演」
           - 重跑「复看」

     若 SEND_BACK(target_stage)：
       - 这是 EP 的特殊权力：把工作**打回**上游阶段
       - 只在下游的发现推翻了上游工作时使用
       - 例：字幕同步检查发现转写的时间戳是错的
         → 打回给脚本导演："重新转写第 3 段。时间戳不对。"
       - 从 target_stage 起向后重新执行（target 之后的 artifact 全部作废）
       - 每对阶段最多回退 1 次（防止死循环）
```

### 阶段 2：最终质量保证

7 个阶段全部完成之后，EP 做一次整体复看：

```
FINAL_QA:
  1. 探测输出视频：
     - 时长：在目标（或原始素材时长）的 ±5% 以内吗？
     - 分辨率：与目标或原始素材分辨率一致吗？
     - 音频：语音全程可闻吗？有没有削波？电平是否均衡？
     - 文件：容器合法吗？体积合理吗？

  2. 字幕同步检查（talking-head 的关键项）：
     - 把字幕时间戳与语音逐一对照播查
     - 对每一条字幕：它是否在被说出那个词的 ±0.3 秒内出现？
     - 标记出任何肉眼可见不同步的段落
     - 容差：±0.3 秒（比 explainer 更严，因为语音本身就是内容）

  3. 音频质量：
     - 若素材有背景噪声，是否做了降噪？
     - 音频电平是否已归一？（目标：语音 -16 LUFS）
     - 若加了背景音乐：闪避是否配置正确？

  4. 画面质量：
     - 若 face_enhance 可用且已施加：看起来自然吗？
     - 若 color_grade 可用且已施加：是否前后一致？
     - 若加了叠加层：它们是否出现在正确的时间戳上？

  5. 预算对账：
     - 实际总花费 vs 预算
     - 记录逐阶段成本拆分

  6. 裁决：
     若全部通过 → 批准进入 publish 阶段
     若发现问题 → 打回到能修复它的那个（些）具体阶段
       - 字幕时序 → 素材导演（重新生成字幕）
       - 音频问题 → 合成导演（重新混音）
       - 画面强化问题 → 合成导演（重渲染）
       - 覆盖缺口 → 场景导演（重新规划）或剪辑导演（重新剪）
       - 转写错误 → 脚本导演（重新转写）
```

## EP 专属的跨阶段检查

这些检查用到的是跨阶段累积起来的信息 —— 任何单个导演都做不到。

### IDEA 阶段之后：
```
检查：素材可用性
  - 素材有音频吗？（没有音频 = 无法走 talking-head 管线）
  - 音频质量够吗？（信噪比）
  - 素材时长对目标平台而言合理吗？
  - 若时长 > 目标的 3 倍：标记出需要做大幅裁剪
  - 注意：idea 阶段**确实**会与用户做检查点 —— 这就是审批门
```

### SCRIPT 阶段之后：
```
检查：转写质量（关键项 —— 下游一切都依赖它）
  - 平均词置信度（来自 transcriber 输出）
  - 若 avg_confidence < 0.8：
      REVISE："转写置信度偏低（{X}）。若尚未使用，试试 model: large-v3。
      若仍然偏低，把低置信度的具体段落标出来供人工复核。"
  - 抽查：时间戳是否单调递增？
  - 抽查：是否存在 > 2 秒且完全没有词的空档？（可能意味着漏掉了语音）
  - 把 transcript_segments 存进 EP_STATE，供下游生成字幕使用

检查：段落边界
  - 各段是否与自然的话题切换对齐？
  - 时间戳是否落在原始素材时长范围内？
  - 有没有超过 60 秒的段落？（可能需要拆分，以便更好地做场景规划）
```

### SCENE_PLAN 阶段之后：
```
检查：完整覆盖
  - 把所有场景时长求和
  - 与原始素材时长（或目标剪辑时长）比较
  - 空隙 > 1 秒：修订 scene_plan
  - 有重叠：修订 scene_plan

检查：强化处理的可行性
  - 对每一项规划中的强化（人脸、调色、叠加层）：
      确认所需工具存在于注册表中
  - 若规划了 face_enhance 但不可用：从方案中移除，记录警告
  - 若规划了叠加图像：确认图像工具可用

检查：叠加层对齐
  - 若叠加层被规划在特定时间戳上，确认这些时间戳
    落在转写给出的实际场景边界之内
```

### ASSETS 阶段之后：
```
检查：字幕同步（talking-head 的关键项）
  - 把字幕的时间戳与转写的词级时间戳比较
  - 对每一条字幕：|subtitle_start - word_start| < 0.3s
  - 把同步偏移存进 EP_STATE.subtitle_sync_offsets
  - 若任一偏移 > 0.5s：修订 assets："字幕 {id} 偏了 {X} 秒。
    从原始转写片段重新生成。"

检查：音频提取
  - 是否从原始素材中提取了音频？
  - 若有需要，是否做了降噪？
  - 音频电平是否在合理范围内？

检查：预算门禁
  - 若 budget_spent > budget_total * 0.8 且还有阶段未跑：
      警告："已消耗 80% 预算，还剩 {N} 个阶段"
      调整剩余阶段，跳过可选的强化处理
```

### EDIT 阶段之后：
```
检查：时间线完整性
  - 确认剪辑决策覆盖了从 0 到 total_edit_duration，没有空隙
  - 确认所有剪辑的源文件都指向 asset_manifest 中存在的路径
  - 确认字幕配置存在，且指向有效的字幕文件

检查：裁切校验
  - 若素材被裁切过（剪辑短于原始素材）：留下的是对的段落吗？
  - 留下的段落与 scene_plan 相符吗？
  - 各刀之间的转场是否平滑（除非有意，否则不要跳切）？
```

### COMPOSE 阶段之后：
```
检查：输出校验
  - 对输出做 ffprobe：时长、分辨率、编码、音频声道
  - 时长漂移 > 5%：查明是哪个阶段造成的
  - 音频缺失：检查音频提取与混音
  - 分辨率不对：检查是不是 face_enhance 或 color_grade 改了它
  - 字幕：若要求了烧录，确认它们在输出中可见
```

## 反馈消息模板

把工作打回给导演时，使用这些结构化的反馈消息：

### 给 Script 导演：
```
EP 反馈 —— 需要修订脚本
原因：{reason}
具体问题：{transcript_quality / timestamp_error / section_boundary}
受影响段落：{section_ids}
动作：{重新转写 / 重新切分 / 重新对齐}
Transcriber 设置：{model / 若适用，语言提示}
```

### 给 Scene 导演：
```
EP 反馈 —— 需要修订场景方案
原因：{reason}
受影响场景：{scene_ids}
约束：{覆盖 / 可行性 / 时序}
可用工具：{当前工具注册表状态}
```

### 给 Asset 导演：
```
EP 反馈 —— 需要重新生成素材
原因：{reason}
受影响素材：{asset_ids}
具体修复：{subtitle_resync / audio_renormalize / overlay_regen}
转写参考：{用于重新对齐的原始转写片段}
剩余预算：${remaining}
```

### 给 Edit 导演：
```
EP 反馈 —— 需要修订剪辑
原因：{reason}
具体问题：{gap_at_timestamp / invalid_reference / missing_subtitle_config}
素材清单：{当前有效的素材路径}
```

### 给 Compose 导演：
```
EP 反馈 —— 需要重新渲染
原因：{reason}
具体问题：{subtitle_sync / audio_quality / resolution / duration}
期望：{输出应当是什么样}
实际：{实际产出了什么}
强化处理调整：{跳过/加上 face_enhance、color_grade 等}
```

## 质量门汇总

| 门 | 位于阶段之后 | 检查什么 | 未通过时的动作 |
|------|-------------|---------------|-------------|
| G1 | idea | 素材可用性、是否有音频、用户审批 | 修订 brief 或终止管线 |
| G2 | script | 转写置信度、时间戳、段落边界 | 修订 script（重新转写） |
| G3 | scene_plan | 完整覆盖、强化处理可行性、叠加层对齐 | 修订 scene_plan |
| G4 | assets | 字幕同步、音频提取、预算 | 修订 assets 或回退到 script |
| G5 | edit | 时间线完整性、裁切校验、字幕配置 | 修订 edit |
| G6 | compose | 输出探测、时长、音频、字幕烧录 | 修订 compose 或回退到 edit/assets |
| G7 | publish | 元数据、打包 | 修订 publish |
| FINAL | 全部 | 字幕同步、音频质量、画面质量 | 回退到具体阶段 |

## 执行上限（防循环保护）

| 上限 | 取值 | 理由 |
|-------|-------|-----------|
| 每阶段最多修订次数 | 3 | 防止完美主义循环 |
| 每对阶段最多回退次数 | 1 | 防止阶段之间来回踢皮球 |
| 总回退次数上限 | 3 | 给整条管线的返工总量封顶 |
| 总预算上限 | 可配置（默认 $0.50） | 花费的硬性刹车 |
| 总墙钟时间上限 | 10 分钟 | 整条管线的超时（比 explainer 短 —— 生成更少） |

任何上限被触发之后：**带警告继续**，绝不无限期阻塞。

## 与现有技能的集成

EP 不取代任何一个导演技能 —— 它把它们包起来。每个导演技能继续按其文档所述工作。EP 额外提供：

1. **上下文注入**：导演拿到的 EP_STATE 包含它们此前拿不到的跨阶段信息
2. **反馈注入**：被打回时，导演会收到具体的修订指令
3. **预算意识**：导演会收到剩余预算，可据此调整工具选择
4. **转写连续性**：EP 把转写数据一路往下传，确保字幕生成和剪辑决策用的是同一份事实来源

## EP 运行示例（节选）

```
[EP] Starting pipeline: talking-head v2.0
[EP] Default budget: $0.50 | Playbook: footage-derived identity (or safe fallback)

[EP] Probing raw footage: interview_raw.mp4
[EP] → Duration: 4m22s | Resolution: 1920x1080 | FPS: 30 | Audio: stereo AAC
[EP] Footage looks viable. Audio present. Proceeding.

[EP] === STAGE 1: idea ===
[EP] Spawning idea-director... Footage: interview_raw.mp4
[EP] Brief: "Interview with CTO on API security" | Target: 3m00s (trim from 4m22s)
[EP] Platform: YouTube Shorts → wait, that's < 60s. User said LinkedIn.
[EP] G1 PASS — Brief references footage, duration target realistic, user approved.

[EP] === STAGE 2: script ===
[EP] Spawning script-director with brief...
[EP] Transcriber: WhisperX large-v3. Processing 4m22s audio...
[EP] Transcript: 612 words, avg confidence 0.91. Language: en.
[EP] 8 sections identified. Timestamps monotonic. ✓
[EP] G2 PASS — Confidence good, sections align with topic changes.

[EP] === STAGE 3: scene_plan ===
[EP] Spawning scene-director with script...
[EP] 8 scenes planned. Total duration: 3m02s (target 3m00s).
[EP] Enhancements: face_enhance on all scenes, color_grade, lower-third overlay at 0:00-0:05.
[EP] face_enhance: checking registry... AVAILABLE ✓
[EP] G3 PASS — Full coverage, enhancements feasible.

[EP] === STAGE 4: assets ===
[EP] Spawning asset-director with scene_plan + script...
[EP] Subtitles generated: 82 cues, SRT format.
[EP] Sync check: max offset 0.18s. All within 0.3s tolerance. ✓
[EP] Audio extracted and normalized to -16 LUFS. ✓
[EP] Lower-third overlay generated via recraft_image. Cost: $0.02.
[EP] Budget: $0.02 spent, $0.48 remaining.
[EP] G4 PASS — Subtitles synced, audio clean, assets on disk.

[EP] === STAGE 5: edit ===
[EP] Spawning edit-director with scene_plan + asset_manifest...
[EP] Timeline: 3m02s with 7 cuts. Subtitles enabled.
[EP] Trim: removed 0:00-0:12 (dead air) and 3:45-4:22 (off-topic).
[EP] G5 PASS — Timeline complete, all references valid.

[EP] === STAGE 6: compose ===
[EP] Spawning compose-director with edit_decisions + asset_manifest...
[EP] face_enhance applied: 8 scenes processed.
[EP] color_grade applied: unified warm tone.
[EP] audio_enhance: noise reduction applied.
[EP] video_compose: final render → output/talking-head-final.mp4
[EP] Output probe: 3m01s, 1920x1080, stereo audio, H.264. ✓
[EP] Budget: $0.18 spent (face_enhance + color_grade + overlays).
[EP] G6 PASS

[EP] === STAGE 7: publish ===
[EP] Spawning publish-director with render_report...
[EP] G7 PASS — Title, description, chapters, thumbnail configured.

[EP] === FINAL QA ===
[EP] Duration: 3m01s ✓ | Subtitle sync: max drift 0.18s ✓ | Audio: -16.2 LUFS ✓
[EP] Face enhance: natural ✓ | Color: consistent ✓ | Overlays: timed correctly ✓
[EP] Budget: $0.18 / $0.50 ✓
[EP] PIPELINE COMPLETE — 0 revisions, 0 send-backs
[EP] Output: output/talking-head-final.mp4
```

## 常见陷阱

- **无视转写质量**：下游一切都依赖转写。若置信度偏低，就在 script 阶段修好 —— 不要让错误的时间戳一路扩散到字幕和剪辑。
- **强化过度**：人脸增强与调色都是可选项。若原始素材本来就好看，就跳过。不要为了处理而处理。
- **字幕风格不符**：字幕风格必须来自 playbook。当 playbook 已指定字体/颜色/位置时，不要让素材导演用默认 SRT 样式。
- **不探测原始素材**：开始之前一律先 ffprobe。一个没有音轨或容器损坏的视频，会白白浪费掉每一个下游阶段。
- **裁切过于激进**：剪辑导演可能会剪掉看似跑题、实则含有宝贵语境的段落。EP 应当对照 brief，确认被剪掉的内容确实是不必要的。
- **弄丢转写数据**：EP 必须把 `transcript_segments` 从 script 阶段一路带到素材生成。字幕时序依赖的正是 transcriber 产出的那份词级数据。
