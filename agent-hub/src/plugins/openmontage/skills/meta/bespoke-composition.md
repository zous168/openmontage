# 定制合成（Atelier 模式）

用于**从零手工编写 composition** 而非装配现成场景类型的元技能。这是"每一件都手工缝制"的路径：对于旗舰作品，外观的每一个像素都是重新写出来的，因此任何两支视频都不会共用同一套视觉语言。

只要你为某个作品选定了 **atelier 模式**（见"何时使用"），就读本文。它不会直接把组件交给你 —— 它把你导向所需的*原则、引擎机制和工具接线*，让你造出来的东西既正确又与众不同。

> 统摄下文一切的唯一一条规则：**复用引擎知识，绝不复用创意组件。**
> Remotion 如何解析一个素材，属于引擎知识 —— 尽管复用。上一支视频
> 长什么样，属于创意决策 —— 绝不复用。

## 何时使用本技能（编写模式是 proposal 阶段的决策）

OpenMontage 区分三个正交的轴，全部在 proposal 阶段锁定：

- `renderer_family` —— 创意语法
- `render_runtime` —— 技术引擎（remotion / hyperframes / ffmpeg）
- **`composition_mode`** —— **templated**（装配现成 `cut.type` 场景）**vs. atelier**（手工编写）

以下情况默认选 **atelier**：营销、发布、必须惊艳的讲解视频、品牌
作品，以及任何以质量为核心的单件交付物。以下情况选 **templated**：批量
产出、本地化变体、快速草稿、低风险的内部片段 —— 也就是那些可靠的一致性没问题、
而定制成本不划算的场合。在 proposal 阶段把这个选择呈现给用户，并
记入 `decision_log`（`category: "composition_mode"`），方式与呈现运行时相同。

### Atelier 与两个运行时

两个运行时对"定制"的处理方式不同 —— 在假定这套教条能同样映射到两者之前，先读这一段：

- **Remotion** 自带一套由 `Explainer`/`CinematicRenderer` composition 分发的 `cut.type` 现成场景注册表（`text_card`、`stat_card`、`bar_chart`……）。那是 templated 的默认路径。**atelier 模式是逃生通道** —— `composition_mode: "atelier"` 会把渲染路由到 `_render_via_atelier` 并完全绕开注册表，于是 agent 在 `projects/<slug>/` 下手写自己的 React composition。
- **HyperFrames 本质上就是 atelier 的。** HF 里没有 cut-schema —— 每个 composition 都是你手工编写的、带 `data-*` 时序属性和 GSAP 时间线的 `index.html`。它的注册表（`hyperframes add`）是一个 **block** 注册表（颗粒叠加、转场）—— 它是给你的 composition 用的可选输入，而不是一个分发整个渲染的场景目录。**当选定 `render_runtime: "hyperframes"` 时，作品本身就已经是 atelier 风格的；`composition_mode: "atelier"` 是隐含的。** 本技能中的原则（艺术指导、场景独特性、不要用主角组件当骨架、独特性复看）同样适用。渲染走 `hyperframes_compose`（或对手工编写的 composition 直接用 `npx hyperframes render` —— 见第 5 节）。

因此：若 `render_runtime == "remotion"` 且这是旗舰作品，就记一条 `composition_mode: "atelier"` 决策。若 `render_runtime == "hyperframes"`，atelier 就是默认行为，你不需要为它辩护；本技能依然会在你写 composition 之前带你走一遍同样的原则。

一旦 atelier 生效（无论哪个运行时），现成的 Remotion `cut.type` 目录、被当作场景消费（而非当作原始输入）的 `hyperframes-registry` 成品 block、fixture，以及任何预制的创意组件，都是**禁用的** —— 它们是被冻结的外观，会把雷同重新带回来。

## 构建路线

按此顺序编写。每一步都会把你导向已有的知识 —— 不要跳过第一步。

### 1. 为**这个题材**确立一套艺术指导 —— 分化引擎
在写任何组件之前，先定下一套只适合**这个**主题、不适合其他主题的视觉语言。
先读 **`skills/meta/taste-direction.md`** 并写出 `taste_profile`：设计判读、
`visual_variance`、`motion_intensity`、`information_density`、参考策略和
反模式。然后用 **`visual-style`** 这个 Layer 3 技能（CREATE 模式）锁定：配色、字体性格、
运动性格、版式体系，以及**一个**这件作品独有的**标志性装置**。视频之间的差异
在这里就被保证了 —— 不是靠不给你组件，而是靠强制每次都产出一套全新方向。
把它写下来（项目里放一份简短的 `art-direction.md`），然后照着它建造。

