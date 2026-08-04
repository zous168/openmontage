# 动画运行时选择器

回答两个问题的元技能：

1. **这支视频该用哪个合成运行时？** —— Remotion、HyperFrames 还是 FFmpeg。
2. **这个场景该用哪个动画库 / Layer 3 技能？** —— Remotion 原语、GSAP 插件、framer-motion、Lottie、Manim、D3。

在编写任何动画组件或 composition 之前读本文，以及在 proposal 阶段选定 `render_runtime` 时读本文。它会把你导向正确的 Layer 3 技能，省得你手搓一个插件早就解决了的东西。

> **编写模式优先。** 在决定运行时或库之前，先确定 composition *如何*
> 构建：**templated**（装配现成的 `cut.type` 场景）还是 **atelier**（从零手工编写）。
> 旗舰作品默认走 atelier，并遵循 `skills/meta/bespoke-composition.md`。
> 下面的路由在两种模式下都适用 —— 但在 atelier 模式下，现成的场景类型和
> registry block 是禁用的；你要自己写。"有没有现成的 cut-type 能凑合？"对旗舰作品**不是**
> 一条正当的捷径。见 `AGENT_GUIDE.md` → "Composition Authoring Mode"。

## 何时使用本技能

以下情况适用：
- **Proposal 阶段**需要锁定 `render_runtime`（remotion / hyperframes / ffmpeg）
- 某个阶段导演（asset、edit、compose）需要编写动画组件
- agent 即将为一个涉及文字揭示、SVG 运动、曲线镜头路径、形状变形或多阶段编排的场景编写 Remotion JSX
- agent 被要求构建一个 HyperFrames composition
- agent 不确定该用 GSAP 插件还是内联的 `interpolate()`/`spring()`

## 运行时选择（Remotion vs HyperFrames vs FFmpeg）

OpenMontage 把创意语法（`renderer_family`）与技术
引擎（`render_runtime`）分开。两者都在 proposal 阶段锁定，并原封不动地贯穿
`edit_decisions`。在 compose 阶段静默切换运行时属于
违反契约。

### 硬规则 —— 呈现两个运行时，不要静默取默认值

当本机上 Remotion **和** HyperFrames 都可用时（检查
`video_compose.get_info()["render_engines"]`），agent **必须**在锁定
`render_runtime` 之前把两个选项都呈现给用户。下面的决策矩阵
是 agent 与用户对话的**输入**，**不是**静默取
"默认"那一行的许可证。完整契约见 `AGENT_GUIDE.md` → "Present Both Composition
Runtimes"。

具体地，在 proposal 阶段：

1. 查询 `video_compose.get_info()["render_engines"]`，看这台机器上
   有哪些运行时可用。
2. 若 Remotion 和 HyperFrames 都可用，把两者都呈现给
   用户，附上：贴合本次 brief 的一句话描述、一句
   如实的权衡、以及 agent 的推荐及理由。
3. 等待用户明确审批。
4. 把决策记入 `decision_log`，category 为
   `render_runtime_selection`，`options_considered` 里包含两个运行时。
5. 然后才把 `render_runtime` 写进 `proposal_packet.production_plan`。

若两个运行时都可用，而 `render_runtime_selection` 决策里只考虑了
一个选项，这是 CRITICAL 级的 reviewer 发现。

