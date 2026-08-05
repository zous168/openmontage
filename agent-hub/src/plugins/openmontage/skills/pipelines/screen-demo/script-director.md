# 脚本导演 —— Screen Demo 管线

## 何时使用

你要把已检视过的录制，变成一份带时间戳的流程型脚本。和 explainer 类工作不同，你不是在发明流程。你是在把语言与观众将会亲眼看到的操作做同步。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/script.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["idea"]["brief"]` | 含工作流、关键时刻与源素材备注的 brief |
| 工具 | `transcriber`、`frame_sampler`、`audio_enhance` | 音频/转写检视与抽查 |

## 流程

### 1. 决定脚本模式

用 brief 的 metadata 从三种模式里选一种：

| 旁白状态 | 策略 |
|-----------------|----------|
| `voiced` | 转写、精简，并尽量保留说话人的原本表达 |
| `silent` | 围绕操作写以文字为主、或可供 TTS 朗读的旁白 |
| `partial` | 转写已有语音，只在必要处做衔接 |

若录制是静音的，且预检时 TTS 不可用，就不要假装后面会有旁白。要把脚本写成即便只有字幕、钩子卡和步骤标签，视频也依然成立。

### 2. 搭建操作图

操作图是本阶段真正的骨架。把 `frame_sampler` 和 `transcriber` 配合使用，记录下：

- 精确的任务边界，
- 值得高亮的点击，
- 值得放慢的输入内容，
- 值得加速或剪掉的等待，
- 需要保持实时速度的那个结果时刻。

把详细的操作信息存进 `script.metadata.interaction_map`。保持 `sections` 干净且符合 schema。

有用的 `interaction_map` 字段：

- `timestamp_seconds`
- `action_type`
- `target`
- `importance`
- `suggested_treatment`（`realtime`、`speed_up`、`cut`、`highlight`、`zoom`）

### 3. 按步骤写 section

每个 `script.sections[]` 条目都应对应一个真实的用户步骤，而不是一段主题性的段落。

好的 section 标签：

- `Open the settings panel`
- `Paste the API token`
- `Run the build`
- `Verify the live result`

每个 section 都要做三件事：

- 说清正在发生什么，
- 说清它为什么重要，
- 为高亮、缩放或变速留下明确提示。

### 4. 让旁白保持流程感

用有研究支撑的规则：

- 讲意图和效果，不讲显而易见的光标移动，
- 措辞简短直接，
- 除非目标受众明确期待，否则避免行话，
- 让屏幕上的操作与措辞保持同步，
- 若源素材已有旁白，就保留说话人本来的语气。

### 5. 标注节奏决策

用 section 级备注和 `metadata.speed_plan` 明确指出：

| 速度系数 | 何时使用 | 示例 |
|-------------|-------------|---------|
| `0.75-1.0x` | 重要的点击或结果 | 小控件、关键的验证时刻 |
| `1.5-2.0x` | 常规输入或导航 | 填写显而易见的字段 |
| `3.0-6.0x` | 安装、构建、加载 | 依赖安装、编译 |
| `cut` | 没有学习价值 | 长时间空等 |

不要把关键的证据时刻放进加速的片段里。

### 6. 用 Metadata 记录屏幕专属细节

推荐的 `script.metadata` 字段：

- `interaction_map`
- `speed_plan`
- `chapter_candidates`
- `pronunciation_guides`
- `callout_candidates`
- `sections_needing_zoom`

### 7. 质量门

| 判据 | 问题 |
|-----------|----------|
| **操作覆盖** | brief 中的每个关键时刻都标了时间戳吗？ |
| **旁白同步** | 每段旁白是否与屏幕上正在发生的事对齐？ |
| **变速标注** | 空白时间段是否被标记为加速或删除？ |
| **强化密度** | 高亮是否只留给真正的注意力转移，而不是每次点击都上？ |
| **技术准确性** | 所有软件名、命令和 UI 元素是否都写对了？ |
| **用词经济** | 旁白是否简洁、有流程感？ |

### 生产中途的事实核验

若你在写脚本过程中遇到不确定：
- 用 `web_search` 在把事实性主张写进脚本之前先核验
- 用 `web_search` 找参考图，保证视觉准确性
- 把核验记入 decision log：`category="visual_accuracy_check"`

脚本中的每一条事实性主张都应能追溯到 `research_brief`。
若你提出了调研中没有的主张，就补做调研并补上来源。
不要杜撰统计数字、日期或出处。

## 常见陷阱

- 解说光标，而不是解说结果。
- 让口播时序偏离了画面上的操作。
- 让构建和加载画面保持实时速度。
- 写了一份静音录制的脚本，却暗地里依赖并不可用的 TTS。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
