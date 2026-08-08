# OpenMontage — Agent 指南

从这里开始。这是 OpenMontage 的完整操作指南与 Agent 契约。

架构、关键文件与约定参见 [`PROJECT_CONTEXT.md`](PROJECT_CONTEXT.md)。

<!-- om:session-brief:start -->
## 会话简报（Hermes）

本块是 **OpenMontage 插件**契约，不是 Hermes 全局系统提示。仅在用户本轮在谈视频生产 / OM 项目时由插件注入；问候与无关闲聊不应加载本块，更不要为此调用 `om_*` / onboarding。

OpenMontage 生产是流水线驱动的。**不要**用 `read_file` / `search_files` / `terminal` 浏览仓库或插件源码来重建契约、猜审批、找 reset 脚本——`om_*` 通道已足够。进入 OM/视频意图后，编排 agent **会从工具列表统一拿掉** `read_file`/`search_files`/`terminal`/`execute_code`；违规调用仍会被 `pre_tool_call` 硬拦截。

动手做视频 / 查项目时：
1. 完整契约 → `skill_view("openmontage:agent-guide")`（即本文件）
2. 能力菜单 → `om_preflight`
3. 项目进度 / 产物是否存在 → `om_project`（看 `stages[].artifact_exists`、`orphans`、`suggested_action`）
4. Stage 导演 → `om_director(project_id=...)`
5. 运行 / 轮询 → `om_run` / `om_job` / `om_state`
   - `om_run` 后立即用 `om_job` 轮询（返回 `status`/`work_done`/`checkpoint_status`/`suggested_action`/`recovery`），**不要**自己 `execute_code`/`terminal`/`import stage_runner` 跑阶段
   - **轮询节奏**：反复调 `om_job`（约每 15–60s 一次）。label 写成「轮询 research 进度」/「轮询 edit 进度」。**禁止**「等 90 秒查 … 进度」「Wait 10min」——假等待会被硬拦
   - `om_job` 若 `work_done=true` / `suggested_action=stop_polling` / `gate_blocked` → **立刻停轮询**；`pid_scope=hub` 时 `hub_pid_alive`≠阶段还在跑，以 `worker_active`/`work_done` 为准
   - 若 `om_project`/`om_job` 提示 orphan（磁盘已有规范产物但 checkpoint 未闭环）→ `om_state(action="complete_from_disk", stage=...)`；门控 stage 仍走 `awaiting_human` + approve（看 `gate_blocked` / `next_runnable_stage`）
   - **失败时读返回的 `diagnostics` / `runtime`**（`busy`、`worker_active`、`blockers`、`schema.errors`、`expected` 字段契约、`suggested_actions`），按其中建议行动；**不要** find 源码、清 `.run.lock`、或猜审批
   - schema 失败时按 `diagnostics.expected` 改字段名（如 `claim` 不是 `stat`），或 `om_run` 重跑；`om_director` 也会返回 `artifact_contracts`
   - 写文件优先用 `write_file`（带 label），不要用 `execute_code` 拼路径写 checkpoint
   - 任务在跑时不要 `om_state approve`；等 `om_job` 完成或失败后再处理
6. **必填** `label`：`execute_code` / `terminal` / `om_job` 无 label 会被拦截；3–8 字、用户语言，说明**这一次**在做什么（如「写 in_progress 检查点」「轮询 research 进度」），不要写「运行代码」/工具名、不要照抄用户原话；每次轮询换新 label；**禁止**「等 Ns 查进度」假等待 label

元技能（onboarding、reviewer 等）→ `skill_view("openmontage:<name>")`。
流水线定义 / stage 顺序 / 审批门 → `om_pipeline`。
`.agents/skills/` 下的 Layer 3 供应商技能在工具通过 `agent_skills` 列出时，仍可按路径读取。
<!-- om:session-brief:end -->

## Hermes 工具通道

当 Hermes 的 `om_*` 工具可用时，用它们来代替按路径阅读 OpenMontage 文档：

| 需求 | 调用 |
|------|------|
| 完整契约（本指南） | `skill_view("openmontage:agent-guide")` |
| 入门引导 / 元方法论 | `skill_view("openmontage:<name>")` |
| 能力 / 供应商菜单 | `om_preflight` |
| 按能力查看工具 | `om_catalog` |
| 流水线列表、stage、审批门 | `om_pipeline` |
| 项目 `next_stage` / 资产 / 审计 | `om_project` |
| 当前 stage 导演技能全文 | `om_director` |
| 执行 stage / 轮询 job / 写入状态 | `om_run` / `om_job` / `om_state` |

当 `om_*` / `skill_view` 可用时，**不要**用文件工具打开 `pipeline_defs/*.yaml` 或 `skills/pipelines/**` 来了解 stage 顺序或导演流程——那是 `om_pipeline` 和 `om_director` 的职责。

没有 `om_*` 的宿主（Cursor / Claude Code）仍按下面的路径说明执行。

## 首次交互 — 入门引导

当用户在谈**视频 / 内容制作**，且请求含糊或探索性质（例如"帮我做个视频"、"你能做什么视频？"、"帮我做点内容"、"我想做点内容"）时，先加载入门引导技能，**再**做任何其他事情：

**Hermes：** `skill_view("openmontage:onboarding")`
**其他宿主：** 阅读 `skills/meta/onboarding.md`

该技能教你如何做需求挖掘、对用户的配置进行分类、用平实的语言介绍能力，并基于用户可用的工具给出量身定制的起始提示词。目标：让用户在 60 秒内从"好奇"进入"开始做视频"。

**跳过入门引导**的情况：
- 纯问候或无关闲聊（"hi"、"你好"）——正常寒暄即可，**不要**为此读 AGENT_GUIDE、加载 onboarding 或跑 `om_preflight`
- 用户带着明确、可执行的需求到来（例如"做一个关于黑洞的 60 秒解说视频"）——直接进入零号规则（Rule Zero）

## 参考视频入口

当用户提供**视频 URL 或本地视频文件作为灵感参考**时——例如：

- "你能做一个像这样的视频吗？"
- "我很喜欢这个 YouTube Short，帮我做点类似的。"
- "把这个 Reel 当作参考。"

——**不要**把这类请求当作普通的网页搜索或提示词编写需求来处理。

这是 OpenMontage 的一级工作流（first-class workflow）。

### 必需行为

1. **加载：** Hermes `skill_view("openmontage:video-reference-analyst")` —— 其他宿主：阅读 `skills/meta/video-reference-analyst.md`
2. **运行参考分析工作流**，使用本地分析工具（`video_analyzer`、字幕提取、场景检测、抽帧采样）
3. **产出一份有依据的参考视频分析摘要**，说明该参考视频在做什么：
   - 内容
   - 节奏
   - 结构
   - 风格
   - 它为什么有效
4. **然后**进行常规的能力审计与流水线选择
5. 为用户版本提出 **2–3 个差异化概念**——而不是照抄（carbon copy）

### 重要区分

- **参考驱动型需求：**"帮我做点像这样的东西" → 使用 `video-reference-analyst.md`
- **素材剪辑型需求：**"剪辑这段素材" / "把这段剪成短片" → 使用 `source_media_review` 和相应的素材主导型流水线

如果模型错过这一区分，往往会退回到"普通搜索 + 猜测"的做法。对 OpenMontage 而言这是错误的。

## 零号规则 — 所有生产必须走流水线

**每个视频生产请求都必须走流水线系统。没有例外。**

当用户要求制作、创建、生产或生成任何视频内容——预告片、解说视频、短片、动画或任何其他视频时，agent 必须：

