# HyperFrames 技能（Layer 2）

这是 HyperFrames 的 **OpenMontage 专属**指南。它讲清楚 OpenMontage
管线在什么情况下应该选 HyperFrames 而不是 Remotion、OpenMontage
artifact 如何映射到 HyperFrames 项目文件，以及 compose 阶段如何驱动
HyperFrames CLI。

关于 HyperFrames 本身的原始知识（编写契约、`data-*` 属性、GSAP
时间线规则、CLI 参数、registry blocks、website-to-video），请阅读 Layer 3
技能：

- `.agents/skills/hyperframes/` —— 通往下列细分技能的路由（HF 0.7+ 把原来的单体技能拆分了）
- `.agents/skills/hyperframes-core/` —— composition 契约：`data-*` 时序、tracks、子 composition、确定性渲染规则
- `.agents/skills/hyperframes-creative/` —— 非动画类创意指导：配色、字体、旁白、节拍规划
- `.agents/skills/hyperframes-media/` —— TTS/BGM/SFX/转写/字幕/背景移除
- `.agents/skills/hyperframes-animation/` —— 全部运动知识（规则、蓝图、转场、运行时适配器）
- `.agents/skills/hyperframes-cli/` —— init、add、lint、validate、inspect、snapshot、preview、render、benchmark、lambda、doctor（0.7+）
- `.agents/skills/hyperframes-registry/` —— `hyperframes add` + block 接线
- `.agents/skills/website-to-video/` —— 捕获转视频工作流（0.7 中由 website-to-video 改名而来）
- `.agents/skills/music-to-video/` —— 用 `hyperframes beats` 做节拍同步的音乐驱动视频
- `.agents/skills/motion-graphics/` —— 短小的、设计主导的动态图形范式
- `.agents/skills/media-use/` —— 用于 BGM/SFX/图像/图标的 `resolve` 动词（适用于任意管线、任意运行时）
- `.agents/skills/remotion-to-hyperframes/` —— **仅当**用户明确要求移植某个 Remotion 源码时才使用的迁移指南

本文件教的是两者之间的桥梁。

---

## OpenMontage 何时应该选 HyperFrames（对比 Remotion 与 FFmpeg）

OpenMontage 区分两个概念：

- **`renderer_family`** —— 创意语法（`explainer-data`、
  `cinematic-trailer`、`product-reveal` 等）。在 proposal 阶段选定。
- **`render_runtime`** —— 实现该语法的技术引擎
  （`remotion`、`hyperframes`、`ffmpeg`）。同样在 proposal 阶段选定。

两者都锁定在 `proposal_packet.schema.json` 中，并原封不动地贯穿
`edit_decisions`，除非在 `decision_log` 中记录了 `render_runtime_selection`
决策。静默切换运行时属于违反契约。

### 决策矩阵

| 场景 | 优先选 | 理由 |
|----------|--------|-----|
| 已有的讲解视频、React 场景组件栈（text_card、stat_card、图表场景、字幕叠加、TalkingHead、CinematicRenderer） | **Remotion** | 这些 composition 已经存在于 `remotion-composer/` 中。复用它们是免费的；用 HTML 重做一遍不是。 |
| 词级字幕烧录 / 卡拉 OK 式字幕 | **Remotion** | `remotion_caption_burn` 是 Remotion 专属的，HyperFrames 在第一天并不具备对等能力。 |
| 数字人 / 唇形同步主持人 | **Remotion** | `TalkingHead` composition 位于 Remotion。HyperFrames 目前还没有等价物。 |
| 动态排版、大量文字运动、GSAP 原生动画 | **HyperFrames** | HTML/GSAP 就是这类内容的天然媒介。把它表达成 Remotion 的 `interpolate()` 调用既慢又脆弱。 |
| 产品宣传片 / 发布短片 / 营销标题卡 | **HyperFrames** | CSS/GSAP 的合成语法契合设计师思考这类内容的方式。模板（`kinetic-type`、`product-promo`、`swiss-grid`）提供了扎实的起点。 |
| Website-to-video / UI 驱动的合成 | **HyperFrames** | `website-to-video` 工作流正是为此而生。 |
| 需要 registry block（数据图表、颗粒叠加、微光扫过、shader 转场） | **HyperFrames** | registry 是 HyperFrames 独有的。Remotion 没有 `hyperframes add`。 |
| 合成 UI / 伪终端 / 伪浏览器演示 | 都可以 —— 取决于现有覆盖情况 | OpenMontage 已经内置了 Remotion `TerminalScene`（见 Layer 3 的 `synthetic-screen-recording`）。若需要终端以外的 UI 外壳，HyperFrames 的 HTML 更省事。 |
| 纯粹的源片段拼接/修剪，不做合成 | **FFmpeg** | Remotion 和 HyperFrames 在这里都不产生价值。 |
| 本机未安装 Remotion | **HyperFrames**（若可用）或 **FFmpeg** | 不要静默降级。降级前先告知用户。 |