问自己：*有什么属于这个题材、而我以前没用过的视觉隐喻？* 若
答案与过去某件作品相似，那说明你还没找到方向。

### 1.5 把每个场景当作它自己的 composition 来规划 —— 不要用主角组件当骨架
最阴险的一种模板化会在*场景*层面偷偷溜回来：挑一个抢眼的
视觉元素（一支蜡烛、一个浏览器边框、一个评分圆环），然后每个场景都复用它、只换下面的
文字。作品显得定制，是因为那个主角是定制的 —— 但每个场景在机制上都是同一个
composition。那是打了品牌的幻灯片，不是影片。**不要那么做。**

你在艺术指导中点名的那个标志性装置，应当只出现在**一个、至多两个
节拍**里 —— 通常是高潮时刻 —— 而不是充当每个场景的视觉骨架。它
靠稀缺来获得分量。

对方案里的每个场景，在*动手写代码之前*给出具体回答：

- **这个场景的主要视觉主体是什么？** 它必须与上一个
  场景*不同*。一个角色。一张图解。一件证物。一片风景。一个排版时刻。那个
  标志性装置。一片虚空。每个场景的主体就是它的职责。
- **这个节拍为什么存在？** 它为故事做了别的节拍做不到的什么事？若你
  能把两个场景合成一个而不损失意义，那就该合。
- **它在视觉上与前后场景有何不同？** 不同的构图（三分法 vs 居中 vs 分屏）。
  不同的尺度（亲密的近景 vs 开阔的远景）。不同的运动
  基调（静止 vs 繁忙）。不同的配色重心。不同的字体处理。
- **如果把标志性装置从这个场景里拿掉，这个场景还成立吗？** 若成立，
  那这个标志性装置多半不属于这个场景 —— 它在那里只是填空。删掉。

Reviewer 会把这一条作为 "scene_distinctness" 检查来强制执行（见
`skills/meta/reviewer.md` → Composition Authoring Mode Review）：需要记录一份
逐场景的 主要主体 + 首帧 清单，并明确回答"是否有任意两个场景
共用了主要视觉主体？"。是 ⇒ CRITICAL ⇒ 重新规划。

推论：这份逐场景方案是一份**一等 artifact**，不是隐含的。在编写 `Composition.tsx` 之前，
把它写下来（写进 `art-direction.md` 或同级的 `scenes.md`）。

### 2. 确定运动语言 —— 用原则，不用预设
去找**原则性**技能，绝不去找成品动画：
- **`framer-motion`** 和 **`lottie-bodymovin`** —— 迪士尼十二法则（预备、舞台调度、
  跟随与重叠、缓入缓出、弧线、时序、夸张、吸引力）。与运行时无关；把这些
  *原则*应用到你自己的 Remotion `spring()`/`interpolate()` 代码里。
- HyperFrames 的 `references/motion-principles.md` —— 缓动即情绪，时序即重量。

### 3. 只有当概念本身需要时，才动用更丰富的词汇

**在 Remotion 上** —— 多数场景用 Remotion 原语即可。只在*创意本身*需要时才升级，不要默认升级：
`gsap-*`（用 SplitText 做动态排版、用 MorphSVG 做形状变形、用 MotionPath 做曲线
运动、用 DrawSVG 做线条绘制、自定义缓动）、`threejs-*`（3D）、`d3-viz`
（数据驱动的自定义图表 —— 手工搭这张图；**不要**直接丢一个现成的
`bar_chart`/`line_chart` 进去）、`manim-*`（数学）、`canvas-procedural-animation`（粒子/天气）。