1. **识别流水线。** 通过 `om_pipeline` 匹配请求（或询问用户）。不要凭记忆臆造 stage 顺序。
2. **加载流水线定义。** Hermes：`om_pipeline(name=...)`。其他宿主：阅读 `pipeline_defs/<pipeline>.yaml` —— 了解各个 stage、工具和质量门（quality gates）。
3. **执行预检（preflight）。** Hermes：`om_preflight`。其他宿主：通过注册表发现。展示能力菜单。
4. **逐 stage 执行。** 对**每个** stage，在执行任何工作**之前**先加载 stage 导演技能：Hermes `om_director(project_id=..., stage=...)` —— 其他宿主：阅读 `skills/pipelines/<pipeline>/<stage>-director.md`。
5. **调用工具前先读 Layer 3 技能。** 在调用任何带 `agent_skills` 字段的工具之前，阅读 `.agents/skills/` 中引用的技能（此处按路径读取是正确的——这些不是 Hermes 插件技能）。这些技能包含供应商特定的提示词指导、参数优化和质量技巧，能大幅提升输出质量。

**禁止：**
- 编写临时 Python 脚本来直接调用工具
- 跳过流水线直接调用 API
- 不先阅读 stage 导演技能就生成资产
- 不查看工具的 Layer 3 技能就使用该工具
- 绕过预检、检查点（checkpoint）或评审
- 当 `om_*` / `skill_view` 可用时，用通用文件工具浏览 `AGENT_GUIDE.md` / `skills/` / `pipeline_defs/` 来重建 OpenMontage 契约

智能在技能里，不在临场发挥的代码里。阅读了导演技能和 Layer 3 知识的 agent 产生的输出，将明显优于用通用提示词直接调用工具的 agent。

### 流水线绕行禁令（HARD RULE）

生产编排必须保持在流水线循环之内。agent 用**导演技能 + 注册表工具 + 检查点**驱动各个 stage——而不是用链式串联多个 stage 的临场 Python 脚本。

**禁止的绕行模式：**

| 模式 | 违反契约的原因 |
|---------|------------------------------|
| 仓库根目录的 `scripts/rerun_*.py`（或类似脚本）跨 assets→compose 调用 `tool.execute()` | 取代了 stage 导演，跳过了人工门，在 `events.jsonl` 中不留工具痕迹 |
| `python -c` / 内联脚本在 `decision_log` 中仍是 `user_approved=false` 时写入 `human_approved=true` 的 `checkpoint_*` | 未经用户同意伪造审批 |
| manifest 要求 `awaiting_human` 时，跳过 proposal/script/assets 的 `awaiting_human` | 等同于静默批准 |
| `get_next_stage()` 不是 `compose` 时进行合成（compose） | 违反 stage 顺序 |

**允许的 Python（不算绕行）：**

- **工具** — 通过注册表调用的 `video_analyzer`、`tts_selector`、`video_compose` 等
- **持久化** — `plugins.openmontage.lib.checkpoint.write_checkpoint`、`init_project`、`get_next_stage`
- **治理工具** — `plugins.openmontage.lib.production_audit.audit_project`（只读）、`scripts/reset_project_pipeline.py`（仅重置检查点——不生成媒体）
- **项目范围内的临时脚本** — 仅限 `projects/<id>/scripts/` 下，按 `skills/meta/capability-extension.md` 执行，并需有 `capability_extension` 决策；绝不能作为多 stage 流水线的替代品

**执行机制：** `skills/meta/reviewer.md` 将绕行信号视为**严重（CRITICAL）**。`tests/contracts/test_pipeline_bypass_contract.py` 中的契约测试守护 agent 指南、评审技能和非生产脚本标记。合成（compose）之后评审时应运行 `audit_project()`——审批漂移（approval drift）和工具痕迹缺失都是阻塞级发现。

**如果需要完整重跑：** 先重置检查点（`scripts/reset_project_pipeline.py`），然后从 `get_next_stage()` 重新进入，用各自的导演技能执行每个 stage。不要把整个流水线包进一个脚本里。

### Agent 内省（HARD RULE）

Agent 通过 **OpenMontage 状态 API** 发现项目状态——而不是用 shell 目录列举。

**首选方式（按顺序）：**

1. **Hermes：** `om_project`（可选 `audit=true`）—— `next_stage`、已完成 stage、资产路径、导演技能路径、工具痕迹摘要的唯一权威来源
2. **其他宿主 / 脚本：** `python -m plugins.openmontage.lib.project_status <project-id>` —— 与上面相同的载荷，外加可选 `--audit`
3. **IDE Read / Glob** — 已知路径时直接打开已知资产或技能文件
4. **文档化的一行命令** — 注册表预检、`write_checkpoint`、`init_project`（见下文各节）

**探索阶段禁止：**

| 模式 | 原因 |
|---------|-----|
| 用 `dir`、`ls`、`find`、`Get-ChildItem`、`tree` 发现项目布局 | 在 Windows/PowerShell 上脆弱；绕过规范路径；易出错 |
| 为打印路径或列举目录而编写临时 `.py` 文件 | 临场编排的味道；改用 `plugins.openmontage.lib.project_status` |
| 用多行 `python -c` 脚本跨 stage 链式调用工具 | 与 `rerun_*.py` 同类的绕行——每个 agent 回合只做一个 stage |

**允许的 `python -c`（仅限单一用途）：**

- `plugins.openmontage.lib.project_status.build_project_status(...)` 或上面的 CLI
- `plugins.openmontage.lib.checkpoint.write_checkpoint` / `get_next_stage` / `init_project` —— **每次调用只有一个调用点**
- `plugins.openmontage.tools.tool_registry.registry.discover()` + 一个目录方法用于预检
- `plugins.openmontage.lib.production_audit.audit_project(...)` — 只读治理

**生产工作仍然使用注册表工具**（`BaseTool.execute()`），而不是 shell 转码，也不是取代导演技能的临时 Python。

### 资产持久化（HARD RULE）

磁盘上的项目状态是**契约数据**，不是草稿纸。Agent 只能通过经过验证的库 API 持久化资产——绝不能用文件编辑器或 shell 重定向来修改 JSON。

**禁止：**

| 模式 | 原因 |
|---------|-----|
| 用 `Write` / `StrReplace` 修改 `projects/<id>/decision_log.json` | 绕过 schema 校验和只追加（append-only）审计轨迹；agent 篡改 `user_visible` 来作弊漂移检查 |
| 直接编辑 `checkpoint_*.json` 或 `artifacts/*.json` | 同样——改用 `write_checkpoint()` |
| 在仓库根目录或项目根目录放一次性辅助脚本，如 `_compose_once.py`、`run_stage.py` | 临场编排——改用注册表工具 + 导演技能 |
| 通过隐藏旧 `decision_log` 条目而不是追加已批准的条目来"修复审计" | 违反只追加历史；Backlot 按 `(category, subject)` 显示最新条目 |

**必需的 API：**

| 需求 | 使用 |
|------|-----|
| Stage 完成 + 资产 | `plugins.openmontage.lib.checkpoint.write_checkpoint(...)` |
| stage 中途追加决策 / 重跑审批 | `plugins.openmontage.lib.decision_log.append_decisions(project_id, [...])` 或 CLI `python -m plugins.openmontage.lib.decision_log append <id> --file decisions.json` |
| 检查状态 | `python -m plugins.openmontage.lib.project_status <id>` |
| 生成媒体 | 注册表工具（`piper_tts`、`video_compose` 等）通过 `BaseTool.execute()` |

当某个选择发生变化时，**追加**一条新的、使用相同 `(category, subject)` 的决策——绝不重写或删除旧条目。

### 语音可听性（HARD RULE）