### 硬规则：两个运行时都可用时必须都呈现给用户

上面的决策矩阵是与用户对话的**输入**，**不是**静默选取某个"默认值"的
许可证。当本机上 Remotion 与 HyperFrames 都可用时，proposal 阶段
**必须**：

1. 结合本次 brief 的具体情况，把两者的优劣都呈现给用户。
2. 推荐其中一个，并给出与 `delivery_promise` 和
   `visual_approach` 挂钩的理由。
3. 等待用户审批。
4. 把两者都记入 `render_runtime_selection` 决策的
   `options_considered`。

完整契约见 `AGENT_GUIDE.md` → "Present Both Composition Runtimes (HARD RULE)"，
CRITICAL 级发现的执行方式见 `skills/meta/reviewer.md`。

### 硬规则：以运动为必要条件的交付物

若 brief 的 `delivery_promise.motion_required` 为 `true`（科幻预告片、
电影感先导片、燃向剪辑，以及任何承诺依赖真实运动的 brief），
那么 proposal 阶段选定的运行时就是一项**承诺**，而不是提示。compose
**不得**降级为 FFmpeg 的 Ken Burns。若选定的运行时失败（Remotion
未安装、`npx hyperframes doctor` 报告阻塞项），按
`AGENT_GUIDE.md` > "Escalate Blockers Explicitly" 上报该阻塞，并在切换运行时前
等待用户审批。

---

## 哪些内容在 Phase 1 仍然只走 Remotion

第一天**不要**尝试把这些移植到 HyperFrames。它们需要
专门的对等能力建设：

- `remotion_caption_burn`（逐词烧录字幕）
- `TalkingHead` composition（数字人/唇形同步主持人）
- 现有的 documentary-montage 片尾标签叠加栈（依赖特定的
  Remotion 组件）
- 任何假定素材被暂存于 `remotion-composer/public/`
  并由现有 React 场景组件消费的内容

对于这些，保持 `render_runtime = "remotion"` 并照现状推进。

---

## 项目工作区布局

HyperFrames 需要自己的项目工作区。**不要**复用
`remotion-composer/public/` —— 那是 Remotion 的共享暂存目录，
在那里混用运行时会造成跨项目冲突。

```
projects/<project-name>/
├── artifacts/
├── assets/
│   ├── images/
│   ├── video/
│   ├── audio/
│   └── music/
├── hyperframes/                ← HyperFrames 运行时工作区（选用时才有）
│   ├── index.html              ← 根 composition
│   ├── compositions/           ← 子 composition 与 registry blocks
│   │   └── components/         ← registry 组件（颗粒叠加等）
│   ├── assets/                 ← 项目素材的符号链接或副本
│   ├── hyperframes.json        ← CLI 配置（registry URL、安装路径）
│   ├── DESIGN.md               ← 由 playbook 派生的视觉 brief（可选）
│   └── narration.wav           ← TTS 输出（适用时）
└── renders/
    └── final.mp4
```

该工作区在 compose 时由 `hyperframes_compose` 依据
`edit_decisions` + `asset_manifest` + 当前生效的 playbook 生成。它是可重新生成的，
并与 `projects/` 的其余部分一起被 gitignore。

### 为什么每个项目要有独立工作区

