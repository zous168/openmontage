# Reviewer —— 元技能

## 何时使用

在完成任何管线阶段的工作之后 —— 写检查点之前。你是"工作做完"与"工作被接受"之间的质量门。本技能用一套指令驱动的自评协议取代了 Python 的 reviewer 类。

每个阶段都要复看。没有例外。复看质量决定了最终视频值不值得看。

## 评论质量（CHAI 规则）

> 发现 ≠ 评论。发现指出一个问题；评论告诉下一个阶段该怎么修。CMU/Harvard 的 CHAI 研究（《Building a Precise Video Language with Human-AI Oversight》，arXiv 2604.21718v2）表明，从三个维度衡量的评论质量，直接决定了下游产出的质量。每一轮 reviewer 都要把这三条都用上。
>
> **准确。** 每条发现都必须引用一个具体的 artifact 字段、行号或可见的素材画面。禁止凭空捏造的批评 —— 如果你说不出问题在哪，那就是在猜。
>
> **完整。** 一轮抓到一个错误却漏掉第二个的复看，还不如评为"需要再来一轮"然后继续。若你找到一个关键问题，在返回之前先把同一类的其余问题都扫一遍。做模式匹配：这个 artifact 里还有哪里可能藏着同样的错误？
>
> **建设性。** 每条 "critical" 发现**必须**给出具体的修法，而不只是指出问题。"字幕写错了" → "字幕写的是 'man on the right'；而画面里那个人在左边。替换成 'the man on the left of the frame.'" 若你提不出修法，就把这条发现标为 "investigation" 而不是 "critical"。
>
> 去掉这三条性质中的任何一条，都会实测地损害管线产出。reviewer 是咽喉要道 —— 要严格。

## 协议

### 第 1 步：加载复看上下文

复看之前，收集：
1. 管线 manifest 中该阶段的**复看关注项**（`review_focus` 字段）
2. manifest 中该阶段的**成功标准**（`success_criteria` 字段）
3. **当前生效的 playbook** 的质量规则
4. 该阶段产出的 **artifact**

### 第 2 步：Schema 校验

第一件、不可妥协的检查：
- 按 JSON schema（`schemas/artifacts/<name>.schema.json`）校验该 artifact
- 若 schema 校验失败，这是一条 **critical** 发现 —— 立即修复，不要继续往下走

### 第 3 步：对照关注项复看

对 manifest 中的每一条 `review_focus`：
1. 按这条具体标准评估该 artifact
2. 判定严重级别：
   - **critical** —— 必须修好才能继续。artifact 是坏的、不完整的，或危险地错误。**按 CHAI 规则，每条 critical 发现都必须带一个 `proposed_fix`（具体的替换文本、确切的字段值，或明确的纠正动作）。没有 proposed_fix 的 critical 发现会被降级为 `investigation`。**
   - **suggestion** —— 应该修。能显著提升质量，但不阻塞推进。**建议必须带一个 `proposed_change`，说明如何改进。**
   - **nitpick** —— 可以修。锦上添花的小打磨。可以不带修改建议单独存在。
   - **investigation** —— 确实是个隐忧，但你无法定位修法。把它抛出来留待下一轮；不要因它阻塞。
3. 写下具体、可执行的发现（不要含糊）

**好的发现：** "第 3 段旁白在一个 10 秒窗口里有 180 个词 —— 那是每分钟 1080 词，根本说不出来。删到 25 个词。"
**差的发现：** "脚本可能有点长。"

### 第 4 步：对照 playbook 交叉核对

若有生效的风格 playbook，逐项确认：
- [ ] 颜色引用与 playbook 配色一致
- [ ] 转场类型在 playbook 允许的集合内
- [ ] 节奏规则被遵守（最短/最长时长）
- [ ] 素材描述中包含 playbook 的风格提示
- [ ] 质量规则未被违反

每一处违反都是一条 **suggestion** 级发现。

### 第 4b 步：审美方向复看