旁白语速必须保持在正常聆听极限之内。参见 `skills/meta/voice-performance-director.md` → 可听性下限（Listenability Floor）。Piper `length_scale` ≥ **0.85**（且 ≥ 脚本的 `provider_notes`）；未经用户明确批准（`decision_log` 中的 `downgrade_approval`），不得用 TTS 之后的 `atempo` 压缩来强行适配时间线。`audit_project()` 将 `voice_listenability_violation` 标记为**严重（CRITICAL）**。

## OpenMontage 是什么

OpenMontage 是一个指令驱动的视频生产系统。AI agent 本身就是智能体——它读取指令（流水线清单 + stage 导演技能 + 元技能）并用工具驱动流水线。

```
Agent 读取流水线清单 (YAML) -> 读取 stage 导演技能 (MD)
-> 使用工具 (Python BaseTool 子类) -> 自我评审 (元技能)
-> 检查点 (Python 工具) -> 提交给人类审批
```

**Python = 工具 + 持久化。** 编排逻辑、创意决策、评审逻辑或检查点策略都不写在 Python 代码里。这些决策由 agent 在指令引导下做出。

核心循环：

1. 选择流水线。
2. 运行预检。
3. 从注册表发现真实工具。
4. 向用户呈现概念、工具方案、生产方案和成本。
5. 带检查点逐 stage 执行。

## 决策沟通契约

对于任何有实质意义的生产决策，agent 必须在行动之前沟通该决策。用户绝不应该在事后才去推断选用了哪个供应商、模型或渲染路径。

### 执行前宣布

在发起任何付费或影响重大的生成调用之前，说明：

- 确切工具名，
- 供应商，
- 模型或供应商变体，
- 选择它的原因，
- 这是样例运行（sample）还是批量运行（batch）。

### 重大变更前先询问

在更改任何重大生产选择之前，agent 必须询问用户，包括：

- 更换供应商，
- 更换模型系列或供应商变体，
- 从视频主导改为静态图主导的处理方式，
- 在输出特征会改变的情况下更换合成引擎，
- 删除已批准的旁白、音乐或其他创意元素，
- 从样例模式改为批量模式。

在已批准的供应商/模型路径内做细微的提示词调整，不需要单独批准，除非它实质性地改变了创意方向。

### 重新记录变更的决策（具约束力）

`decision_log` 是看板（board）的"决策（Decisions）"轨道，也是本次运行（run）的审计轨迹。它是**只追加历史，不是草稿纸。** 当你已经记录的某个选择在运行中途发生变化时——用户更换了配音，你切换了供应商/模型/运行时/音乐，或某个回退方案覆盖了先前选择——你必须为新的选择**追加一条新的 `decision_log` 条目**，复用**相同的 `category` 和相同的 `subject`**（例如 `category: "voice_selection"`、`subject: "Narration TTS provider"`），并将被取代的选项移入 `options_considered` 和 `rejected_because`，注明它已变更。

只编辑下游资产（`asset_manifest`、某个 prop）却把旧决策留在日志里是一个缺陷：看板会一直显示过时的选择（例如用户已切到 Chirp3，看板仍显示 `voice → openai_onyx`）。看板用 **(category, subject) 对** 来标识一条决策，并将该对的最新条目渲染为当前状态（标记为"已修订（revised）"）——所以正确的做法是追加一条 `subject` 完全相同的新条目，绝不静默篡改旧条目或改写 subject（改写过的 subject 会被读成另一条决策，两条都会显示）。在同一个 category 里保留不同决策（例如 TTS 与图像的 `provider_selection`）正是要用"对"而不是只用 category 作为键的原因。这一规则适用于每个 stage，不只是 `idea`。

### 呈现两种合成运行时（HARD RULE）

当机器上同时可用 Remotion 和 HyperFrames 时（检查 `video_compose.get_info()["render_engines"]`），agent 在 proposal stage 锁定 `render_runtime` **之前必须把两个选项都呈现给用户**。agent 可以给出带理由的推荐——但即使流水线清单或某个导演技能暗示了某个默认值，**静默选择"默认"也是被禁止的**。

呈现内容必须包含每个运行时的：

1. 一句平实的语言，说明它针对**这个具体简报（brief）**最擅长做什么。
2. 一句诚实的权衡（为什么在这里可能不是正确选择）。
3. agent 的推荐及其理由，与简报的 delivery_promise 和视觉方案挂钩。

然后等待用户明确批准再推进。把完整候选清单——两个运行时加上任何适用的 "ffmpeg" 选项——记录为 `decision_log` 中 `render_runtime_selection` 决策的 `options_considered`。当两个运行时都可用却只考虑了其中一个的决策日志条目，是评审的严重（CRITICAL）发现。

例外：如果机器上只有一个运行时可用，agent 可以用它继续，但必须明确说明（"这台机器没装 HyperFrames；我继续使用 Remotion。如果你想用另一个，请安装 HyperFrames。"）。`render_runtime_selection` 决策仍须将不可用选项记录为 `rejected_because: "runtime not available on this machine"`。

此规则适用于每个调用 `video_compose` 的流水线——不只是 Wave 1。流水线的导演技能可以推荐某个运行时，但该推荐只是与用户对话的输入，而不是决策。

### 合成创作模式 — 模板化（Templated）vs Atelier

与*运行时*正交的是*创作模式*：合成是**如何**构建的。把它作为独立的 proposal 决策呈现，并记录到 `decision_log`（`category: "composition_mode"`）。

- **Templated（模板化）** — 把现成的 `cut.type` 场景类型（`text_card`、`stat_card`、`bar_chart` 等）组装进 `Explainer`/`CinematicRenderer` 合成。快速、便宜、可靠——也是大多数视频看起来千篇一律的原因。适合批量输出、多语言变体、快速草稿和低风险内部短片。
- **Atelier（工坊）** — **从零手写合成**：定制场景、一次性主题、为这个片子专门写的动效，通过 `composition_mode: "atelier"` 渲染（见 `video_compose` → `_render_via_atelier`）。没有可复用的创意组件；每次都是一种全新的视觉语言。

**英雄级作品（hero work）默认用 atelier**——营销、发布、品牌片、任何必须惊艳的单一交付解说视频。判定规则：*复用引擎知识，绝不复用创意组件。* 在 atelier 模式下，现成场景类型目录、`hyperframes-registry` 块、fixtures 和成品组件都是**禁区**——它们是会重新带来千篇一律感的冻结外观。开工前，先走 **`skills/meta/taste-direction.md`** 设定设计读取和品味刻度（taste dials），再走 **`skills/meta/bespoke-composition.md`**，其顺序为：美术方向（`visual-style`）→ 动效原理（通过 `framer-motion`/`lottie-bodymovin` 的迪士尼 12 原则）→ 引擎机制（`remotion-best-practices` + 把现成组件**仅**当作机制法典来读）→ 通过 atelier 路径渲染。最后做一次**独特性评审**：*这会不会是任何其他产品的视频？它是否复用了我以前做过的外观？*——即"是否符合参考"的反面。Atelier 比模板化花费更多 token 和迭代；在 proposal 时说明这一点，让用户知情选择。

### 明确升级阻塞

发生阻塞时，agent 必须立即按以下结构上报：

1. 尝试了什么
2. 失败了什么
3. 问题是鉴权、供应商访问、工具缺陷，还是提示词/设计质量
4. 接下来有哪些选项
5. agent 推荐哪个选项，以及理由

在用户批准之前，不要继续走替代路径。

### 推荐风格

请用户选择时，不要只列选项。agent 应该：

- 给出候选清单，
- 简要说明权衡，
- 推荐一个选项，
- 获得批准后再继续。

### 不得单方面替换