- HyperFrames 解析 `data-composition-src`、`src=` 和 registry blocks
  时是相对项目根目录的。共享工作区会破坏这一点。
- `npx hyperframes lint | validate | render` 全部作用于一个项目
  目录。它们不像 Remotion 那样接受抽象的 composition ID。
- 素材与引用它们的 HTML 放在一起，与
  `website-to-video` 参考工作流保持一致。

---

## Artifact → HyperFrames 映射

当 `render_runtime = "hyperframes"` 时，compose 阶段把
OpenMontage artifact 翻译成 HyperFrames 项目文件：

| OpenMontage artifact 字段 | HyperFrames 目标 |
|---|---|
| `edit_decisions.cuts[]`（场景序列） | `index.html` 时间线，每个 cut 对应一个 `<div data-composition-id data-composition-src>` |
| `edit_decisions.cuts[i].in_seconds / out_seconds` | 片段元素上的 `data-start` / `data-duration` |
| `edit_decisions.cuts[i].type`（场景种类） | 通过 `hyperframes add` 安装的 registry block，或手工编写的子 composition 模板 |
| `asset_manifest.assets[]` 路径 | 复制或符号链接到 `projects/<p>/hyperframes/assets/`，并用相对 `src=` 引用 |
| `audio.narration.segments[]` | 带对应 `data-start` / `data-duration` 的 `<audio>` 元素 |
| `audio.music` | 第二个 `<audio>` 元素，`data-volume` 更低 |
| `subtitles`（启用 + 来源） | 要么用 registry 的 `captions` block，要么手写逐词 span —— **不是** `remotion_caption_burn` |
| 选定的 playbook（`flat-motion-graphics`、`clean-professional` 等） | `:root` 上的 CSS 自定义属性 + `DESIGN.md`。见 `lib/hyperframes_style_bridge.py`。 |
| `renderer_family` | 决定使用哪个顶层 HTML 模板，以及预装哪些 registry blocks |

具体的渲染过程是：`hyperframes_compose` 把文件写入
工作区，依次运行 `lint → validate → render`，并返回一份 `render_report`，
其中含生成的 MP4 路径。见 `tools/video/hyperframes_compose.py`。

### 工作区内的编写辅助文件

上游的 `website-to-video` 技能把 `DESIGN.md`、`SCRIPT.md` 和
`STORYBOARD.md` 当作逐步推进的工作区文件。OpenMontage **不会**
用这些文件替换自己的规范 artifact 契约 —— `brief`、`script`、
`scene_plan`、`edit_decisions` 等仍然是位于
`projects/<p>/artifacts/` 下的事实来源。把上游那些文件当作写进
HyperFrames 工作区的**便利副本**，让运行时工作流用起来更顺手：

- `DESIGN.md` —— 由选定的 playbook 派生，由
  `hyperframes_compose` 或 `lib/hyperframes_style_bridge.py` 写出。可以放心地当作
  工作区内的工作 brief 使用。
- `SCRIPT.md` —— 供人工复看的可选旁白文案。规范脚本
  仍在 `artifacts/script.json`。
- `STORYBOARD.md` —— 可选的逐节拍创意指导。规范的场景
  规划仍在 `artifacts/scene_plan.json`。

若工作区内的文件与规范 artifact 冲突，以规范
artifact 为准。

---

## 运行时选择规则

1. **Proposal 阶段**选定 `render_runtime`，并以 `render_runtime_selection`
   为 category 把决策记入 `decision_log`。它必须同时考虑
   上面的决策矩阵与各运行时的实际可用性。
2. **Preflight** 报告哪些运行时可用（见下文）。不可用的
   运行时不构成合法的 proposal 选项，除非
   用户明确同意去安装它。
3. **Edit 阶段**原封不动地把 `render_runtime` 往下传。
4. **Compose 阶段**读取 `edit_decisions.render_runtime`，并经由
   `video_compose` → `hyperframes_compose`（HyperFrames）或既有的
   Remotion 路径（Remotion）进行路由。没有新的
   `render_runtime_selection` 决策，compose 不得切换运行时。
5. **最终复查**记录 `render_runtime_used`，若与 proposal 不一致则把
   `runtime_swap_detected` 设为 `true`。