若存在 `proposal_packet.production_plan.taste_profile` 或当前 playbook 的 `taste_profile`，逐项确认：
- [ ] `design_read` 解释了 brief、受众和交付承诺；它不只是"现代/干净/专业"
- [ ] `visual_variance`、`motion_intensity` 和 `information_density` 在场景版式、节奏、标注密度和素材提示词中有所体现
- [ ] 当 atelier 工作、AI 图像/视频、产品/品牌视觉或情绪板依赖视觉细腻度时，`reference_strategy` 存在
- [ ] 列出的 `anti_patterns` 确实被避免了
- [ ] 质量门具体到下一阶段能够执行

在 proposal 阶段，缺少 `taste_profile` 对于预设/低风险工作是 **suggestion**，对于 atelier、产品/品牌、发布、旗舰或自定义 playbook 工作是 **critical** 发现。在 scene_plan/edit/compose 阶段，把旋钮违规视为 **suggestion**，除非它破坏了已获批的交付承诺。

### 第 5 步：评估成功标准

对 manifest 中的每一条 `success_criteria`：
- 该标准是否达成？（是/否/部分）
- 若未达成，创建一条 **critical** 发现

### 第 6 步：做出裁决

按严重级别统计发现数：

| 情形 | 措施 |
|----------|--------|
| 0 条 critical，有任意数量的 suggestion/nitpick | **通过** —— 进入写检查点。把建议记录在案。 |
| 1 条及以上 critical 发现 | **修订** —— 修完所有 critical 发现，然后重新复看（最多 2 轮）。 |
| 2 轮修订之后仍有 critical | **带警告通过** —— 照常推进，但把未解决的问题记下来。绝不要无限期阻塞。 |

### 第 7 步：记录复看

把你的复看整理成：

```
## Review: [stage_name] — Round [N]

**Decision:** PASS / REVISE / PASS_WITH_WARNINGS

### Findings

1. [CRITICAL] 发现的标题
   - Description: 哪里错了
   - Action: 要修什么
   - Status: pending / fixed / accepted / deferred

2. [SUGGESTION] 发现的标题
   - Description: 哪里可以更好
   - Action: 如何改进
   - Status: pending / accepted / deferred

### Summary
- Critical: N（已修 N）
- Suggestions: N
- Nitpicks: N
- Playbook 违规: N
- 成功标准达成: N/M
```

## 关键原则

1. **要具体，不要含糊。** "钩子很弱"毫无用处。"钩子提了个问题但没有制造紧迫感 —— 试试用 key_point #2 里那个令人意外的数据开场"才是可执行的。

2. **critical 就意味着关键。** 不要虚抬严重级别。缺少一个 schema 字段是 critical。某段稍显啰嗦是 suggestion。一个逗号连句是 nitpick。

3. **最多两轮。** 目标是交付，不是完美。两轮修订之后，带警告通过并往前走。完美主义会杀死管线。

4. **复看 artifact，不复看过程。** 你检查的是产出，不是它是怎么被做出来的。若 brief 很有说服力，agent 用了不寻常的方法也无所谓。

5. **playbook 就是法律。** 若 playbook 说"屏幕上不超过 3 种颜色"，那不是建议 —— 那是约束。违反必须标出。

## 各阶段的复看重点

| 阶段 | 最要紧的是什么 |
|-------|-----------------|
| research | 来源多样性、论断可核实性、视觉参考质量 |
| proposal | 交付承诺是否清晰、renderer family **和** render runtime 的选择、音乐/配音计划、decision log 是否已开始 |
| idea | 钩子的独特性、调研深度、切入角度的多样性 |
| script | 时序准确性、叙事弧线、增强提示密度 |
| scene_plan | 覆盖是否完整、视觉多样性、素材可行性、幻灯片化风险分 |
| assets | 文件是否存在、风格一致性、预算遵守、UGC 视频提示词合规（存在 brief 时） |
| edit | 时间线覆盖、音画同步、字幕是否存在、交付承诺合规 |
| compose | 可播放性、时长准确性、音频质量、compose 前校验是否通过 |
| publish | SEO 质量、元数据完整性、导出打包 |

