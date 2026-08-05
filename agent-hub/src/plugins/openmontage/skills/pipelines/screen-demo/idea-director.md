# 创意导演 —— Screen Demo 管线

## 运行时选择（强制 —— 呈现所有可行的运行时）

在 idea 阶段就与制作模式一并锁定 `render_runtime`。哪些运行时可行取决于模式：

| 制作模式 | 可行运行时 |
|-----------------|-----------------|
| `real_capture`（真实屏幕录制） | `remotion`（首选 —— 录制与叠加层混合）、`ffmpeg`（纯拼接/裁切） |
| `synthetic_terminal`（Remotion `TerminalScene`） | 仅 `remotion` |
| `synthetic_ui`（自定义 HTML UI 演示） | `remotion` 或 `hyperframes` —— 这是真选择，两个都要呈现 |

按 AGENT_GUIDE.md → "Present Both Composition Runtimes (HARD RULE)"：当模式允许多个运行时**且**机器上两者都可用时（检查 `video_compose.get_info()["render_engines"]`），把两者都呈现给用户，配上针对本 brief 的分析，推荐其中一个，然后等待审批。**不要**静默采用默认值。当模式本身限定了选择（例如 `synthetic_terminal` 只能用 Remotion），要明确告诉用户这个约束，而不是静默锁定 remotion。每一次选择都要连同所有考虑过的选项，记录到 `decision_log` 的 `render_runtime_selection` 下。

## 何时使用

只要交付物是屏幕录制风格的演示，就用这条管线。它有**两种制作模式** —— 在 brief 中选定其一：

| 模式 | 源素材 | 何时选它 |
|---|---|---|
| **`real_capture`** | 一段真实的屏幕录制（MP4），由 `screen_recorder`、`cap_recorder` 或 `playwright-recording` 采集 | 真实 app UI、实时行为、浏览器流程、IDE 插件、用户要求录他们自己的屏幕 |
| **`synthetic_terminal`** | 无 —— 什么都不采集。你为 Remotion 编写一个 `terminal_scene` 镜头 | CLI / 终端 / 安装流程 / make 目标 / git clone / API key 配置 —— 任何每条命令和输出都可预测、可脚本化的场景 |

**判定问题：** *"我能在开拍之前预测每条命令及其输出吗？"* 能 → synthetic。不能 → real capture。

**把模式记入 `brief.metadata.production_mode`。** asset-director 会读这个字段，来决定是走「采集 + 叠加层素材」，还是走一份与旁白配速的 `steps` 列表。

对 `synthetic_terminal`，在继续之前还要读 `.agents/skills/synthetic-screen-recording/SKILL.md` —— 它固化了那条节奏规则，正是它此前搞砸过一次样片渲染（命令在 40% 的场景时长里就跑完了，剩下 60% 终端一动不动）。

本阶段你的工作，是把用户的请求变成一份清晰的流程型视频方案。主要交付物是一份符合 schema 的 `brief`，管线专属的细节存放在 `brief.metadata` 中。

## 运作原则

屏幕演示的最佳实践是一致的：

- 流程优先于理论，
- 范围控制在一个工作流或一个结果上，
- 让旁白与可见操作对应，
- 有节制地规划注意力引导，
- 先保可读性，再谈风格。

参考文档：
- `docs/screen-demo-best-practices.md`
- `skills/creative/screen-recording.md`

## 流程

### 1. 检视源素材

在动笔写 brief 之前，先用可用的分析工具：

- `frame_sampler` 取代表性帧，并在可能的关键时刻附近做密集采样
- `scene_detect` 找窗口切换、页面变化和主要版式变化
- `transcriber` 判断录制里是有旁白、只有系统声音，还是完全静音

识别出：

- 出现了哪些软件和界面，
- 正在教的那**一个**工作流，
- 关键交互：点击、输入、滚动、提交、结果，
- 明显需要缩放或高亮辅助的时刻，
- 空白时间：安装、构建、加载、重复打字，
- `9:16` 在不丢失信息的前提下究竟可不可行。

### 2. 给演示分类

选定一种主导原型：

- `tutorial`：一步步完成一项任务
- `feature_showcase`：展示某个功能能做什么
- `troubleshooting`：复现并修复一个问题
- `walkthrough`：讲解跨工具的多步流程
- `comparison`：对比两种做法或两种结果

若素材混合了多种原型，就选那个应当主导节奏与包装的原型。

### 3. 确定交付意图

屏幕演示应当保持窄口径、以结果为导向：

- `30-60s`：快速技巧或功能揭示
- `60-120s`：聚焦的产品走查或 bug 修复
- `120-300s`：分章节的教程

默认取「仍能把任务讲干净」的最短时长。除非用户明确要的是尽量少压缩的培训素材，否则不要保留原始时长。

### 4. 选一个可行的输出形态

围绕可读性来规划平台，而不是围绕潮流压力：

- 密集的桌面 UI 用 `youtube` 或 `linkedin`，
- 只有当活跃区域扛得住窄画幅裁切时，才用 `instagram` 或 `tiktok`，
- 界面有多个面板或代码窗口时，优先 `1:1` 或 `16:9`。

### 5. 搭建 Brief

用 schema 字段写下简洁的创意契约，把更丰富的制作细节存进 `metadata`。

推荐的 `metadata` 键：

- `source_path`
- `source_duration_seconds`
- `source_resolution`
- `has_voiceover`
- `software_shown`
- `demo_archetype`
- `critical_moments`
- `dead_time_segments`
- `recommended_aspect_ratios`
- `notes_for_scene_planner`

Brief 应当回答：

- 观众会学到什么，
- 这是给谁看的，
- 视频最终要落在什么证据/结果上，
- 必须展示的操作有哪些，
- 哪些裁切方向是安全的。

### 6. 质量门

写检查点之前，确认：

- 工作流对选定时长而言足够窄，
- "恍然大悟"的那个结果已被清晰指认，
- 目标平台与 UI 密度相匹配，
- brief 点名了真实的软件，而不是含糊地描述，
- metadata 给了下游阶段足够的制作实况。

## 常见陷阱

- 默认把一段 7 分钟的录制当成 7 分钟的交付物。
- 仅因为用户提了 Shorts，就给密集的桌面录制选 `9:16`。
- 用户真正需要的是把任务做完，你却写了一份概念繁重的 brief。
- 没有标注静音；若没有旁白，下游阶段必须立刻知道。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