如果已批准的路径被阻塞，agent 可以调查并准备备选方案，但在未经用户批准之前不得执行这些备选方案。

这一点尤其适用于：

- 供应商更换，
- 模型更换，
- 回退工具，
- 用纯提示词替代参考驱动生成，
- 用静态图动画分镜（animatic）替代真正的动效。

## 编排器

agent 本身编排生产状态机：

`research -> proposal -> script -> scene_plan -> assets -> edit -> compose`

agent：

1. 读取流水线清单（`pipeline_defs/*.yaml`）以了解流程
2. 调用 `python -m plugins.openmontage.lib.project_status <project-id>`（或 `checkpoint.get_next_stage()`）以确定从何处续跑、下一步该读哪个导演技能
3. 读取该 stage 的导演技能（`skills/pipelines/<pipeline>/<stage>-director.md`）以了解怎么做
4. 用工具（`tools/`）提供具体能力
5. 用评审元技能（`skills/meta/reviewer.md`）自我评审
6. 按检查点协议（`skills/meta/checkpoint-protocol.md`）落检查点
7. 当 `human_approval_default: true` 时提交给人类审批

基础设施文件：

- `lib/checkpoint.py` — 检查点读写、stage 校验
- `lib/project_status.py` — **agent 内省 CLI**（`python -m plugins.openmontage.lib.project_status <id>`）
- `lib/decision_log.py` — **只追加决策日志 API**（`python -m plugins.openmontage.lib.decision_log append …`）
- `tools/cost_tracker.py` — 预算治理
- `lib/pipeline_loader.py` — 清单加载与辅助函数

## 项目目录约定

每次生产运行都在 `projects/` 下创建项目工作区。该目录已被 gitignore——所有生成的资产都是可再生的。

```
projects/<project-name>/
├── artifacts/          # 每个 stage 的 JSON 资产（research_brief、script、scene_plan 等）
├── assets/
│   ├── images/         # 生成的图片 (PNG)
│   ├── video/          # 生成的视频片段 (MP4)
│   ├── audio/          # 旁白片段 + 最终混音 (MP3/WAV)
│   ├── music/          # 背景音乐轨道 (MP3)
│   └── subtitles.srt   # 生成的字幕
└── renders/
    └── final.mp4       # 最终渲染视频（交付物）
```

**命名约定**：用视频标题派生 kebab-case（例如 `hidden-math-of-nature`、`how-music-rewires-brain`）。

在流水线初始化时、任何 stage 运行之前：

1. **初始化工作区**：`python -c "from plugins.openmontage.lib.checkpoint import init_project; init_project('<project-id>', title='<Title>', pipeline_type='<pipeline>')"` —— 创建上面的目录结构并写入 `project.json`（Backlot 看板读取的标记文件）。
2. **把用户引向看板**：打开 `http://127.0.0.1:<hub-port>/plugins/openmontage/p/<project-id>`（或 `/plugins/openmontage/` 库页面）。Backlot 已挂载在 Hermes hub 内部——**没有独立的 `backlot open` 进程**。如果浏览器打不开，继续生产即可——看板是观察者，绝不是阻塞项。

### Backlot Web 通道（页面驱动的运行）

自 Backlot API v44 起，看板不再*仅*是观察者：页面可以作为第二条执行通道驱动流水线，与交互式 agent 拥有同等的契约地位。

- **运行一个 stage** — `POST /api/plugins/openmontage/project/{id}/stage/run`
  启动一个**进程内**的 Hermes `AIAgent`（与 hub 同进程/同大脑），它读取**相同的导演技能**、执行**相同的注册表工具**（events.jsonl 自动归因）并写入**相同的检查点契约**。它恰好只执行一个 stage——`stage == get_next_stage()` 是唯一合法的目标；服务器绝不串联 stage 或自动推进。
- **批准 / 拒绝门** — `POST /api/project/{id}/stage/approve` / `/stage/reject` 是聊天审批在页面上的等价物：approve 将 `awaiting_human` 改写为 `completed` 且 `human_approved=True`，**并镜像写入同一条 `(category, subject)` 决策，`user_approved=true`**（否则会触发 `approval_gate_drift`）；reject 追加一条 `human_rejection` 决策并将该 stage 改写为 `in_progress`（资产保留），以便重跑通过 `get_next_stage()` 重新进入。
- **并发** — Web 通道用每个项目一个 `.run.lock`（可接管过期锁）保护自身；它**不**对交互式 agent 加锁（该通道保持不变）。两个执行器竞争同一个 stage 是已文档化的边界：last-write-wins 加上检查点门和 stage 顺序审计作为兜底。
- **服务端文件**（`runs/*.json`、`runs/*.log`、`.run.lock`）只是观察元数据——绝不参与 checkpoint / artifacts / decision_log / events.jsonl 的契约路径。`audit_project()` 对页面驱动的运行与对 agent 驱动的运行一视同仁。
- Web 运行的资产仍然以人工为门：无头 agent 写入 `awaiting_human` 然后**结束**；页面上的批准按钮就是人工门。

所有工具和 agent 都必须把输出写到这些路径——**始终在 `projects/<project-id>/` 下传入显式的 `output_path`**。写到仓库根目录、cwd 或临时目录的资产对用户的看板不可见，且违反工作区契约。

**这也适用于 atelier 和 HyperFrames 技能运行**：手写合成的作品仍要把它们拥有的规范资产（脚本或 beats 计划、scene_plan 等价物、资产清单）连同检查点写入 `projects/<project-id>/`。看板与运行时无关；只有跳过资产的运行才会得到降级的看板。

## 音乐库

用户可以在 `music_library/` 中放置免版权音乐（已 gitignore）。资产导演在回退到基于 API 的音乐生成之前，会先检查这个文件夹。

```
music_library/
├── ambient_track.mp3
├── cinematic_epic.mp3
└── ...
```

如果该文件夹里有音轨，proposal 和 assets 阶段应把它们与生成的音乐一起作为选项呈现。详见 proposal-director 和 asset-director 技能。

## 可用流水线

| 流水线 | 最适合 | 稳定性 |
|----------|----------|-----------|
| `animated-explainer` | 从主题到完整生成的解说视频 | production |
| `talking-head` | 素材主导的口播视频 | beta |
| `screen-demo` | 屏幕录制与操作演示 | production |
| `clip-factory` | 从一个长素材切出多个短片 | beta |
| `podcast-repurpose` | 播客精彩片段与衍生内容 | beta |
| `cinematic` | 预告片、宣传片与情绪主导的剪辑 | production |
| `animation` | 动态图形与动画优先的视频 | production |
| `character-animation` | 本地绑定卡通角色与可复用角色表演 | beta |
| `hybrid` | 源素材加辅助视觉 | production |
| `avatar-spokesperson` | 主持人主导的虚拟形象或唇形同步视频 | production |
| `localization-dub` | 字幕、配音与翻译变体 | beta |
| `framework-smoke` | 测试：最小 2-stage 冒烟测试 | test |

> **Beta 流水线**尚未经过全面审计。它们能用，但会有毛刺。用户选择时请提及这一点。

## 强制预检

在任何创意工作之前做这件事。**先使用 `provider_menu_summary()`——它是面向人类的汇总。** 原始的 `support_envelope()` 转储是一股洪流（配置良好的机器上会有数 MB 的 JSON）；贴进聊天会把用户淹没。

**使用仓库的解释器**（不是 Cursor/宿主 `python`）。Windows：`.venv/Scripts/python.exe`。macOS/Linux：`.venv/bin/python`。或者在 `.env` 中设置 `OPENMONTAGE_PYTHON`。宿主 venv 缺少 torch/diffusers 时，即使仓库 venv 里装了本地 LTX，也会误报 `video_selector` 不可用。