## 参考对齐复看

当存在 VideoAnalysisBrief（reference-driven 生产）时，在**每个阶段**运行。

### 检查项：

1. **落地检查：** 产出是否引用了 VideoAnalysisBrief 中的具体发现，
   还是在编造关于参考视频的东西？
   - proposal 说"节奏很快"但参考的 pacing_style 是 "slow_contemplative" → **CRITICAL**
   - 脚本声称参考视频有旁白，但 VideoAnalysisBrief 显示没有旁白 → **CRITICAL**

2. **差异化检查：** 每个概念/场景是否与参考有清晰的创意
   差异，还是照抄？
   - proposal 是参考的翻版（同一主题、同一结构、同一处理方式）→ **CRITICAL**
   - 每个概念**必须**至少有一个元素与参考不同 → 若差异微弱则为 **SUGGESTION**
   - brief 中的创意差异化种子应当在 proposal 中有所体现

3. **承诺保持：** 用户说他们喜欢参考视频的那些元素，在产出中是否
   仍然存在？
   - 用户说"我喜欢它的节奏"，但 scene_plan 里的场景长了一倍 → **SUGGESTION**
   - 用户说"保留那种钩子风格"，但脚本用了另一种钩子 → **SUGGESTION**

4. **成本对齐：** 成本估算是否仍然准确，还是范围膨胀了？
   - 若实际花费超出估算 30% 以上且未经用户重新批准 → **CRITICAL**
   - 若在已获批 proposal 之外新增了素材 → **SUGGESTION**

5. **UGC 视频提示词合规（仅 assets 阶段）：** 当存在 VideoAnalysisBrief 时，对来自
   `video_selector` 的每个视频素材：
   - `assets[].prompt` 必须存在，且符合
     `skills/pipelines/explainer/asset-director.md` 中的六段式 UGC 规格
   - 必须包含 `real-time physics` 和 `constant speed`；必须包含 `[MM:SS` 形式的定时节拍
   - 不得包含 "same as above" / 简写式继承
   - `generation_summary` 应注明 `prompt_profile: ugc_native`
   - 提示词缺失或不合规 → **CRITICAL**（用校验过的提示词重跑 assets）

### 严重级别：
- 关于参考视频的事实性错误：**CRITICAL**
- 毫无差异化的照抄：**CRITICAL**
- 差异化薄弱（只有表层改动）：**SUGGESTION**
- 用户偏好未被尊重：**SUGGESTION**
- 成本漂移超过 30%：**CRITICAL**

## 幻灯片化风险复看

在 **scene_plan** 和 **edit** 阶段运行。用 `lib/slideshow_risk.py` 计算分数。

### 在 scene_plan 阶段：
1. 计算 `score_slideshow_risk(scenes, renderer_family=renderer_family)`
2. 若判定为 **"fail"**（平均 ≥ 4.0）：**CRITICAL** —— 场景方案必须先修订才能继续
3. 若判定为 **"revise"**（平均 ≥ 3.0）：**SUGGESTION** —— 标出得分 ≥ 3.5 的具体维度
4. 若判定为 **"strong"** 或 **"acceptable"**：在复看摘要里记一笔，无需生成发现

### 在 edit 阶段：
1. 用完整的 edit_decisions 重新计算：`score_slideshow_risk(scenes, edit_decisions, renderer_family)`
2. 阈值同上 —— 若 edit 阶段把情况变得更糟（分数高于 scene_plan），要标出来

### 各维度该说什么：
| 维度 | 分数 ≥ 3.0 时怎么说 |
|-----------|------------------------------|
| repetition | "有 X 个场景用了同样的版式/景别 —— 让视觉语法变化起来" |
| decorative_visuals | "有 X 个场景没有说明目的（没有 information_role 或 shot_intent）" |
| weak_motion | "存在镜头运动，但缺少叙事上的正当理由" |
| weak_shot_intent | "有 X 个场景缺少 shot_intent —— 这个画面为什么存在？" |
| typography_overreliance | "X% 的场景是文字/数据卡 —— 视频像会动的幻灯片" |
| unsupported_cinematic_claims | "声称电影感，却缺少主镜头时刻 / 光照 / 运动" |