| Brief 特征 | `render_runtime` | 阅读 |
|---|---|---|
| 现有的 React 场景栈（text_card、stat_card、图表、字幕叠加、TalkingHead、CinematicRenderer） | **remotion** | `skills/core/remotion.md` |
| 词级字幕烧录 / 卡拉 OK 式字幕 | **remotion** | `skills/core/remotion.md` |
| 数字人 / 唇形同步 / 出镜主持 | **remotion** | `skills/core/remotion.md` |
| 动态排版、HTML/GSAP 原生运动、产品宣传片、发布短片 | **hyperframes** | `skills/core/hyperframes.md` + `.agents/skills/hyperframes/SKILL.md`（路由）→ `hyperframes-core`（契约）、`hyperframes-creative`（配色/字体）、`hyperframes-animation`（运动） |
| 网页 → 视频、UI 驱动的合成 | **hyperframes** | `.agents/skills/website-to-video/SKILL.md`（0.7 中由 website-to-hyperframes 改名） |
| 需要 registry block（data-chart、grain-overlay、shader 转场等） | **hyperframes** | `.agents/skills/hyperframes-registry/SKILL.md` |
| 节拍同步的音乐视频（音频驱动场景时序） | **hyperframes** | `.agents/skills/music-to-video/SKILL.md` —— 用 `hyperframes beats` 检测 drop，把画面排布到节拍网格上 |
| 把现有 Remotion composition 移植到 HyperFrames | **hyperframes** | `.agents/skills/remotion-to-hyperframes/SKILL.md` —— 迁移指引，**仅**用于明确的移植请求 |
| BGM / SFX / 图像 / 图标的解析（任意管线、任意运行时） | 不适用 | `.agents/skills/media-use/SKILL.md` —— 针对 项目缓存 + 全局缓存 + HeyGen 目录 的 `resolve` 动词 |
| 短小的设计主导动态图形（下三分之一条、数据揭示、Logo 音效动画、大标题） | **hyperframes** | `.agents/skills/motion-graphics/SKILL.md` |
| 纯粹的源片段拼接/修剪，不需要合成 | **ffmpeg** | `skills/core/ffmpeg.md` |
| 选定的运行时不可用 | **上报** —— 不要静默替换 | `AGENT_GUIDE.md` → Escalate Blockers |

完整的 Remotion 与 HyperFrames 决策矩阵，以及 Phase 1 中仍然只走 Remotion 的
功能清单，见 `skills/core/hyperframes.md`。

## 动画库决策矩阵

| 动画需求 | 推荐运行时 | 先读 |
|---|---|---|
| 简单的淡入 / 滑动 / 缩放 / 弹簧 | Remotion 原语（不用插件） | `.agents/skills/remotion` |
| 带物理的双状态弹簧 | Remotion `spring()` | `.agents/skills/remotion` |
| 带偏移量的多步序列 | Remotion `Sequence` + `interpolate()` **或** GSAP 时间线 | `.agents/skills/remotion` + 可选 `.agents/skills/gsap-timeline` |
| 与旁白同步的逐词文字揭示 | 由词级转写稿驱动的 Remotion `interpolate`（现有的 `CaptionOverlay` 范式） | `.agents/skills/remotion` |
| 逐字符的动态排版（SplitText 风格） | 在 Remotion 内使用 GSAP SplitText | `.agents/skills/gsap-plugins`（SplitText）、`.agents/skills/gsap-react` |
| 两条路径之间的 SVG 形状变形 | 在 Remotion 内使用 GSAP MorphSVG | `.agents/skills/gsap-plugins`（MorphSVG） |
| 沿自定义路径的曲线镜头 / 物体运动 | 在 Remotion 内使用 GSAP MotionPath | `.agents/skills/gsap-plugins`（MotionPath） |
| SVG 线条绘制 / 描边显现 | GSAP DrawSVG | `.agents/skills/gsap-plugins`（DrawSVG） |
| 定制的贝塞尔 / 弹性 / 顿挫缓动 | GSAP CustomEase / EasePack / CustomWiggle | `.agents/skills/gsap-plugins` |
| 版式到版式的过渡（FLIP） | 在 Remotion 内使用 GSAP Flip | `.agents/skills/gsap-plugins`（Flip） |
| 用于 UI 运动的迪士尼十二动画法则 | framer-motion + Lottie | `.agents/skills/framer-motion`、`.agents/skills/lottie-bodymovin` |
| 从 After Effects / Figma 导出 Lottie | Lottie | `.agents/skills/lottie-bodymovin` |
| 合成终端 / CLI 演示 | Remotion TerminalScene | `.agents/skills/synthetic-screen-recording` |
| 数学 / 科学可视化 | Manim | `.agents/skills/manim-composer`、`.agents/skills/manimce-best-practices` |
| D3 数据驱动可视化 | D3 | `.agents/skills/d3-viz` |
| 数据图表（柱状/折线/饼图/KPI） | Remotion 内置图表组件 | `remotion-composer/SCENE_TYPES.md` |
| HyperFrames composition —— 动画知识（规则、蓝图、转场、运行时适配器） | HyperFrames + 默认 GSAP | `.agents/skills/hyperframes-animation`（整合后的运动技能）+ `.agents/skills/gsap-core`、`.agents/skills/gsap-timeline` |
| HyperFrames composition 结构（data-* 时序、tracks、子 composition） | HyperFrames | `.agents/skills/hyperframes-core` |
| HyperFrames 创意指导（配色、字体、旁白、节拍规划） | HyperFrames | `.agents/skills/hyperframes-creative` |
| HyperFrames 音频/媒体（TTS、BGM、SFX、转写、字幕、背景移除） | HyperFrames | `.agents/skills/hyperframes-media` |
| HyperFrames composition 的 CLI 工作（lint/validate/inspect/snapshot/benchmark/render/lambda） | HyperFrames CLI 0.7+ | `.agents/skills/hyperframes-cli` |
| HyperFrames registry block 安装（`hyperframes add ...`） | HyperFrames registry | `.agents/skills/hyperframes-registry` |