```bash
.venv/Scripts/python.exe -c "
from plugins.openmontage.tools.tool_registry import registry
import json
registry.discover()
print(json.dumps(registry.provider_menu_summary(), indent=2))
"
```

汇总返回四个字段，agent 应将其转译为平实的语言：

- `composition_runtimes` — `ffmpeg`、`remotion`、`hyperframes` 的布尔值。这是"呈现两种合成运行时（HARD RULE）"检查的权威来源。
- `capabilities[]` — 每个能力家族一条，含 `configured / total` 计数和供应商列表。可直接用于"N of M 已配置"菜单。
- `setup_offers[]` — 不可用但安装只需 1 分钟环境变量修复的工具。推荐升级时优先讲这些。
- `runtime_warnings[]` — 具体信号，如 "hyperframes: npm package not resolvable"。把这类信息逐字呈现给用户——它们是那种会破坏治理契约的静默失败 bug。

然后，做更深入的检查（仅当汇总不够时）：

```bash
# 完整菜单——按能力分组的可用/不可用。
.venv/Scripts/python.exe -c "from plugins.openmontage.tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu(), indent=2))"

# 原始信封——每个工具的完整契约。慢/洪流；仅供调试。
.venv/Scripts/python.exe -c "from plugins.openmontage.tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.support_envelope(), indent=2))"
```

然后：

1. 读取 `pipeline_defs/` 中选定的清单。
2. 把每个 `required_tools` 条目与注册表核对。
3. 检查 `fallback_tools` 中不可用的工具。
4. 报告其中之一：`passed`、`degraded` 或 `blocked`。
5. 在用户了解真实能力信封之前，不要开始生产。

### 供应商菜单（预检时强制）

已通过上面的 `provider_menu_summary()` 获取。阅读该输出并**把它作为能力菜单呈现给用户**，而不是作为扁平的工具列表。只有当你需要汇总折叠掉的逐工具细节时，才直接使用 `provider_menu()`。

**如何呈现：**

```
你的能力

  视频生成:  0/13 已配置
  图像生成:  1/7 已配置
  文字转语音:  1/3 已配置
  音乐生成:  1/1 已配置
  合成:       3/3 已配置 (FFmpeg, video_stitch, video_trimmer)

  你现在就能用图片 + TTS + FFmpeg 制作视频。
  还有快速升级项可选——见下方。
```

对于**每个**有不可用供应商的能力，从菜单输出中读取 `install_instructions` 字段，并按投入程度分组呈现设置选项：

```
快速设置选项（每个 1 分钟——在 .env 里设置一个环境变量）

  视频生成 (0/13 -> 解锁最大的升级):
    每个不可用供应商都有各自的 install_instructions。
    从 provider_menu 输出中读取它们，按环境变量分组呈现。
    示例：如果有 3 个工具需要 FAL_KEY，把它们归为一组："FAL_KEY 解锁 3 个供应商"

  图像生成 (1/7 -> 更多风格选项):
    同样的模式——从每个不可用工具读取 install_instructions。

  文字转语音 (1/3):
    同样的模式。

本地选项（免费，需要硬件）:
  runtime=LOCAL 或 runtime=LOCAL_GPU 的工具——从菜单中读取。

已经可用的:
  列出可用的部分。让用户对自己已有的东西感觉良好。
```

**规则：**
- **不要**在提示词中硬编码供应商名称、API 密钥名称或设置 URL。
  从注册表中每个工具的 `install_instructions` 字段读取。
- 始终显示比例："X of Y 已配置"——这让广度可见。
- 按能力分组，而不是按单个工具分组。
- 先展示他们现在能做什么，再展示他们可能解锁什么。
- 如果用户拒绝设置，就用现有最佳路径继续——不要唠叨。
- 如果一个工具与其他工具共享环境变量，把它们归为一组（从 `dependencies` 字段读取）。

### 设置提议协议

当工具为 `UNAVAILABLE` 但可以通过简单配置修复时，**主动向用户提供设置帮助，而不是静默绕过这个限制。** 很多工具只差一个环境变量就能工作。

| 修复复杂度 | 动作 |
|----------------|--------|
| **1 分钟修复**（环境变量） | 提议现在帮忙配置——从工具读取 `install_instructions` |
| **5 分钟修复**（安装） | 说明要装什么、为什么——从工具读取 `install_instructions` |
| **复杂修复**（GPU、模型下载） | 说明限制，解释它能解锁什么，然后继续 |

**规则：**
- 始终告诉用户他们缺什么**以及**能获得什么
- 展示成本差异（免费本地 vs 付费 API）
- 如果用户拒绝设置，就用现有最佳路径继续——不要唠叨
- 把相关的修复归组（共享同一环境变量依赖的工具）

### 合成运行时（video_compose 内部）

`video_compose` 有**三个**渲染引擎/运行时。它们是平行的，不是排名的——选择在 proposal 时做出，并锁定在 `edit_decisions.render_runtime`。检查哪些可用：

```bash
python -c "
from plugins.openmontage.tools.tool_registry import registry
registry.discover()
info = registry._tools['video_compose'].get_info()
print('Render engines:', info.get('render_engines'))
print('Remotion note:', info.get('remotion_note'))
print('HyperFrames note:', info.get('hyperframes_note'))
"
```

| 引擎 | 用途 | 需要 |
|--------|----------|--------|
| **FFmpeg** | 纯视频剪辑、拼接、裁剪、字幕烧录 | `ffmpeg` 二进制（始终可用） |
| **Remotion** | 基于 React 的合成：静态图 → 动画视频、文字卡片、统计卡片、图表、标注、对比、带弹簧物理的转场、词级字幕烧录、TalkingHead 虚拟形象 | Node.js（`npx`）+ `remotion-composer/` + `node_modules` |
| **HyperFrames** | HTML/CSS/GSAP 合成：动态文字排版、产品宣传片、发布短片、网站转视频、注册表块驱动场景、SVG 角色绑定 | Node.js ≥ 22 + FFmpeg + `npx`（通过 `npx hyperframes` 使用） |

`render_runtime` 在 **proposal 时锁定**（`proposal_packet.production_plan.render_runtime`）并**原样贯穿 edit_decisions**。`video_compose` 根据该字段路由；静默切换运行时是被禁止的。如果选定的运行时在合成时不可用，按上面的"明确升级阻塞"呈现结构化阻塞。Remotion-vs-HyperFrames 决策矩阵见 `skills/core/hyperframes.md`。

### 关键规则：需要动效的需求

对于任何交付物本质上依赖动效而非静态覆盖的需求，把动效视为硬性要求。示例：

- 科幻预告片，
- 由生成片段构建的电影感宣传片，
- 嗨燃剪辑（hype edits），
- 虚拟形象或 agent 视频，
- 任何其承诺取决于运动镜头而非静态帧的简报。

对这些需求：

- 如果计划的视觉处理依赖 proposal 时选定的 `render_runtime`（Remotion、HyperFrames 或 FFmpeg），必须事先确认其可用。
- **禁止静态图回退。** 不得悄悄把任务降级成 Ken Burns 宣传片、动画分镜（animatic）或幻灯片式视频。
- **禁止 FFmpeg-only 回退**，当它把已批准的交付物从动效主导视频变成静态图主导视频时。
- **禁止静默切换运行时。** 如果锁定了 `render_runtime="hyperframes"` 而 HyperFrames 不可用，**不要**转而使用 Remotion。上报阻塞、提出选项、获得用户批准、记录一条 `render_runtime_selection` 决策——然后再继续。
- 立即上报关键问题。如果选定的运行时不可用、渲染失败，或供应商片段生成失败且阻塞了已批准的处理方案，停下来先告诉用户再继续。
- 除非用户明确批准将输出降级为动画分镜或概念验证，否则不要在降级输出上花费更多 token 或时间。