## Decision Log 复看

在 proposal 之后的**每个阶段**运行。decision log（`schemas/artifacts/decision_log.schema.json`）是一条累积的审计轨迹。

### 检查项：
1. **是否存在**：检查点是否引用了 `decision_log_ref`？若 proposal 阶段之后仍没有，标为 **SUGGESTION**。
2. **覆盖度**：每一个重要选择是否都有条目？**必须**记录的关键决策：
   - Provider 选择（选了哪个图像/视频/音频工具，为什么）
   - 风格/playbook 选择
   - 音乐曲目选择
   - 配音选择
   - Renderer family 选择
   - 任何兜底或降级（例如 运动 → 静图）
3. **质量**：每条决策应当有：
   - 至少 2 个 `options_considered`（不只是被选中的那个）
   - 一个不是套话的 `reason`（"最好的选项"不算理由）
   - 正确的 `confidence`（0.0–1.0）—— 若全都是 1.0 就标出来（不现实）
4. **用户可见性**：标为 `user_visible: true` 的决策，应当是用户真的会在意的那些（不是内部路由）

### 严重级别：
- proposal 之后缺少 decision log：**SUGGESTION**（第一次）、**CRITICAL**（若到 edit 阶段仍然缺失）
- 只考虑了 1 个选项的决策：**SUGGESTION** —— "把被否决的备选也记下来，以便审计"
- 所有决策的 confidence 都是 1.0：**SUGGESTION** —— "置信度不现实 —— 至少 provider 选择是有权衡的"

## 管线编排绕行复看

在**每个受门禁的阶段**运行，并在呈现产出之前于 **compose** 阶段再跑一次。用于识别那些用临时 Python 替换了管线的 agent。

### 检查项（使用 `lib.production_audit.audit_project(project_dir)`）

1. **审批门禁漂移**（`approval_gate_drift`）：某个受门禁的检查点（`proposal`、`script`、`scene_plan`、`assets`）状态为 `completed` 且 `human_approved=true`，而该阶段任何 `user_visible` 的 decision_log 条目仍然是 `user_approved=false`。→ **CRITICAL** —— "检查点声称已获人工批准，但 decision_log 并不支持。把该阶段重新打开为 awaiting_human；不要伪造审批。"

2. **阶段顺序违规**（`stage_order_violation`）：`get_completed_stages()` 不是管线阶段列表的前缀。→ **CRITICAL** —— "阶段完成顺序错乱 —— 很可能是某个绕行脚本跳过了 director 技能。"

3. **compose 无工具轨迹**（`compose_without_tool_trace`）：`compose` 为 `completed`、`assets` 为 `completed`，但 `events.jsonl` 中没有任何 assets 阶段工具（`tts_selector`、`piper_tts`、`image_selector`、`frame_sampler`、`subtitle_gen` 等）的成功 `finish` 事件。→ **CRITICAL** —— "compose 完成了却没有注册表工具事件 —— 生产很可能是通过临时脚本跑的。请通过阶段 director 重跑，让 BaseTool 的埋点记录事件。"

4. **非生产脚本滥用**：若 agent 在一次生产运行中调用了仓库根目录下匹配 `rerun_*.py` 或 `run_*_assets.py` 的脚本 → **CRITICAL** —— "使用了非生产的绕行脚本。请只用 director 技能，从 `get_next_stage()` 重跑。"

5. **临场编排**（自动化判定不明确时的会话复看）：agent 用 shell 目录列举（`dir`、`ls`、`Get-ChildItem`、`find`）去探索 `projects/`，而不是用 `python -m lib.project_status <id>`；或者写了跨阶段串联工具的多阶段临时 Python。→ 首次出现为 **SUGGESTION**；若它跳过了 director 技能或没留下工具轨迹，则为 **CRITICAL**。