---

## Preflight —— HyperFrames 可用性

在 preflight 阶段，provider 菜单会报告 HyperFrames 的可用性。
`hyperframes_compose` 工具的 `get_info()` 返回：

```json
{
  "runtime_available": true | false,
  "node_major": 22,
  "ffmpeg_available": true,
  "doctor_ok": true,
  "install_instructions": "…"
}
```

底线要求（全部满足才有 `runtime_available: true`）：

- Node.js 主版本号 ≥ 22
- PATH 中有 `ffmpeg` 二进制
- PATH 中有 `npx`（随 Node.js 一起提供）
- `npx hyperframes doctor` 退出码为 0，或某个等价的轻量检查通过

**不**需要 `bun` —— HyperFrames 可通过 `npx hyperframes` 使用（发布到 npm 的包名是 `hyperframes`；monorepo 内部的 `@hyperframes/cli` 名称并不在公共 npm registry 上，访问会返回 404）。

当 `runtime_available: false` 时，preflight 必须把原因和
安装说明呈现出来。按 `AGENT_GUIDE.md` 的 Setup Offer Protocol，按
所需工作量分组：

- 缺 Node 22 → 5 分钟安装，说明它能解锁什么
- 缺 FFmpeg → macOS/Linux 上 1 分钟安装，Windows 上耗时更长
- `doctor` 报告问题 → 原样展示 doctor 的输出

---

## 校验协议

HyperFrames 自带一套真正的校验栈。在宣布渲染完成之前，**全部**
运行以下步骤：

1. **`npx hyperframes lint`** —— 静态契约检查（重复 id、
   轨道重叠、缺少 `data-composition-id`、未注册的时间线）。
   渲染前必须通过。
2. **`npx hyperframes validate`** —— 基于浏览器的运行时检查：seek 到
   暂停的 composition、截图、采样像素、计算 WCAG
   对比度、验证 `window.__timelines` 注册情况以及计时元素上的
   `class="clip"`。渲染前必须通过（迭代过程中可用 `--no-contrast`
   暂缓对比度检查，但最终成片不行）。
3. **`npx hyperframes render --quality standard`** —— 产出 MP4。
4. **渲染后最终复查** —— 用 ffprobe 探测、抽帧、
   转写音频、与脚本比对。与 Remotion 路径同一套契约。
   见 `final_review.schema.json`。

若 lint 或 validate 失败，**不要**渲染。修好 composition 再重跑。
从一个校验失败的 composition 静默渲染属于违反契约 ——
HyperFrames 的全部意义就在于 validate 能捕获 FFmpeg 或 Remotion
捕获不到的问题。

---

## 风格桥接（playbook → CSS）

OpenMontage 的 playbook 目前会翻译成 Remotion 的 `themeConfig`
对象。对 HyperFrames 而言，等价的翻译产出：

- `:root` 上的一组 CSS 自定义属性（`--color-bg`、`--color-fg`、
  `--color-accent`、`--font-heading`、`--font-body`、`--ease-primary`、
  `--duration-primary` 等）。
- 一份简短的 `DESIGN.md`，用平实语言解释视觉体系。
- 可选的排版 `@import` 语句（仅限 HyperFrames 字体
  编译器支持的字体）。

见 `lib/hyperframes_style_bridge.py`。playbook **不**需要分叉 ——
现有的 playbook schema 携带的信息足以同时驱动 Remotion
和 HyperFrames 的输出。

---

## 成本模型

HyperFrames 的渲染是本地的：API 成本为 $0，但吃 CPU（无头
Chrome + FFmpeg）。通过 `cost_tracker` 追踪：

- `estimate` —— 基于 composition 时长 × 分辨率 × `--workers`
- `reserve` —— 0（无 API 支出）
- `reconcile` —— 渲染的墙钟时间

与 Remotion 同一套范式。

---

## 实战中的坑（用血泪换来的）

上游文档不会警告、但会让你花掉一次 60 分钟渲染才发现的问题。
在编写阶段就修掉，别等到渲染阶段。

### 全屏背景视频：源分辨率陷阱（这不是框架 bug）