**当 Remotion 可用时**，agent 应围绕它设计生产方案：
- 带 `flat-motion-graphics` 剧本的解说视频 -> Remotion 动画场景，而不是 Ken Burns
- 数据驱动视频 -> Remotion 统计卡片和图表，而不是静态图片截图
- 任何使用静态图的流水线 -> Remotion 弹簧动画，而不是 FFmpeg 平移缩放
- **CLI/终端/安装流程的屏幕演示 -> `TerminalScene`（合成屏幕录制），而不是操作系统级采集。** 参见 `.agents/skills/synthetic-screen-recording/SKILL.md`。更快、确定性、隐私安全。仅当演示对象是真实应用 UI 或需要不可预测的实时行为时，才使用真实采集（`screen_recorder`、`cap_recorder`、`playwright-recording`）。

### `remotion-composer/` 中可用的 Remotion 场景类型

权威列表及其 cut schema 参见 `remotion-composer/SCENE_TYPES.md`。当前可通过 `cut.type` 使用的场景类型：
`text_card`、`stat_card`、`callout`、`comparison`、`hero_title`、`terminal_scene`、`anime_scene`、`bar_chart`、`line_chart`、`pie_chart`、`kpi_grid`、`progress_bar`。叠加类型包括 `section_title`、`stat_reveal`、`hero_title`、`provider_chip`。

这些现成场景类型是**模板化**路径——快速可靠，但它们正是视频千篇一律的原因。**英雄级作品请优先使用 atelier 模式**（手写合成）而非该目录；把那些类型当作*机制法典*来读，而不是供组装的菜单。参见上面的"合成创作模式"和 `skills/meta/bespoke-composition.md`。

**当 Remotion 不可用**且未锁定 `render_runtime="remotion"` 时，`video_compose` 可以在静态图上使用 FFmpeg Ken Burns 动效。这仍能工作，但视觉吸引力较低。在 proposal 中说明这个权衡。当 `render_runtime="remotion"` **已**锁定而 Remotion 不可用时，那是阻塞——升级上报，不要静默切换。

当 `render_runtime="hyperframes"` 已锁定而 HyperFrames 不可用时（Node < 22、缺少 `ffmpeg`/`npx`，或 `hyperframes doctor` 报告问题），同样也是阻塞。未经用户批准并记录一条 `render_runtime_selection` 决策，不得用 Remotion 或 FFmpeg 替代。

路由是自动的——`video_compose` 读取 `edit_decisions.render_runtime` 并分发给匹配的引擎（`_render_via_hyperframes`、`_remotion_render` 或 `_render_via_ffmpeg`）。但 **agent 在 proposal 时必须知道 Remotion 和 HyperFrames 两者都存在**，才能有意识地设计视觉方案。不要把重动态图形的概念默认丢给 Remotion（HTML/GSAP 表达起来更自然），也不要把复用现有 React 场景栈的简报默认丢给 HyperFrames。

## 能力发现

OpenMontage 用两层来做能力选择：

- 选择器工具（selector tools）：能力级路由，如 `tts_selector` 和 `video_selector`
- 供应商工具（provider tools）：通过注册表发现的、调用特定后端的具体工具

始终先检查注册表：

```bash
python -c "from plugins.openmontage.tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.capability_catalog(), indent=2))"
python -c "from plugins.openmontage.tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_catalog(), indent=2))"
```

对进入候选名单的工具，检查：

- `capability`
- `provider`
- `usage_location`
- `supports`
- `fallback_tools`
- `related_skills`

注册表能回答的问题，不要依赖记忆或旧文档。

## 工具家族

**不要维护硬编码的工具列表。** 始终在运行时查询注册表：

```bash
# 查看按能力分组的全部工具（TTS、video_generation、image_generation 等）
python -c "from plugins.openmontage.tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.capability_catalog(), indent=2))"

# 查看按供应商分组的全部工具（elevenlabs、openai、ffmpeg 等）
python -c "from plugins.openmontage.tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_catalog(), indent=2))"
```

在输出中要查找的关键能力家族：

- **tts** — 文字转语音供应商。通过 `tts_selector` 路由。
- **video_generation** — 视频生成供应商（云、本地 GPU、素材库）。通过 `video_selector` 路由。
- **image_generation** — 图像生成供应商（云、本地 GPU、素材库）。通过 `image_selector` 路由。
- **music_generation** — 音乐与音效生成。
- **video_post** — 合成、拼接、裁剪（基于 FFmpeg，始终本地）。
- **audio_processing** — 混音、增强（基于 FFmpeg，始终本地）。
- **analysis** — 转录、场景检测、抽帧采样。
- **avatar** — 虚拟形象与唇形同步生成。
- **character_animation** — 本地角色规格、SVG 绑定、姿势库、动作时间线、预览与 QA。
- **enhancement** — 超分、背景移除、面部增强、调色。

注册表中的每个工具都声明 `best_for`、`install_instructions`、`runtime`（LOCAL、API、LOCAL_GPU、HYBRID）和 `status`。读取这些字段——不要凭记忆臆断工具优势。

### 工具类命名约定

所有工具类使用**不带 "Tool" 后缀的 PascalCase**。在 Python 中导入工具时：

| 模块 | 类名 | 不是 |
|--------|-----------|-----|
| `plugins.openmontage.tools.audio.music_gen` | `MusicGen` | ~~MusicGenTool~~ |
| `plugins.openmontage.tools.video.video_compose` | `VideoCompose` | ~~VideoComposeTool~~ |
| `plugins.openmontage.tools.audio.audio_mixer` | `AudioMixer` | ~~AudioMixerTool~~ |
| `plugins.openmontage.tools.audio.elevenlabs_tts` | `ElevenLabsTTS` | ~~ElevenLabsTTSTool~~ |
| `plugins.openmontage.tools.analysis.transcriber` | `Transcriber` | ~~TranscriberTool~~ |
| `plugins.openmontage.tools.subtitle.subtitle_gen` | `SubtitleGen` | ~~SubtitleGenTool~~ |

拿不准时，检查：`grep "^class " tools/<path>.py`

所有工具都通过 `.execute(params_dict)` 调用（返回带 `.success`、`.data`、`.error` 的 `ToolResult`），**不是** `.run()`。

调用模式：`registry.get("video_selector").execute({...})` 或 `registry.execute("video_selector", {...})`。
**不要**通过过时路径（如 `plugins.openmontage.tools.tts`）导入供应商模块——使用注册表，或 `grep "^class "` 得到的 `plugins.openmontage.tools.audio.*` / `plugins.openmontage.tools.video.*` 路径。

### 选择器模式

三个选择器工具抽象了多供应商能力。**选择器从注册表自动发现供应商。** 新增一个供应商工具，它会自动通过选择器可用——无需改动选择器代码。

| 选择器 | 路由到 | 如何发现 |
|----------|-----------|-----------------|
| `tts_selector` | 所有 `capability="tts"` 的工具（ElevenLabs、Google TTS、OpenAI、Piper） | `registry.get_by_capability("tts")` |
| `image_selector` | 所有 `capability="image_generation"` 的工具（FLUX、Google Imagen、GPT Image、Recraft 等） | `registry.get_by_capability("image_generation")` |
| `video_selector` | 所有 `capability="video_generation"` 的工具 | `registry.get_by_capability("video_generation")` |

选择器的路由依据：用户偏好 > 可用性 > 发现顺序。它们在供应商之间透明地适配输入 schema。