6. **忽视自省能力**：agent 不跑探索性 shell 就说不出 `next_stage` 或 artifact 路径。→ **SUGGESTION** —— "在临场发挥之前先用 `lib.project_status`。"

7. **直接编辑 artifact 文件**：agent 用编辑器/shell 重写了 `decision_log.json`、`checkpoint_*.json` 或 `artifacts/*.json`，而不是用 `write_checkpoint()` / `lib.decision_log.append_decisions()`。→ **CRITICAL** —— "项目 JSON 是契约数据；只能用库 API。"

8. **Decision log 篡改**：agent 修改了已有决策条目上的字段（例如把陈旧行的 `user_visible` 翻转），而不是以相同的 `(category, subject)` 追加一条新的已批准条目。→ **CRITICAL** —— "违反了 append-only 审计轨迹。"

9. **配音可听性**（`voice_listenability_violation`）：旁白使用了低于 0.85 的 Piper `length_scale`、低于脚本 `provider_notes` 的值、超出 0.92–1.05 的 TTS 后 `atempo`，或素材摘要里出现了 `atempo fit`。→ **CRITICAL** —— "语速超出正常可听上限；请以自然语速重新生成 TTS 并延长时间线。"

### 严重级别汇总：
- 任何 `severity=critical` 的 `audit_project` 发现：**CRITICAL** —— 在修好、或用户在 `decision_log` 中明确接受一次有记录的降级之前，阻止呈现。
- 没有自动化检测手段的绕行模式（agent 在会话中承认用 `python -c` 做编排）：**CRITICAL** —— 补救措施同上。

见 AGENT_GUIDE.md → Pipeline Bypass Prohibition (HARD RULE)。

## 创意差异化复看

在 **scene_plan** 和 **edit** 阶段运行。用于防止"每支视频都长一个样"的失败模式。

### 检查项：
1. **变化度检查**（仅 scene_plan）：用 `lib/variation_checker.py` → `check_scene_variation(scenes)`。
   - 若判定为 "poor"（分数 ≤ 2）：**CRITICAL** —— "场景方案缺乏变化：[列出违规项]"
   - 若判定为 "fair"（分数 ≤ 3）：**SUGGESTION** —— 记下检查器给出的具体建议

2. **Playbook 匹配度**：当前 playbook 适合这个内容吗？
   - 电影感预告片用了 "clean-professional" 主题 → 标记不匹配
   - 教育讲解在用户未要求的情况下用了 "anime-ghibli" 主题 → 标记

3. **镜头语言完整性**（scene_plan）：
   - 每个场景至少应有 `shot_size` 和 `shot_intent`
   - 主镜头时刻应有完整的 shot_language（全部 6 个字段）
   - 把 shot_language 为空的场景标为 **SUGGESTION**

4. **Renderer family 匹配**（edit 阶段）：
   - edit_decisions 中的 `renderer_family` 是否与 proposal 阶段设定的一致？
   - 若在 decision log 中没有记录理由就发生了变更 → **CRITICAL**

5. **Render runtime 匹配**（edit 和 compose 阶段）：
   - edit_decisions 中的 `render_runtime` 必须与 proposal_packet.production_plan.render_runtime 一致
   - 若变更了却没有在 decision_log 中记录 `render_runtime_selection` 决策 → **CRITICAL**
   - 在 compose 阶段，`final_review.checks.promise_preservation.runtime_swap_detected` 必须为 `false`。若为 `true` 且没有已获批的 `render_runtime_selection` 决策 → **CRITICAL**
   - "compose 时运行时不可用"不构成静默切换的借口 —— 正确做法是上报、取得批准、记录决策，然后再跑。