症状：背景视频渲染成画面中央的一个小方框，四周一圈黑边，
尽管你已经告诉 HyperFrames 这个片段是 1920×1080。
六次渲染的调试表明，这**几乎总是源素材的质量问题，而不是
HyperFrames 的框架 bug**。要修的是输入素材，不是 CSS。

根本原因（在 Pexels + Pixabay 素材上观察到）：许多免费素材
片段即便你请求"large"尺寸档，实际交付的仍是 640×360 或
960×540。如果你的预处理做的是
`scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:...`，
你会得到一个 1920×1080 的文件，但可见内容只是居中的
640×360 矩形加黑色填充。HyperFrames 只是忠实地播放这个片段 ——
你看到的"黑框里的小视频"是对一个加了黑边的输入所做的正确渲染。

先做诊断：在怪罪 CSS 之前，对源片段和你预处理后的片段分别运行
`ffprobe -v error -select_streams v -show_entries stream=width,height`。
如果预处理后的文件已经显示为 1920×1080 填充里包着一个
640×360 的有效区域，那问题出在上游。

把预处理改成"缩放至 COVER 再裁切"，而不是"缩放至 FIT 再填充"：

```
-vf "scale=1920:1080:force_original_aspect_ratio=increase,\
     crop=1920:1080,unsharp=3:3:0.6"
```

这会把小片段放大到至少覆盖 1920×1080，裁掉溢出部分，
并做锐化（unsharp）以抵消观感上的发虚。输出是
满幅的，HyperFrames 会把它渲染成铺满整个画面。

规范的 wrapper-div 范式（`patterns.md`）依然是背景的正确
HTML 结构：

```html
<div style="position:absolute;top:0;left:0;width:1920px;height:1080px;overflow:hidden;">
  <video
    data-start="0" data-duration="60" data-track-index="0"
    src="..." muted playsinline
    style="width:100%;height:100%;object-fit:cover;"
  ></video>
</div>
```

之所以要用它，是因为当视频画幅比与 16:9 略有出入时，wrapper 上的
`overflow: hidden` 能优雅地裁切；也因为内层 `<video>` 上的
`object-fit: cover` 能处理源画幅比不是 16:9 的（少见）情况。它
**不是**对某个框架布局 bug 的绕行方案 —— 只要源文件的内容填满整个画面，
框架同样会把 `<video class="clip">` 的尺寸算对。

视觉处理（`filter`、`border-radius` 等）应施加在
wrapper 上，或施加在像 `.bg-slot video { filter: ... }` 这样限定作用域的选择器上。

隐蔽 vs 显眼的失败模式：当你在上面叠加压暗滤镜
（`brightness(0.25–0.35)`）或满幅排版时，这个坑会被掩盖 ——
黑边看起来像是"氛围感的暗调"。而一旦你转向素材优先的处理
（brightness > 0.5、下三分之一排版），它就会立刻暴露。如果
你从一开始就打算走素材优先路线，请在 assets 阶段探测源素材分辨率。

当你确实找不到 HD 片段时，就换管线：改用 FFmpeg
混合合成（在外部的 b-roll 卷中做 缩放至 cover + 裁切 + unsharp，
再通过色度键叠加 HyperFrames 排版）。这正是
`projects/quantum-willow-multiverse/` 在用 640×360 Pexels 源素材做了六次
HyperFrames 渲染之后最终采用的范式。

### 素材优先的场景，渲染前一定要先在预览里拖动检查

60 分钟的渲染很昂贵。在投入整段渲染之前，
打开 Launch 预览面板（或 `npx hyperframes preview`），
在每一章里至少拖到一个 b-roll 应当占主导的场景。小视频这个 bug ——
以及诸如"下三分之一文字在 1080p 下跑到画面外"这类布局问题 ——
在预览阶段只是 2 秒的目视检查，在渲染阶段却是 60 分钟的回归代价。

### 提升素材片段的可读性，而不是调低不透明度

在 b-roll 之上叠加排版时，不要只是降低视频的不透明度 ——
那会把两层都弄浑浊。正确做法是：

- 视频保持 `filter: brightness(0.55) saturate(0.85)`（可见
  但已压暗）。