## "保持简单"的倾向

在动手用 GSAP 之前，先问：**Remotion 的原语 API 能不能用 20 行以内解决这个问题？**

- 淡入/滑动/缩放/旋转 → `interpolate(frame, [inFrame, outFrame], [from, to])`
- 自然的"弹跳"运动 → `spring({ frame, fps, config: { damping, stiffness } })`
- 词级字幕高亮 → 遍历转写稿，按 `frame / fps` 过滤

如果能，就用 Remotion 原语。如果不能，那才是升级到 GSAP 插件的信号。

GSAP 是强力的逃生通道，不是默认项。每引入一个插件都会增加打包体积、注册样板代码，以及又一份要读的技能文档。

## 在 Remotion 内确定性地运行 GSAP

标准的 GSAP 跑在 `requestAnimationFrame` 上 —— 不确定，开箱也不兼容 Remotion。以下三种范式**是** Remotion 安全的：

```jsx
// 范式 1：暂停的时间线，按进度 seek
const tl = useRef(gsap.timeline({ paused: true })).current;
useEffect(() => {
  tl.to('.x', { x: 500 }).to('.y', { opacity: 0 });
}, []);
tl.progress(frame / durationInFrames);

// 范式 2：暂停的时间线，按时间 seek
tl.seek(frame / fps);

// 范式 3：只把 GSAP 当作数值计算器
const easeFn = gsap.parseEase('power2.out');
const t = frame / durationInFrames;
const easedValue = easeFn(t);
```

完整拆解请读 `.agents/skills/gsap-react/SKILL.md`。

## 与管线的阶段导演对照

每条管线的 asset-director 都有动画方面的专门指导。如果你正在：
- **animated-explainer** → 读 `skills/pipelines/explainer/asset-director.md` —— 它给出了动态排版的文字/SVG 选项
- **animation** → 读 `skills/pipelines/animation/asset-director.md` —— 它给出了 Logo/动态图形工作中的 MorphSVG 与 MotionPath
- **cinematic** → 读 `skills/pipelines/cinematic/asset-director.md` —— 它给出了电影感镜头运动中的 MotionPath

asset-director 告诉你在这条管线的语境下*要做什么*。本选择器告诉你*怎么做*。

## 绝不要做

- ❌ 在只需要淡入/滑动的场景里引入 GSAP —— 用 Remotion 原语。
- ❌ 在 Remotion 内让 GSAP 跑 `requestAnimationFrame` —— 渲染会变得不确定。
- ❌ 在已经指明要用某个插件时跳过对应的 Layer 3 技能 —— 逐插件的用法指导很重要。
- ❌ 在组件函数体内注册 GSAP 插件 —— 在模块作用域或应用入口处注册一次。