6. **运行时选择是否呈现了两个选项**（proposal 阶段，强制）：
   - 查询 `video_compose.get_info()["render_engines"]`。若 `remotion` 和 `hyperframes` 都为 `True`，则 `decision_log` 中的 `render_runtime_selection` 决策的 `options_considered` **必须**同时包含两个运行时。
   - 机器上两个都可用，而 `render_runtime_selection` 的 `options_considered` 只有一个运行时 → **CRITICAL**。agent 静默取了默认值；用户没有被呈现另一个选项。重新打开 proposal 阶段并把两者都呈现出来。
   - 若只有一个运行时可用，`options_considered` 仍必须列出不可用的那个，并注明 `rejected_because: "runtime not available on this machine"` —— 否则审计轨迹就丢失了"这个选择是被约束的、而非自由裁量的"这一事实。
   - 按 AGENT_GUIDE.md > "Present Both Composition Runtimes (HARD RULE)"：管线建议的"默认"运行时**不是**跳过与用户对话的许可证。

## 交付承诺复看

在 **edit** 和 **compose** 阶段运行。使用 `lib/delivery_promise.py`。

### 在 edit 阶段：
1. 从 proposal packet 或 edit_decisions 的元数据中提取交付承诺
2. 对解析出的 cut 列表运行 `promise.validate_cuts(cuts)`
3. 若 `valid` 为 False：**CRITICAL** —— "交付承诺违规：[violations]"
4. 检查 `motion_ratio`：若一个以运动为主的承诺下运动类 cut 少于 50%，即便技术上合法也要标出来

### 在 compose 阶段：
1. video_compose.py 里的 `_pre_compose_validation()` 会自动强制执行这一点
2. 复看应确认该校验没有被绕过（检查 render report 中的警告）
3. 若在以运动为主的承诺下运动占比很低却仍渲染成功，标为 **SUGGESTION**

## 源素材理解复看

当存在用户提供的媒体文件时，在 **research** 和 **proposal** 阶段运行。

### 检查项：
1. **是否存在**：若项目中提供了用户文件，是否存在 `source_media_review` artifact？
   - 若有用户媒体却没有 `source_media_review`：**CRITICAL** —— "用户提供了媒体，但 agent 在规划之前没有检视它。请先运行 `lib/source_media_review.review_source_media()` 再继续。"
2. **是否真的检视过**：每个文件条目是否都有 `reviewed: true` 和非空的 `technical_probe`？
   - 若 `reviewed` 缺失或 `technical_probe` 为空：**CRITICAL** —— "source_media_review 声称已复看，但里面没有探测数据。这个文件其实没有被检视过。"
3. **规划是否体现**：`planning_implications` 是否出现在 proposal 的制作计划中？
   - 若识别出了质量风险（例如分辨率低、单声道音频）但 proposal 只字未提：**SUGGESTION** —— "源素材存在质量风险，而 proposal 没有应对。"
4. **内容准确性**：方案是否依赖了源素材中其实并不存在的内容？
   - 例如方案假定有访谈对白，但 transcript_summary 显示没有人声：**CRITICAL** —— "方案假定有对白，但源素材中没有人声。"
5. **不要幻觉内容**：agent 不得仅凭文件名推断出没有依据的内容。若 `content_summary` 写着"访谈素材"，而探测结果只显示 3 秒无声视频，标为 **CRITICAL**。

### 严重级别：
- 有用户文件却缺少 `source_media_review`：proposal 阶段 **CRITICAL**
- 未经检视的文件（无探测数据）：**CRITICAL**
- 方案未反映质量风险：**SUGGESTION**
- 方案假定了源素材中没有的内容：**CRITICAL**

## 最终自评复看

在 **compose** 和 **publish** 阶段运行。确保 agent 复看了真正渲染出来的成品。

### 在 compose 阶段：
1. **是否存在**：`render_report` 旁边是否有一份 `final_review` artifact？
   - 若缺失：**CRITICAL** —— "compose 产出了 render_report 但没有 final_review。agent 必须在呈现之前检视渲染成品。"