**在 HyperFrames 上** —— 词汇表位于 `/hyperframes-animation`：36 个以上的原子运动
**规则**（`kinetic-beat-slam`、`3d-text-depth-layers`、`motion-blur-streak`、
`physics-press-reaction`、`multi-phase-camera`、`depth-of-field-blur`……）、15 个以上的场景
**蓝图**（`kinetic-type-beats`、`comparison-split`、`dataviz-countup`、
`constellation-hub`、`ticker-takeover`、`device-surface-showcase`……）、16 个**转场**
家族（`css-distortion`、`css-destruction`、`css-radial`、`css-light`、`css-mechanical`
……），以及同一个 composition 下的 **7 个运行时适配器**：默认 GSAP，外加 Lottie、Three.js、
Anime.js、CSS keyframes、WAAPI 和 TypeGPU（GPU 计算）。招牌能力是
`adapters/html-in-canvas-patterns.md` —— 把实时 HTML/CSS 捕获为 GPU 纹理，再
经由 WebGL/Three.js 渲染，实现电影感的辉光、碎裂、流体、传送门效果。每支视频用它做 1–3
个主镜头节拍，不要每个节拍都用。**每个节拍组合 2–4 条不同的原子规则**，并在
整件作品中**至少使用 3 种不同的缓动** —— 这是烘焙进那份
动画技能里的教条，不是可选的润色。

HF 的创意指导（配色/字体/旁白/节拍规划）读 `/hyperframes-creative`。
HF 的素材（TTS/BGM/SFX/转写/背景移除）读 `/hyperframes-media` 或
`/media-use`。HF 的 CLI 工作流（init/lint/validate/inspect/snapshot/beats/render）读
`/hyperframes-cli`。`/hyperframes` 这个路由技能把这一切串了起来。

### 4. 把引擎机制搞对 —— 陷阱大全
这是唯一一处你需要"复用"的地方：引擎已经解决的问题。这些是关于
框架如何工作的事实，不是外观。

**Remotion 方面**，研读 `.agents/skills/remotion-best-practices`（19 份规则文件：时序、
转场、文字动画、透明视频、字体、音频、序列编排、文本测量）。
你也可以把 `remotion-composer/src/components/` 里的现成组件**当作
机制大全来读 —— 学习惯用法，绝不用来 import 或模仿某种外观。**

**HyperFrames 方面**，composition 契约在 `/hyperframes-core`（`data-*`
时序属性 —— `data-start`、`data-duration`、`data-track-index` —— 外加
强制的 `class="clip"`、`data-composition-id`、`window.__timelines` 注册、以及子
composition 挂载）。每次改动之后都跑 `npx hyperframes lint && npx hyperframes validate`
—— 它们能在渲染之前抓出缺失的根属性、缺失的 clip id、GSAP 目标未解析、tween 重叠
和对比度不达标。用 `npx hyperframes snapshot . --at <times>`
在投入完整渲染之前对各节拍做目视抽查。

如果不知道就会被咬的常见机制：
- **确定性**：不要逐帧使用 `Math.random()` / `Date.now()` —— 用 Remotion 的 `random(seed)` 或
  带种子的辅助函数，否则粒子/缓动会在整段渲染中闪烁。
- **逐场景时长**：`useVideoConfig().durationInFrames` 返回的是 *composition* 长度，不是
  你那个场景的。场景内的时序要由传入的 `durationInFrames`/`Sequence` 驱动，不要用全局值。
- **素材路径**：URL 和 `staticFile()`（public/）到处都能用；但 **`<Audio>` 拒绝 `file://`**
  （只有 `<OffthreadVideo>`/`<Img>` 接受绝对 `file://`）。把音频/视频放进逐项目的
  public 目录，并通过 `staticFile` 引用。照搬 `resolveAsset` 辅助函数的做法。
- **Remotion 里的 GSAP**：使用 `paused` 时间线并调用 `.seek(frame/fps)` —— 绝不要用 `requestAnimationFrame`
  —— 这样帧才能确定性地渲染。
- **字体（Remotion）**：在模块作用域调用一次来自 `@remotion/google-fonts/<Name>` 的 `loadFont()`。
- **HF 的 data-* 契约**：每个带时序的元素都需要 `data-start`、`data-duration`、
  `data-track-index`，**以及** `class="clip"` —— 没有 `clip`，框架就不会管理
  可见性，你的元素会整条时间线都留在画面上。根 `<body>` 需要
  `data-composition-id`、`data-start="0"`、`data-duration`、`data-width`、`data-height`。
  每条时间线都必须是 `gsap.timeline({ paused: true })`，并注册为
  `window.__timelines["<composition-id>"]`。在 clip 和 GSAP 目标上使用稳定的 `id` 属性 ——
  `nth-of-type` 选择器在 validate 阶段很不稳。