- 在特定文字后面加一层局部 CSS 遮罩（`radial-gradient` 或
  `rgba(7,7,12,0.5)` 的 `linear-gradient`），尺寸贴合该文字块。
- 在文字自身上使用 `text-shadow: 0 2px 24px rgba(0,0,0,0.8)`，形成
  独立于背景的局部光晕。

这样既保留素材的鲜活感，又能确保字幕和标题
在任何一帧上都保持可读。

### 素材片段在渲染前需要更密集的关键帧

当素材片段的关键帧间隔 > 5 秒时，渲染会以
`video_heavy_parallel_timeout` 失败，或产生画面卡顿。下载的素材在
暂存进工作区之前，务必用
`ffmpeg ... -c:v libx264 -r 30 -g 30 -keyint_min 30
-sc_threshold 0 -movflags +faststart` 重新编码。参见
`hyperframes_compose` 现有的工作区预处理 —— 它目前还
不会自动做这件事。

### 视频密集的 composition 用 `--workers 1` 渲染

当大量视频同时加载时，默认的并行捕获会压垮无头 Chrome。
对于任何包含 5 个以上背景视频元素的 composition，务必给
`hyperframes render` 传 `--workers 1`。

### 用 Outfit / Inter / JetBrains Mono，不要用 Space Grotesk

HyperFrames 的确定性字体编译器只会内联它有映射表的字体。
即便通过 Google Fonts 加载，`Space Grotesk` 也会退化为
回退字体（通常是 Arial）。检查编译器的警告输出或
`deterministicFonts.ts` 映射表。稳妥的选择：`Outfit`、
`Montserrat`、`Inter`、`JetBrains Mono`、`Poppins`、`Playfair Display`。

## 反模式

- ❌ 当现有 schema 已经携带颜色、排版和运动信息时，还为 HyperFrames
  分叉一份 playbook 数据。
- ❌ 编写引用 `remotion-composer/public/` 的 HyperFrames composition
  —— HyperFrames 工作区是独立且自包含的。
- ❌ 从 OpenMontage 编排器运行 `hyperframes init`。`init`
  会创建它自己的一套项目语义并安装 agent skills —— 它是给
  人类初始化项目用的，不是给管线用的。`hyperframes_compose`
  会直接生成项目文件。
- ❌ 把 HyperFrames 当作"不带 Remotion 的 React"。HyperFrames 是
  以 HTML 为先、配合 GSAP 的。如果你的场景是用 React JSX 写的，它属于
  Remotion。
- ❌ 在 HyperFrames 内的 GSAP 中使用 `repeat: -1`。无限循环的 tween 会破坏
  确定性的 seek-and-capture 渲染。始终使用有界的重复次数。
- ❌ 在构建时间线的过程中，从 `async` 上下文、`setTimeout` 或 Promise
  中触发动画。页面加载后，`window.__timelines` 必须被
  同步地完整填充。

---

## 已接入 HyperFrames 的管线

| 管线 | 状态 |
|----------|--------|
| `animation` | Wave 1 —— 对于动态图形密集的 brief，HyperFrames 是一等选项 |
| `animated-explainer` | Wave 1 —— 当概念本身就是 HTML/GSAP 原生的时候 HyperFrames 可行；数据图表密集的讲解视频仍以 Remotion 为默认 |
| `screen-demo` | Wave 1 —— 合成产品 UI 用 HyperFrames 可行；终端专属演示仍优先用 `TerminalScene`（Remotion） |
| `cinematic` | Wave 2 |
| `hybrid` | Wave 2 |
| `documentary-montage` | Wave 2 |
| `talking-head` | 推迟 —— 取决于 TalkingHead 的对等能力 |
| `avatar-spokesperson` | 推迟 —— 取决于 TalkingHead 的对等能力 |
| `clip-factory`、`podcast-repurpose`、`localization-dub` | 推迟 —— 当前的 compose 路径依赖 Remotion 的字幕烧录 |
| `framework-smoke` | 不适用（测试管线） |

已接入管线的 proposal 与 compose director 会显式描述运行时选择 ——
见各管线的 `proposal-director.md` 与
`compose-director.md`。