2. **状态检查**：`final_review.status` 是什么？
   - `pass` → 可以，继续
   - `revise` → agent 本应在呈现之前修好问题。若管线仍然继续了：**CRITICAL** —— "自评发现了需要修订的问题，agent 却照样呈现了。"
   - `fail` → 管线**不得**继续。若继续了：**CRITICAL**
3. **检查完整性**：5 项必需检查都必须有数据：
   - `technical_probe` 必须显示合法的容器，且时长/分辨率合理
   - `visual_spotcheck` 必须有 `frames_sampled >= 4`
   - `audio_spotcheck` 必须报告旁白/音乐是否存在
   - `promise_preservation` 必须确认 `delivery_promise_honored`
   - `subtitle_check` 必须报告字幕的有无
   - 任何一项数据缺失：**SUGGESTION** —— "自评检查 [X] 数据不完整"
4. **承诺保持**：若 `promise_preservation.silent_downgrade_detected` 为 true：**CRITICAL** —— "自评检测到从运动主导到静图主导的静默降级。"

### 在 publish 阶段：
1. 确认 `final_review` 作为必需 artifact 被传递了下来
2. 若 `final_review.status` 不是 `pass`：**CRITICAL** —— "自评未通过，不能发布"
3. 若 `final_review.issues_found` 非空且 `recommended_action` 不是 `present_to_user`：**SUGGESTION** —— "自评发现了问题；发布前请确认它们已被解决"

## 合成编写模式复看

templated→atelier 的倒置（`AGENT_GUIDE.md` → "Composition Authoring Mode" + `skills/meta/bespoke-composition.md`）是治理规则，不是建议。reviewer 是执行点：没有这些检查，下一个 agent 就会悄悄退回现成的 cut-schema，于是每支视频又开始长得一样。

### 在 proposal 阶段：
1. `decision_log` 中必须有一条 `composition_mode` 决策，`options_considered: ["templated","atelier"]`，并且 `selected` 的取值附有与 brief 挂钩的真实理由。
   - 完全没有 `composition_mode` 决策：**CRITICAL** —— "proposal 缺少 composition_mode 选择。atelier vs templated 是必须呈现的决策（见 AGENT_GUIDE.md → Composition Authoring Mode）。"
   - 决策只考虑了一个选项：**CRITICAL** —— "记录了 composition_mode 决策，却没有把 templated 和 atelier 两个备选都呈现出来。"
2. 对于**旗舰作品**（brief 标记为 营销 / 发布 / 品牌片 / 有质量要求的讲解视频 / 任何以质量为核心的单件交付物）而 `selected == "templated"` 时：**CRITICAL** —— "旗舰 brief 却把 composition_mode 锁成了 'templated'。按教条默认应为 atelier；选 templated 必须在 `decision_log.<entry>.reason` 中给出明确理由（例如本地化变体、批量、有时限的草稿）。" 只有当 reason 字段点名了某个被认可的例外时才免除。
3. 若 `composition_mode == "atelier"` 而 `proposal_packet` 缺少 `art_direction` 声明（配色、字体、运动、标志性装置）：**CRITICAL** —— "atelier proposal 缺少艺术指导承诺。按 `skills/meta/bespoke-composition.md` 第 1 步，艺术指导必须在编写场景*之前*写下来。"

### 在 scene_plan / edit 阶段（当 composition_mode == "atelier" 时）：
1. `edit_decisions.composition_mode` 必须等于 `"atelier"`，且 `edit_decisions.bespoke.{entry, composition_id, art_direction}` 必须全部设置。
   - 缺少 `entry`/`composition_id` 中任何一项：**CRITICAL** —— "atelier compose 契约不完整；渲染会被 `_render_via_atelier` 拒绝。"
   - 缺少 `art_direction`：**CRITICAL** —— "atelier 没有艺术指导声明；reviewer 无法评估独特性。"