- **字幕 vs 屏幕文字 —— 同一内容只选一个角色，绝不两者兼有。** 在动手编写之前，
  每件作品定一次：字幕是在补充口播承载不了的信息（一个数字、一个人名、一句翻译、一处引语出处），
  **还是**在做与旁白重复的无障碍字幕？若你的场景里已经有一行逐字复述脚本的 SerifLine，
  就**不要**再自动生成一条同样文字的字幕 —— 即便场景其余部分很美，
  重复出现的同一句话也会显得业余。要么在 props 里把 `captions=[]` 置空，要么只在
  屏幕文字与口播内容不同的场景上启用字幕。

### 5. 走与运行时相匹配的定制渲染路径
定制 composition 是**用完即弃、项目本地**的 —— 它们绝不进入任何共享注册表。

#### Remotion atelier 路径
- 在 `projects/<slug>/`（已 gitignore）下编写。渲染工具会通过按 mtime 跳过的复制，把你的 `.tsx`/`.ts`
  源码自动暂存到 `remotion-composer/projects/<slug>/`，好让 webpack 能解析
  `node_modules` —— 你的事实来源仍留在 `projects/` 下。
- 用 `python scripts/scaffold_atelier_project.py <slug>` 生成脚手架 —— 它只产出引擎
  管道（entry / Root / 空白的 `Composition.tsx` / `art-direction.md` / props
  模板 / README）。零创意内容；占位画面故意做成一块难看的黑屏，
  这样渲染后的复看就会正确地拒绝把未经编写的脚手架发出去。
- 媒体放在 `projects/<slug>/public/`，并把该路径作为 `bespoke.public_dir` 传入。
- 通过 `video_compose` 的 `operation="render"` 渲染：

```json
edit_decisions = {
  "render_runtime": "remotion",
  "composition_mode": "atelier",
  "bespoke": {
    "entry": "projects/<slug>/index.tsx",
    "composition_id": "<该 entry 的 Root 中注册的 id>",
    "props_path": "<artifacts/props.json 的绝对路径>",
    "public_dir": "<projects/<slug>/public/ 的绝对路径>",
    "art_direction": "<简短说明或 art-direction.md 的路径 —— 必填>",
    "scale": 0.5,          // 0.5 用于快速草稿；出 1080p 成片时去掉
    "crf": 18,             // 锐利的成片
    "concurrency": 8
  }
}
```

atelier 模式下不需要 `asset_manifest` 或 `cuts` —— composition 自己拥有它的素材。
工具的 `_run_atelier_checks` 会在任何源文件从现成注册表
（`src/components`、`src/Explainer` 等）导入时让渲染失败，并在缺少 `art_direction` 时发出警告。

#### HyperFrames 路径
- 用 `npx hyperframes init <slug>` 生成脚手架（在 `projects/` 下运行）。HF init 会生成
  `index.html`、`meta.json`、`package.json`，以及一份逐项目的 `CLAUDE.md`，后者会自动把
  agent 路由进 `/hyperframes` —— 这样下一次会话就确切知道该加载哪些子技能。
- 手写 `index.html`。每个 clip 都需要 `class="clip"` + 三个 `data-*` 时序
  属性 + 一个稳定的 `id`。当单个文件上的时间线超过 4 个 clip 时，通过
  `data-composition-src` 挂载子 composition（lint 会检查这个密度）。
- 音乐驱动的作品，在把音轨放进 `assets/` 之后运行 `npx hyperframes beats .`
  —— 它会产出 `beats/<audio>.json`，逐节拍给出 `{time, strength}`，这样 agent
  就能把场景落在真实的 drop 上（而不是靠猜）。
- 渲染前验证：`npx hyperframes lint . && npx hyperframes validate . && npx hyperframes snapshot . --at <times>`。
  snapshot 是 HF 原生的视觉抽查手段（在选定时间点生成 PNG 帧的接触印样表）——
  用法与 atelier 的 `final_review.visual_spotcheck` 一致。
- **渲染**：`npx hyperframes render . --output renders/<name>.mp4`。
  > 已知缺口（F13）：`hyperframes_compose.render` 目前要求走 templated 路径的
  > `edit_decisions.cuts[]`。对手工编写的 HF composition 它会报错；在该工具长出
  > 定制分支之前，请直接调用 `npx`。

## 防止事与愿违的护栏

- **独特性复看（取代一致性复看）。** 最终渲染之前，问：*这支视频能不能
  是任何别的产品的？它是否复用了我以前做过的某种外观？* 若答案为是，说明艺术指导
  失败了 —— 回到第 1 步。这与"它是否匹配参考"正好相反。