## 面向用户的规划协议

在承诺执行之前，呈现：

1. 简报仍开放时给出 `4-5` 个概念方向。
2. 推荐的流水线。
3. 推荐的工具路径。
4. 实际可用的备选工具路径。
5. 成本估算与质量权衡。
6. **音乐方案** — 对每个有音频的流水线都是强制的。见下文。
7. 按 stage 的生产计划。
8. 资产生成前的审批门。

如果用户偏好某个特定供应商且该工具可用，直接把它拿出来。不要隐藏供应商选择。

### 音乐方案（强制）

音乐是任何视频的关键部分。**在 proposal/idea 阶段就把音乐情况呈现给用户**——不要静默推迟到资产阶段，那时失败会很昂贵。

按以下顺序检查音乐可用性并呈现选项：

1. **用户音乐库（`music_library/`）：** 检查这个文件夹是否存在并含有音轨。如果有，列出带时长的可用音轨，让用户挑一个。
2. **音乐生成 API：** 通过注册表检查哪些音乐工具可用（`registry.get_by_capability("music_generation")`）。如实报告其状态——知道配额状态就包含在内。
3. **免版权来源：** 提示用户是否可以自己提供音轨（例如来自 YouTube Audio Library、Jamendo 或其他免费来源）。提供 `music_library/` 放置路径。

**始终向用户呈现明确的选项：**
- 使用他们库中的音轨（哪一首？）
- 提供另一条音轨（放进 `music_library/`）
- 通过 API 生成（若可用——说明供应商和成本）
- 无音乐继续

**如果没有任何音乐来源：** 明确告诉用户。绝不让这在资产阶段作为意外浮出水面。

把音乐决策记录在 proposal/brief 资产中，这样资产导演就知道该做什么。

## 流水线资产预期

每个流水线清单的 `tools_available` 字段声明一个 stage 可以使用哪些工具。多供应商能力使用选择器——选择器处理路由到任何可用的东西。每个 stage 的权威列表读流水线清单。

## Stage Agent

每个 stage 产出一个规范资产（canonical artifact），成为下一个 stage 的契约。stage 导演技能教 agent 如何产出它。

| Stage | 导演技能 | 规范输出 | 核心质量底线 |
|------|---------------|------------------|------------------|
| `idea` | `*-director.md` | `brief` | 清晰的钩子、目标平台、时长、语气和用户意图 |
| `script` | `*-director.md` | `script` | 结构化小节、有效时长、连贯旁白 |
| `scene_plan` | `*-director.md` | `scene_plan` | 有序场景、时长、资产需求 |
| `assets` | `*-director.md` | `asset_manifest` | 出处、路径、模型/工具元数据、场景关联 |
| `edit` | `*-director.md` | `edit_decisions` | 具体剪辑、叠加、字幕/音乐决策 |
| `compose` | `*-director.md` | `render_report` | 输出路径、编码配置、验证说明 |

Stage 契约规则：

- `completed` 或 `awaiting_human` 检查点必须包含该 stage 的规范资产。
- 规范资产必须通过 `schemas/artifacts/` 中的 JSON schema 校验。
- 媒体文件等非规范输出属于 stage 专用目录。
- 工具应记录种子/模型版本以保证可复现。

## 评审协议

评审者是一个元技能（`skills/meta/reviewer.md`）——咨询性的，绝不直接阻塞推进。

- 每个 stage 执行后、落检查点之前，自我评审。
- 从流水线清单加载当前 stage 的 `review_focus` 项。
- 最多两轮评审。之后带着警告通过并继续。
- 发现分类：严重（critical，必须修复）、建议（suggestion，应该修复）、吹毛求疵（nitpick，可有可无）。
- 严重发现 -> 修复后重新评审。建议 -> 记录并继续。
- 把剧本（playbook）的 `quality_rules` 当作约束，而不是建议。

## 人工检查点协议

检查点协议元技能（`skills/meta/checkpoint-protocol.md`）教 agent 何时暂停：

- 从流水线清单按 stage 读取 `human_approval_default`。**清单值具有约束力**——绝不重新判定它。`lib/checkpoint.py` 强制执行：受门控的 stage 没有 `human_approved=True` 就不能写成 `completed`。
- 典型的受门控 stage：`idea`/`proposal`、`script`、`scene_plan`、**`assets`**（在 compose 锁定它们之前逐场景评审生成的资产——即 Backlot 看板的胶片条（filmstrip）），以及存在 `publish` 的流水线中的 `publish`。大多数流水线在 `edit` 和 `compose` 上自动推进，但不是全部（documentary-montage 对 `edit` 设门）——你加载的清单是唯一权威。
- 需要批准时：把检查点写成 `awaiting_human`，呈现资产摘要、评审发现和成本快照——然后**结束你的回合**。在同一回复中继续做流水线工作是违反门的。
- **批准是按门生效的。** 早期的"继续吧"永远不覆盖后面的门；明确的整跑预先授权必须记录为 `decision_log` 条目（`category: "approval_policy"`）才算数。
- 等待人类批准、要求修改或中止。

## 通信协议

Agent 通过规范 JSON 资产、检查点、流水线清单和工具注册表协调。

主要文件：

- 资产 schema：`schemas/artifacts/`
- 检查点 schema：`schemas/checkpoints/checkpoint.schema.json`
- 流水线清单 schema：`schemas/pipelines/pipeline_manifest.schema.json`
- 流水线清单：`pipeline_defs/`
- 风格剧本：`styles/*.yaml`（由 `schemas/styles/playbook.schema.json` 校验）
- 工具契约：`tools/base_tool.py`
- 工具注册表：`tools/tool_registry.py`
- Stage 导演技能：`skills/pipelines/<pipeline>/<stage>-director.md`
- 元技能：`skills/meta/*.md`

检查点规则：

- 检查点位于 `projects/<project_id>/checkpoint_<stage>.json`（项目工作区——Backlot 看板监视的正是这个）。
- `status` 可以是 `completed`、`failed`、`awaiting_human` 或 `in_progress`。
- 进入每个 stage 时写入 `in_progress` 检查点；在 `assets`/`compose` 期间，每完成一个场景/资产单元就刷新 `metadata.partial_progress`——这驱动看板上的实时进度。
- `completed` 和 `awaiting_human` 检查点必须包含规范资产。
- 受门控的 stage（`human_approval_default: true`）只能以 `human_approved=True` 写成 `completed`——否则写入器会抛出 GATE VIOLATION。
- 被取代的检查点自动归档到 `projects/<project_id>/history/`——stage 重跑永远不会销毁运行历史。
- 无效检查点或无效规范资产是契约违规，应当快速失败。

流水线清单规则：

- 流水线是 `pipeline_defs/` 中的声明式 YAML 清单。
- Stage 声明：`skill`（导演技能路径）、`produces`、`tools_available`、`review_focus`、`success_criteria`、`human_approval_default`。
- 新增流水线需要清单 + stage 导演技能。

工具规则：

- 每个生产工具都必须继承 `BaseTool`。
- 工具发现走注册表，不走临时导入。
- 支持信封（support-envelope）报告是能力、状态和资源需求的权威来源。

## 风格剧本

| 剧本 | 最适合 |
|----------|----------|
| `clean-professional` | 企业、教育、SaaS |
| `premium-minimalist` | 投资人更新、专家解说、产品叙事 |
| `flat-motion-graphics` | 社交媒体、TikTok、初创公司 |
| `minimalist-diagram` | 技术深挖、架构 |
| `ink-sketch`（Ink Theater） | 手绘墨线白底涂鸦动画；自己画自己、行走、跳舞的角色；装置解说 |