2. `edit_decisions.cuts` 中出现任何现成 `cut.type` 场景类型（`text_card`、`stat_card`、`bar_chart`、`kpi_grid`、`callout`、`comparison`、`hero_title`、`terminal_scene`、`anime_scene`、`progress_bar`、`pie_chart`、`line_chart`）：**CRITICAL** —— "atelier 作品去拿了现成的 cut.type {name}。请手工编写这个场景；现成注册表是机制大全，不是零件箱（`skills/meta/bespoke-composition.md`）。"

### 在 compose 阶段（当 composition_mode == "atelier" 时）：
1. compose 阶段的 `final_review.checks.atelier` 块必须存在。若缺失：**CRITICAL** —— "atelier 渲染跳过了教条检查 —— `_render_via_atelier` 返回时没有 `atelier` 检查；排查工具接线。"
2. 若 `final_review.checks.atelier.stock_reuse_detected == true`：**CRITICAL** —— "定制项目内部导入了现成注册表（{offending_imports[0].file} → {offending_imports[0].import}）。请手工编写这个场景；不要从现成的 src/ 导入。"
3. 若 `final_review.checks.atelier.art_direction_declared == false`：**CRITICAL** —— "atelier 渲染没有艺术指导声明。重新渲染之前先设置 `edit_decisions.bespoke.art_direction`。"
4. **场景独特性 —— 不许用主角组件当骨架（必须留档）。** 每个场景采样一帧有代表性的画面（例如每个 `props.sections[i]` 的时间窗中点），并在复看记录中回答：
   - *每个场景是否都有一个独特的主要视觉主体？* 若有两个或以上场景共用主要视觉（同一个主角元素只是换了字幕 —— 那支从不离开的蜡烛、每个节拍都在的浏览器边框、当作骨架用的评分圆环）：**CRITICAL** —— "检测到主角组件骨架：场景 {ids} 共用了主要视觉主体。按 `skills/meta/bespoke-composition.md` 第 1.5 步，每个场景都必须挣得自己的 composition；标志性装置属于某一个高潮节拍，而不是骨架。请重新规划受影响的场景。"
   - *`art_direction` 中点名的标志性装置，是否至少在一个节拍中真实出现？*（否 ⇒ CRITICAL，要么重写，要么把声明更新为与实际构建相符）
   - *标志性装置是否出现在**大多数**节拍中？*（是 ⇒ CRITICAL —— 见上面的主角组件骨架；标志性装置本就应当稀缺）
   这项检查不能被静默跳过；缺少逐场景清单的记录本身就是 **CRITICAL**（"scene_distinctness inventory not recorded"）。
5. **字幕 / 屏幕文字去重（必查）。** 把当前字幕文本与同一时间窗内渲染的任何屏幕文字做比对：
   - 若内容相同（字幕在复述旁白已经念出来的那句场景标题/大标题）：**CRITICAL** —— "字幕在 {t} 秒处与屏幕文字重复（'{text}'）。每件作品定一次：字幕是在补充信息（数字、人名、翻译），还是在做无障碍字幕；同一句话不要两者兼有。要么把这些场景的 `captions=[]` 清空，要么删掉多余的屏幕 SerifLine。"
6. **独特性复看（人工判断，必做）。** 批准渲染之前，reviewer 必须在复看记录中明确回答：
   - *"这支视频能不能是任何别的产品的视频？"*（是 ⇒ CRITICAL，重写艺术指导）
   - *"它的视觉语言是否复用了我之前做过的某种外观？"*（是 ⇒ CRITICAL，重写）
   独特性属于工具无法自动化的审美判断领域；reviewer 在这个问题上缺席，本身就是一条 **CRITICAL** 发现（"distinctness review not recorded"）。

### 在 publish 阶段（当 composition_mode == "atelier" 时）：
1. 上面全部六项 atelier compose 阶段检查（`atelier` 块是否存在、stock_reuse、art_direction_declared、scene_distinctness、字幕/文字去重、人工独特性复看）都必须在复看记录中显示为 `resolved`。任何一项未解决：**CRITICAL** —— "存在未解决的教条或独特性发现，不能发布这件 atelier 作品。"