- **不要静默退回现成组件。** "保持简单"适用于*机制*（10 行的 spring 完全没问题），
  绝不适用于*设计*（简单 ≠ 去拿 `text_card`）。若你发现自己正在给一件旗舰作品
  添加现成的 `cut.type`，停下来。
- **成本要如实说。** atelier 比 templated 消耗更多 agent token 和迭代。在 proposal 阶段说明，
  让用户在知情的前提下选择。没有现成基线时质量波动更大 —— 靠上面那些强有力的
  原则技能和独特性复看来缓解，而不是靠把复用重新引进来。
- **检查点节奏。** 遵循 `skills/meta/checkpoint-protocol.md`：在生成素材**之前**先把脚本 + 场景方案
  提交审批，然后是 **assets 门禁**，然后是首次渲染检查点。
  不要抢在签字之前批量生成，并且**不要为了换取 assets 复看而去渲染草稿** ——
  assets 门禁把守在 compose *之前*（见下）。

- **在 assets 门禁处用逐场景静帧填满胶片条。** 一个定制场景的"素材"是
  一个 `.tsx` composition —— 无法生成缩略图 —— 所以在静帧出现之前看板没法显示它。一旦
  composition 能编译，就按场景各渲染一张有代表性帧的静帧到
  `projects/<slug>/snapshots/<scene_id>.png`，这样 assets 门禁的胶片条上显示的就是真实画面，
  而不是 "◆ BESPOKE" 占位符。使用 Remotion 的静帧渲染器（很快 —— 每张一帧），由
  scene_plan 的时序驱动：

  ```bash
  # 每个场景在中点帧（fps * mid_seconds）渲染一张静帧到 snapshots/<scene_id>.png
  npx remotion still projects/<slug>/index.tsx <CompositionId> \
    projects/<slug>/snapshots/<scene_id>.png \
    --frame=<mid_frame> --props=<artifacts/props.json 绝对路径> --public-dir=<public/ 绝对路径>
  ```

  有一个读取 scene_plan 并渲染全部静帧的辅助脚本：
  `scripts/atelier_snapshots.py`（`python scripts/atelier_snapshots.py <slug>`）。然后在
  assets 门禁处**停下**。完整/草稿渲染属于 **compose** 阶段，在获批之后进行。

## 已完成的先例（学*工作流*，不学外观）

两件参考作品 —— 每个运行时各一件 —— 用来研究**流程**，绝不用来学视觉语言：

- **Remotion atelier** —— Phantom Reach 讲解视频（`projects/phantom-reach-explainer/`）：
  用 Playwright 捕获的应用画面加一层 PII 模糊 → 逐句 TTS 用静默节拍拼接 →
  免费的 Pixabay 音乐 → 手工编写的 Remotion 场景（自定义片头、
  评分圆环、agentic 流程图、CTA），配一套一次性的紫罗兰主题。
  Compound Snowball（`projects/compound-snowball/`）和 Library of Alexandria
  （`projects/alexandria-fire/`）是另外两件 —— 三件 Remotion atelier 作品，三套
  完全不同的视觉语言。

- **HyperFrames** —— `in-a-hurry`（`projects/in-a-hurry/`）：一件音乐驱动的动态排版
  作品，用 HF 0.7 新增的 `beats` 命令把场景时序锁定到真实 drop 上。它调用了
  `/hyperframes-animation` 的**五个类别**：`kinetic-beat-slam`、`3d-text-depth-layers`
  （堆叠挤出）、`motion-blur-streak`（残影拖尾）、`transitions/css-distortion`
  （色差 RGB 分离），以及 `adapters/html-in-canvas-patterns`（在一句主打台词上用 Three.js +
  UnrealBloom）。每个节拍使用不同的缓动（`expo.out`、
  `back.out(2)`、`circ.out`、`sine.inOut`）。

**不要复刻它们中任何一件的视觉语言** —— 下一件作品必须与它们
任何一件都不像。这正是全部要义所在。只研究*流程*（决策、顺序、门禁、
验证）。

另见：`skills/meta/animation-runtime-selector.md`（运行时 + 库的路由）、
`AGENT_GUIDE.md` → "Composition Authoring Mode"、`/hyperframes`（HF 路由与
能力地图）。
