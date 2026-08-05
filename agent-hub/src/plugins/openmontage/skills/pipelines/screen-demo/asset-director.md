# 素材导演 —— Screen Demo 管线

## 何时使用

本阶段产出的是那一小撮「最省力却最见效」的素材，让屏幕演示更容易被跟上：字幕、音频清理、可复用叠加层、遮罩，以及可选的轻量辅助卡片。

## 两种制作模式 —— 生成素材前先选定

**读 brief 的 `production_mode` 字段。** 若 `idea` 阶段没设定，就在这里决定：

| 模式 | 何时 | 素材制作长什么样 |
|---|---|---|
| **`real_capture`** | 真实 app UI（浏览器、设计工具、带插件的 IDE）；实时行为；用户要求录他们自己的屏幕 | 干净音频 + 字幕 + 标注叠加层（箭头、高亮遮罩），叠加在采集到的 MP4 之上 |
| **`synthetic_terminal`** | CLI、终端、安装流程、make 目标、git/npm 命令、`.env` 配置 —— 任何可脚本化的场景 | **完全不做采集。** 为 `video_compose`（Remotion）编写一个 `terminal_scene` 镜头。命令逐字符打出，输出滚动，pill 标签宣告完成。见 `.agents/skills/synthetic-screen-recording/SKILL.md`。 |

**模式选择的经验判据：** *"我能在开拍之前预测每条命令及其输出吗？"* 能 → synthetic。不能 → real capture。

对 synthetic 模式，素材阶段产出的是：
- **旁白（tts_selector）**，对齐到每条命令应当开始输入的确切视频时间
- **一份 `steps` 列表**（cmd/out/pause/pill 原语），与旁白提示配速
- **一次配速校验**，通过 `lib.verify_scene_pacing.assert_alignment(...)` —— 必须在渲染前通过
- **没有**屏幕录制素材、没有标注箭头、没有缩放裁切区域（那些是 real-capture 的概念）

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["idea"]["brief"]` | 要产出什么 |
| 工具 | `subtitle_gen`、`audio_enhance`、`tts_selector`、`image_selector`、`diagram_gen` —— selector 会从注册表自动发现所有可用 provider | 生成能力 |
| Playbook | 当前生效的风格 playbook | 字体排印与叠加层样式 |

## 流程

### 1. 实用优先于装饰

屏幕演示不需要一大堆素材。它需要的是对的那几件：

- 必需：字幕
- 通常必需：清理过的主音频
- 通常有帮助：可复用的高亮框、箭头、步骤标签、模糊遮罩套件
- 可选：一张片头卡、一张片尾卡、稀疏的示意图叠加层
- 仅在预检允许时可选：为静音录制生成的旁白

### 1b. 主场景样片（强制）

在批量生成素材之前：
1. 指认主场景（演示中最重要的那一步或那一次交互）
2. 只为该场景生成**一件**样例素材（字幕样式、高亮叠加层，或片头卡）
3. 呈现它："这是最重要那一步的视觉方向。和你想的一致吗？我会照这个风格把其余的生成出来。"
4. 等审批通过，再进入批量生成

这能避免最昂贵的错误：照着用户不喜欢的方向生成 10 件以上素材。

### 2. 先生成字幕

规则：

- 在未知的 UI 背景上要高对比，
- 绝不遮住观众需要读的文字，
- 优先按短语切块，除非逐词高亮确有实质帮助，
- 把位置覆写备注写进 `asset_manifest.metadata.subtitle_zones`。

### 3. 搭一套可复用的叠加层套件

不要为每一次点击都生成定制素材。搭一套小的共享套件：

- `highlight_box_primary`
- `arrow_primary`
- `step_label_primary`
- `keystroke_badge_primary`
- `blur_mask_template`

这些应当能跨场景复用，时序与摆放交给下游处理。

### 4. 务实地清理或生成音频

目标：

- 去掉扰人的键盘声和房间噪声，
- 让语音响度归一，
- 保住时序，
- 不要处理过度，弄成机器音。

若录制是静音的：

- 只有当 TTS 通过了预检，才生成旁白，
- 否则就让素材方案以文字为主，并在 metadata 中注明这个限制。

### 5. 只有当补充视觉物「配得上」时才生成

只在以下情形使用 `image_selector` 或 `diagram_gen`：

- 一张简短的开场卡，
- 一张步骤转场卡，
- 一张能澄清隐藏流程的简单示意图，
- 一张片尾卡。

不要为一个屏幕本身已经解释清楚的工作流去造装饰性美术。

### 6. 把素材清单搭干净

每件素材都必须有合法的 schema 类型和 `scene_id`。

用 `asset_manifest.metadata` 记录细节，例如：

- `subtitle_zones`
- `overlay_kit`
- `audio_settings`
- `narration_mode`
- `sensitive_regions`

### 7. 质量门

**存在性检查：**
- [ ] 字幕文件在声明路径上存在，且解析无错
- [ ] 清理后的音频文件存在，时长符合预期
- [ ] 可复用叠加层套件存在，且覆盖了规划中的标注类型
- [ ] 所有补充视觉物都在声明路径上存在

**时序检查：**
- [ ] 字幕时间戳与脚本 section 的时间戳对齐
- [ ] 若生成了旁白，其时序与 section 时长足够接近，可供剪辑使用

**质量检查：**
- [ ] 字幕在输出分辨率下可读
- [ ] 清理后的音频不再有扰人噪声
- [ ] 标注颜色对比度足够
- [ ] 模糊遮罩完整覆盖了敏感内容

### 生产中途的事实核验

若你在生成素材过程中遇到不确定：
- 用 `web_search` 核验主体的视觉准确性（例如：这栋建筑实际长什么样？）
- 在生成插画之前，用 `web_search` 找参考图
- 把核验记入 decision log：`category="visual_accuracy_check"`

视觉准确性很重要。若脚本提到了某个具体地点、人物或物件，
就在生成图像之前先核实它实际长什么样。不要依赖
AI 模型的训练数据 —— 它可能是错的或过时的。

## 常见陷阱

- 生成一大堆一次性叠加层文件，而不是做一套可复用套件。
- 字幕直接压在终端输出或底部导航栏上。
- 想当然地以为静音录制会凭空长出旁白，却不去检查 TTS。
- 把图像生成预算花在原始画面已经提供了的视觉物上。


## 当你不知道该怎么做时

若你遇到某种拿不准的生成技法、provider 行为或提示词模式：

1. **上网搜索**当前最佳实践 —— 模型和 API 变化频繁，agent 的训练数据可能已过时
2. **查 `.agents/skills/`** 里已有的 Layer 3 知识（provider 专属提示词指南、API 模式）
3. **若两者都无解**，就在 `projects/<project-name>/skills/<name>.md` 写一份项目级技能，记录你学到的东西
4. **在技能中引用来源 URL**，让知识可追溯
5. **记录它**到 decision log：`category: "capability_extension"`、`subject: "learned technique: <name>"`

以下情形尤其重要：
- **视频生成提示词** —— 模型对特定词汇有反应，而这些词汇每个版本都在变
- **图像模型参数** —— FLUX、GPT Image、Imagen 的最优设置各不相同，且在演进
- **音频 provider 的怪癖** —— 声音克隆、音乐生成和 TTS 各有其模型专属的最佳实践
- **Remotion 组件模式** —— 随着框架演进，会出现新的合成技法

不要依赖陈旧知识。拿不准时，先搜索。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