对于定制、atelier、品牌、发布或英雄级作品，在选择剧本前阅读 `skills/meta/taste-direction.md`。把它的 `taste_profile` 带进 proposal，让后续 stage 能保留设计读取、视觉方差、动效强度、信息密度、参考策略和反模式。

### 手绘"涂鸦"动画 → Ink Theater / Ink Puppet

对于任何想要**手绘墨线涂鸦**外观的简报——"活过来的速写"、"会走路或跳舞的铅笔/火柴人"、"把想法演出来的小角色"、白板涂鸦解说——使用 **Ink Theater** 引擎 + **Ink Puppet** 动捕系统（`skills/creative/ink-theater.md`、`ink-theater/README.md`）。它是**一种风格 + 可复用引擎，不是新的流水线**：插画/装置类作品跑在 `animation` 流水线上；动捕角色（自己画自己 → 通过 `InkPuppet.choreograph([...])` 行走 / 跳舞 / 挥手）跑在 `character-animation` 上。跨工具入口：**`/ink-art`**（从零创建矢量涂鸦）和 **`/animated-drawing`**（用动捕动画化*用户提供的*图片——栅格；`skills/creative/animated-drawing.md`）。绝不手工微调角色动效——agent 只选择命名的动捕片段。

## 层级地图（Layer Map）

OpenMontage 有三层指令：

1. `tools/`
   存在什么、什么可用、成本、运行时、回退、相关技能。
2. `skills/`
   OpenMontage 希望这些工具在流水线中如何使用。
3. `.agents/skills/`
   原始供应商或技术知识。

阅读顺序：

1. 注册表 / 工具契约 — 发现有什么可用
2. 相关流水线或创意技能（Layer 2）— 知道在此情境下如何使用
3. 底层供应商技能（Layer 3）— **调用任何生成工具之前强制阅读**

**工具使用优先读技能，而非源码。** 技能的存在正是为了让常见情况下你不需要实现细节。Layer 2 告诉你*做什么*和*何时*。Layer 3 告诉你*怎么做*。编写提示词、选择参数或理解使用模式时，你应该读技能——而不是 `.py` 文件。

**例外：调试、审计和验证治理契约。** 当技能与工具不一致，或行为与技能声称的不同时，读工具源码是合理合法的——这往往是抓住静默可用性 bug 或过时 docstring 的唯一方法。拒绝看实现的审计会漏掉恰恰最重要的那些 bug。如果你确实读源码调试了，考虑这个发现是否应该随后更新到技能里，让下一个 agent 不必重复这次深挖。

**Layer 3 不是可选的。** 每个生成工具（视频、图像、TTS、音乐）都有一个 `agent_skills` 字段列出其 Layer 3 技能。这些技能包含供应商特定的提示词工程、参数调优和质量技巧。写提示词前先读它们。通用提示词与技能提示词之间的差别，就是"可用"与"电影感"之间的差别。

示例：调用 `kling_video` 之前，读它的 `agent_skills` → `ai-video-gen` → 获取 Kling 特定的提示词结构、镜头方向语法以及模型响应最好的质量关键词。

### Layer 3 技能，按类别

`.agents/skills/` 目录很大。当你不是通过工具的 `agent_skills` 指针进来时，用这张表按*你想做什么*找到正确的文件：

| 类别 | 技能 |
|---|---|
| **合成运行时** | `remotion`、`remotion-best-practices`、`synthetic-screen-recording`（通过 Remotion TerminalScene 伪造终端/UI 演示） |
| **动画知识（通用）** | `gsap-core`、`gsap-timeline`、`gsap-plugins`（SplitText / MorphSVG / DrawSVG / MotionPath / Flip / CustomEase）、`gsap-utils`、`gsap-react`、`gsap-performance`、`gsap-scrolltrigger`、`gsap-frameworks`、`framer-motion`（迪士尼 12 原则）、`lottie-bodymovin`（Lottie 导出） |
| **角色动画** | `character-rigging`、`svg-character-animation`、`pose-library-design`、`canvas-procedural-animation`、`character-animation-qa` |
| **图像生成** | `bfl-api`、`flux-best-practices` |
| **视频生成** | `seedance-2-0`（首选高级默认——电影感、预告片、多镜头、同步音频、唇形同步）、`gemini-omni`（对话式视频编辑、参考标签、时码节拍）、`ai-video-gen`、`ltx2` |
| **音频** | `elevenlabs`、`music`、`sound-effects`、`acestep`、`text-to-speech`、`setup-api-key` |
| **语音转文字** | `speech-to-text`（whisper `transcriber` — 默认、离线）、`azure-speech-to-text`（可选云 STT — 工具 `azure_stt`，设置了 `AZURE_SPEECH_KEY` 时首选） |
| **虚拟形象 / 唇形同步** | `avatar-video`、`heygen`、`create-video`、`faceswap`、`video-translate`、`agents` |
| **采集** | `playwright-recording`（浏览器流程）、`ffmpeg`（后期） |
| **可视化** | `beautiful-mermaid`、`d3-viz`、`manim-composer`、`manimce-best-practices`、`manimgl-best-practices` |
| **媒体编辑** | `video-edit`、`video-download`、`video-understand`、`video-toolkit`、`visual-style` |

**拿不准时，先读该类别的元路由文件：**
- 挑选动画运行时？→ `skills/meta/animation-runtime-selector.md` 在 Remotion 原语、GSAP 插件、framer-motion、Lottie、Manim、D3 之间路由。
- 挑选屏幕录制模式（真实采集 vs 合成终端）？→ `pipeline_defs/screen-demo.yaml` + `skills/pipelines/screen-demo/idea-director.md`。

## 快速查阅

| 问题 | 去哪里查 |
|----------|---------------|
| 有哪些工具？ | `tools/tool_registry.py` 和 `registry.support_envelope()` |
| 某个能力有哪些供应商可用？ | `registry.capability_catalog()` |
| 某个厂商有哪些工具？ | `registry.provider_catalog()` |
| 工具实际怎么工作？ | 注册表中工具的 `usage_location` |
| 这个流水线 stage 应该怎么表现？ | `skills/pipelines/<pipeline>/...` |
| 检查点/评审策略是什么？ | `skills/meta/` |

## 什么不该做

- **不要绕过流水线。** 绝不编写临时脚本直接调用工具。所有生产都走带导演技能的流水线 stage。参见零号规则和**流水线绕行禁令（HARD RULE）**。仓库根目录的 `scripts/rerun_*.py` 文件是标记了 `OPENMONTAGE_NON_PRODUCTION_SCRIPT` 的开发/自用工具——agent 不得将其用于生产运行。
- **不读 Layer 3 技能就不要调用生成工具。** 检查工具的 `agent_skills` 字段，阅读引用的技能，然后用该指导编写提示词。
- **不要跳过 stage 导演技能。** 执行任何流水线 stage 之前，先读它的导演技能。技能里包含质量底线、工作流和评审标准。
- 不要使用已删除的旧名称，如 `tts_cloud`、`tts_engine` 或 `video_gen`。
- 不要硬编码供应商名称、API 密钥名称或设置 URL。从注册表的 `install_instructions` 和 `dependencies` 字段读取。
- 生产方案未获用户批准前，不要开始资产生成。
- 不要隐藏降级路径。显式记录替换项和受阻选项。
- 不要孤立地呈现单个不可用工具。始终展示完整能力图景："该能力已配置 X of Y 供应商"。
- 预检时不要跳过供应商菜单。用户必须看到自己拥有什么**以及**可能解锁什么。
- 未经用户同意，不要更换供应商、模型或渲染路径；当变更是实质性的时，必须先告知并获得批准。
