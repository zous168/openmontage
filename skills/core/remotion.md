# Remotion 技能

## 何时使用

从 Phase 3 起，进阶视频合成使用 Remotion —— 任何需要
基于 React 的场景装配、参数化模板、动画叠加层、转场，或
数据驱动的批量渲染的场合。简单的剪切、烧录和编码，直接优先用 FFmpeg。

## 与 Remotion Agent Skills 的关系

**已安装的 agent skills**（`.agents/skills/remotion-best-practices/`）教的是正确的
Remotion API 用法 —— import、时序、动画约束、代码范式。
**本文件**教的是 OpenMontage 如何使用 Remotion —— 哪些 composition 对应哪些管线
阶段、artifact 如何流入，以及渲染如何触发。

## Remotion 优先的路由

**只要 Remotion 可用，它就是所有最终渲染的默认合成引擎。**
它能处理视频片段（通过 `<OffthreadVideo>`）、静态图像、动画场景、
组件类型、转场以及混合内容 —— 全部在单次基于 React 的
渲染流程中完成。

FFmpeg 是**兜底方案** —— 仅在 Remotion 不可用时使用，或用于
那些不会从 React 渲染中获益的简单独立操作。

| 使用场景 | 后端 | 理由 |
|----------|---------|-----|
| 最终视频渲染（任何内容类型） | **Remotion** | 所有合成的默认项 |
| 视频片段 + 动画静图 + 文字卡 | **Remotion** | 一次渲染搞定混合内容 |
| 纯视频剪辑加转场 | **Remotion** | 原生 `<OffthreadVideo>` + 转场 |
| 动画图表/文字卡 | **Remotion** | 逐帧控制 |
| 数据驱动的批量视频 | **Remotion** | Zod props + 参数化渲染 |
| 词级字幕（在 composition 内） | **Remotion** | 带逐词高亮的 CaptionOverlay —— 优于 SRT |
| 音频嵌入（旁白 + 音乐） | **Remotion** | 原生 `<Audio>` 组件，支持音量/淡入淡出 |
| 简单修剪、拼接（无需合成） | FFmpeg | 瞬时完成，不依赖 Node |
| 字幕烧录（独立、事后追加） | FFmpeg | 仅用于给已渲染好的视频加字幕而不重新渲染 |
| 面部增强、调色 | FFmpeg | 基于滤镜，确定性强 |
| Remotion 不可用 | FFmpeg | 自动兜底 |

**注意：** `render` 操作默认自动路由到 Remotion。只有当 Remotion 未安装，
或 agent 显式为独立操作调用 `operation='compose'` 时，才会选择 FFmpeg。
当现有 composition 覆盖不了所需版式（例如自定义画中画、分屏）时，agent 也可以
通过 capability-extension 协议临时编写自定义 Remotion composition。

## 支持的场景类型（Cut Types）

Explainer composition 支持以下 cut 类型：

| 类型 | 必需的 props | 适用于 |
|------|---------------|----------|
| `text_card` | `text` | 陈述句、标题、收尾语 |
| `stat_card` | `stat`，可选 `subtitle`、`accentColor` | 大数字、冲击力强的指标 |
| `hero_title` | `text`，可选 `heroSubtitle` | 开场标题、戏剧化揭示 |
| `callout` | `text`，可选 `title`、`callout_type`（info/warning/tip/quote） | 提示、引语、重要说明 |
| `comparison` | `leftLabel`、`rightLabel`、`leftValue`、`rightValue` | 前后对比、A/B、对决 |
| `bar_chart` | `chartData` [{label, value}]，可选 `title`、`chartAnimation` | 类别对比、排名 |
| `line_chart` | `chartSeries` [{label, data: [{x,y}]}]，可选 `title` | 趋势、时间序列、增长 |
| `pie_chart` | `chartData` [{label, value}]，可选 `donut`、`centerLabel` | 占比、构成拆解 |
| `kpi_grid` | `chartData` [{label, value, prefix, suffix, change, icon}] | 仪表盘、增长指标 |
| `progress_bar` | `progress`（0-100），可选 `progressSegments` | 历程可视化、完成度、堆叠指标 |
| `anime_scene` | `images`（1-4 个路径），可选 `animation`、`particles`、`particleColor`、`particleCount`、`particleIntensity`、`vignette`、`lightingFrom`、`lightingTo` | 动画/吉卜力风格场景，支持多图交叉淡化、镜头运动、粒子叠加 |

**图表动画：** `grow-up`、`slide-in`、`pop`（柱状图），`draw`、`fade-in`（折线图），`spin`、`expand`、`sequential`（饼图），`count-up`、`pop`、`cascade`（KPI）

### Anime Scene —— 多图交叉淡化 + 粒子

`anime_scene` 类型渲染 1-4 张图像，配合平滑的交叉淡化转场、电影感镜头运动和动画粒子叠加。这能让静态图像产生动画的错觉。

**镜头运动类型：** `zoom-in`、`zoom-out`、`pan-left`、`pan-right`、`ken-burns`、`drift-up`、`drift-down`、`parallax`、`static`

**粒子类型：** `fireflies`（漂浮的金色光点）、`petals`（飘落的樱花）、`sparkles`（闪烁的星光）、`mist`（流动的雾层）、`light-rays`（丁达尔光束）

**关键 prop：** `sceneDurationSeconds` 由 `SceneRenderer` 自动传入 —— 这修复了一个致命的 Remotion 陷阱：`useVideoConfig().durationInFrames` 返回的是整个 composition 的时长，而不是该场景 Sequence 的时长。

**多图交叉淡化的算法：** 每张图占据等长的时间段。第 N 张图的淡出与第 N+1 张图的淡入按 `crossfadeDur`（约 1.2 秒）**重叠**，因此永远不会出现空帧。每个场景从同一套视觉体系生成 2-3 张图，但要逐节拍改变镜头、主体和光照。用相近的 seed 有助于制造细微的运动感，同时避免整段序列被压平成一句重复的提示词。

**参考 composition：** `remotion-composer/public/demo-props/mori-no-seishin.json` —— 6 个动画场景、30 秒，包含粒子、光照、叠加层和氛围音乐。

**风格剧本：** `styles/anime-ghibli.yaml` —— 吉卜力风格美学，含配色、排版、运动参数和 FLUX 提示词前缀。

**零 API key 视频策略：** 当没有任何图像或视频生成能力可用时，
完全用这些组件类型搭建整支视频。一段编排得当的
hero_title → kpi_grid → bar_chart → comparison → stat_card → text_card 序列，
能在零外部依赖的情况下产出精致、专业的视频。

### 零 API key 视频的成熟公式

这些规则源自系统化的渲染测试，能产出电影感的结果：

**1. 每支视频只用一个背景族。** 采用从 playbook 或自定义识别系统推导出的统一背景处理，不要把每段序列都硬套成同一种深色仪表盘外观。
这样能避免刺眼的黑白闪烁转场，也让图表颜色更加突出。
目标是视觉统一，而不是强制使用深色主题。

**2. 扁平的 props 格式。** 所有场景属性都放在 cut 对象的**顶层**
（例如 `cut.text`、`cut.chartData`），**不要**嵌套在 `props` 键下。

**3. KPI Grid 数据规则：**
- `value` 必须是较小的、人类可读的数字。组件会自动格式化：≥1M→"XM"，≥1K→"XK"。
  要表示"81 亿"就写 `value: 8.1, suffix: " Billion"`。绝不要用原始大数再加后缀。
- `change` 必须是**数字**（例如 `3.2`），不能是字符串（**不要**写 `"+3.2%"`）。

**4. Comparison 与 Callout 的主题化：**
- `comparison` 接受 `backgroundColor` 和 `color`（文字颜色），用于深色主题。
- `callout` 接受 `backgroundColor`，它同时设置容器和卡片的背景。

**5. 叠加层带来精致感。**
- `section_title` 叠加层在叙事上把场景分组（"THE CRISIS"、"THE DATA"）。
- `stat_reveal` 叠加层把戏剧化的数字浮在图表场景之上（例如角落里的 "10x"）。

**6. 场景节奏：** 每个场景 4-6 秒，45-50 秒的视频用 8-10 个场景。图表
动画至少要给 4 秒来完成。Hero title 只需要 4 秒。

**7. 配色统一。** 挑 4-5 个与主题相关的强调色，并在图表、叠加层和点缀中
一致使用。在柱状图/饼图/折线图场景中使用同一个 chartColors 数组，
以求视觉统一。

**参考 composition：** 以 `remotion-composer/public/demo-props/climate-dashboard.json`
为黄金标准，其他 demo 文件提供更多范式。

### 渲染前校验（强制）

**渲染前务必运行 `composition_validator`。** 它能捕获：
- 缺失的素材文件（图像、音频），这些会导致渲染失败
- 旁白音频长于视频时长（音频会被截断）
- 音乐短于视频（结尾出现静音）
- 无效的 cut 时序（out ≤ in）

```python
from tools.analysis.composition_validator import CompositionValidator
result = CompositionValidator().execute({
    "composition_path": "path/to/composition.json",
    "assets_root": "remotion-composer/public",
})
# 渲染之前 result.data["valid"] 必须为 True
```

**音频时长对齐：**
- 生成 TTS 旁白后，工具会返回 `audio_duration_seconds`。
- 若旁白超过视频时长：缩短脚本并重新生成，或延长最后一个场景。
- 用 `tools.analysis.audio_probe.probe_duration(path)` 检查任意音频文件的时长。
- 音乐时长应 ≥ 视频时长；播放器通过 `fadeOutSeconds` 处理淡出。

## 架构

```
remotion-composer/
├── src/
│   ├── Root.tsx              # Composition 注册表
│   ├── compositions/         # 每种管线类型一个文件
│   │   ├── Explainer.tsx     # 生成式讲解视频 composition
│   │   ├── AnimatedScene.tsx # 单个动画场景
│   │   └── TitleCard.tsx     # 独立标题卡
│   ├── components/           # 可复用的视觉构件
│   │   ├── Caption.tsx       # 字幕渲染器
│   │   ├── DiagramOverlay.tsx
│   │   ├── ProgressBar.tsx
│   │   └── TransitionWrapper.tsx
│   └── styles/               # Tailwind + 由 playbook 派生的样式
├── public/                   # 静态资源（字体、LUT）
├── package.json
├── remotion.config.ts
└── tsconfig.json
```

## 管线集成

### Artifact 如何映射到 Remotion Props

| OpenMontage Artifact | Remotion Prop | 映射到 |
|---------------------|---------------|--------|
| `scene_plan.json` → `scenes[]` | `scenes` prop | `<TransitionSeries>` 的子元素 |
| `scene.type` | 组件选择器 | `talking_head` → `<Video>`，`diagram` → `<DiagramOverlay>` 等 |
| `scene.start_seconds` / `end_seconds` | `from` / `durationInFrames` | `fps * seconds` 换算 |
| `scene.transition_in` / `transition_out` | `<TransitionSeries.Transition>` | `fade`、`slide`、`wipe` |
| `asset_manifest.json` → assets | `assets` prop | `staticFile()` 或绝对路径 |
| `style_playbook` | `theme` prop | 颜色、字体、动画曲线 |
| `edit_decisions.json` → cuts | `cuts` prop | 带裁剪片段 `<Video>` 的 `<Series>` |
| `media_profile` | Composition 尺寸 | 从 profile 取 `width`、`height`、`fps` |

### 渲染调用

编排器通过 CLI 调用 Remotion 渲染：

```bash
# 标准渲染（composition 名为 "Explainer"，无需指定入口文件）
npx remotion render Explainer \
  --props="public/demo-props/my-video.json" \
  --output=output/final.mp4 \
  --codec=h264 --crf=18

# 指定特定的 media profile
npx remotion render Explainer \
  --width=1080 --height=1920 --fps=30 \
  --props="public/demo-props/my-video.json" \
  --output=output.mp4
```

**注意：** **不要**把 `src/index.ts` 指定为入口文件 —— Remotion 会自动发现 composition。composition 名是 `Explainer`（不是 `ExplainerVideo`）。

在 Python 中，当 `backend="remotion"` 时，从 `video_compose.py` 通过 `subprocess` 调用。

### Media Profile 映射

| OpenMontage Profile | Remotion 配置 |
|--------------------|-----------------|
| `youtube_landscape` | `width: 1920, height: 1080, fps: 30` |
| `youtube_shorts` | `width: 1080, height: 1920, fps: 30` |
| `tiktok_vertical` | `width: 1080, height: 1920, fps: 30` |
| `instagram_reels` | `width: 1080, height: 1920, fps: 30` |
| `instagram_square` | `width: 1080, height: 1080, fps: 30` |
| `cinematic_wide` | `width: 2560, height: 1080, fps: 24` |

## 关键范式

### 从场景规划到 Composition

`scene_plan.json` 中的每个场景都成为 `<TransitionSeries>` 的一个子元素：

```tsx
// 伪代码 —— 实际组件位于 remotion-composer/src/compositions/Explainer.tsx
const Explainer: React.FC<ExplainerProps> = ({ scenes, theme, assets }) => {
  return (
    <TransitionSeries>
      {scenes.map((scene, i) => (
        <React.Fragment key={scene.id}>
          {scene.transition_in && (
            <TransitionSeries.Transition
              presentation={mapTransition(scene.transition_in)}
              timing={timing({ durationInFrames: 15 })}
            />
          )}
          <TransitionSeries.Sequence durationInFrames={secondsToFrames(scene)}>
            <SceneRenderer scene={scene} theme={theme} assets={assets} />
          </TransitionSeries.Sequence>
        </React.Fragment>
      ))}
    </TransitionSeries>
  );
};
```

### 用 calculateMetadata 实现动态时长

当视频长度由 TTS 音频决定时（生成式讲解视频），使用 `calculateMetadata`：

```tsx
export const ExplainerVideo = {
  component: Explainer,
  calculateMetadata: async ({ props }) => {
    const totalDuration = props.scenes.reduce(
      (sum, s) => sum + (s.end_seconds - s.start_seconds), 0
    );
    return {
      durationInFrames: Math.ceil(totalDuration * props.fps),
      fps: props.fps,
      width: props.width,
      height: props.height,
    };
  },
};
```

### 从风格剧本到主题

风格剧本（`skills/styles/`）定义视觉参数。把它们映射为 Remotion 主题：

```tsx
// 由风格剧本 YAML 派生
const cleanProfessional = {
  background: "#FFFFFF",
  text: "#1A1A1A",
  accent: "#2563EB",
  fontFamily: "Inter",
  headingWeight: 600,
  transitionType: "fade",
  transitionDuration: 15, // 帧
  animationEasing: "easeInOutCubic",
};
```

### 音频分层

旁白 + 背景音乐 + 音效，作为并行的 `<Audio>` 组件。

**音乐偏移与循环：** `audio.music` 配置支持：
- `offsetSeconds` —— 跳过安静的前奏，从曲子有力度的部分开始。用 `tools/analysis/audio_energy.py` 可自动找到最佳偏移量。
- `loop` —— 音乐比视频短时循环播放。Remotion 原生支持。
- `fadeInSeconds` / `fadeOutSeconds` —— 首尾的平滑音量渐变。

```json
"audio": {
  "music": {
    "src": "project/music.mp3",
    "volume": 0.15,
    "offsetSeconds": 55,
    "loop": false,
    "fadeInSeconds": 2,
    "fadeOutSeconds": 3
  }
}
```

```tsx
<AbsoluteFill>
  <Audio src={narrationUrl} />
  <Audio src={musicUrl} volume={0.06} startFrom={offsetFrames} loop />
  {sfxCues.map(cue => (
    <Sequence key={cue.id} from={secondsToFrames(cue.time)}>
      <Audio src={cue.url} volume={cue.volume} />
    </Sequence>
  ))}
  {/* 视觉层 */}
</AbsoluteFill>
```

### 成本追踪

Remotion 渲染吃 CPU，但 API 成本为 $0。通过 cost_tracker 追踪：
- `estimate`：基于 composition 时长 × 分辨率档位
- `reserve`：0（无 API 支出）
- `reconcile`：记录渲染的墙钟时间用于基准测试

## 关键约束

- **不要用 CSS 动画或过渡** —— 它们无法正确渲染。所有运动都用 `useCurrentFrame()` + `interpolate()`。
- **不要用 Tailwind 动画类** —— `animate-*` 类会破坏基于帧的渲染。静态 Tailwind 工具类没问题。
- **interpolate() 一律加 clamp** —— 使用 `extrapolateLeft: 'clamp', extrapolateRight: 'clamp'`，防止数值冲出端点。
- **`useVideoConfig().durationInFrames` 返回的是 composition 时长，不是 Sequence 时长** —— 这是 Remotion 的头号大坑。如果你的 composition 是 31 秒（930 帧），而某个场景的 `<Sequence>` 是 5 秒（150 帧），在该场景内部 `durationInFrames` 仍然返回 930。任何直接使用 `durationInFrames` 的交叉淡化、镜头运动或时序逻辑都会严重出错。**修法：** 从父组件把 `sceneDurationSeconds` 作为 prop 传下来，并在组件内部计算 `effectiveDuration = Math.round(sceneDurationSeconds * fps)`。`AnimeScene` 组件就是这个范式的实现。
- **需要 Node.js 18+** —— 在最低系统配置中列为可选，在推荐配置中为必需。
- **串行渲染，不要并行** —— 除非机器内存足够。每次渲染都会启动一个 Chromium 实例。

## 渲染后验证协议（适用于所有管线）

**每一次 Remotion 渲染在呈现给用户之前都必须经过验证。** 本协议适用于
**所有**管线，不只是 explainer。管线专属的 compose-director 可以扩展它，但
不得跳过其中任何一步。

**第 1 步：探测输出文件（门禁 —— 阻塞其余所有步骤）：**
```bash
ffprobe -v quiet -print_format json -show_format -show_streams rendered_video.mp4
```
逐项确认：
- [ ] 视频流存在，分辨率与 FPS 正确
- [ ] **音频流存在** —— 若缺失，立即停止，修正音频配置，重新渲染
- [ ] 时长在目标值的 ±5% 以内
- [ ] 文件体积合理（不是 0 字节，也不是小得可疑）

**若音频流缺失，不要继续。** 这意味着旁白/音乐没有被嵌入。
最常见原因：音频源在外部混好了，却从未通过 Remotion 的
`audio` prop 传入。修法：把 `audio.narration` 和 `audio.music` 加到 composition props 中并重新渲染。

**第 2 步：抽取复看帧**，取各场景的中点，逐帧目视检查。

**第 3 步：用 WhisperX/transcriber 工具转写已渲染视频的音频。**
- 若返回 0 个词 → 尽管音频流存在但内容是静音 → 需排查
- 若词数少于脚本的 80% → 音频被截断 → 需排查
- 把转写的最后一个词与脚本的最后一个词做比对

**第 4 步：向用户呈现结构化复查报告**，包含文件统计、音频验证结果、
视觉检查发现和字幕状态，然后才能宣布视频完成。

## 质量检查清单

- [ ] Composition 时长等于各场景时长之和减去转场重叠部分
- [ ] 所有 `staticFile()` 引用都能解析到实际存在的素材
- [ ] 转场没有切掉内容（时序上要把重叠算进去）
- [ ] **渲染输出中存在音频流**（ffprobe 确认 codec_type: "audio"）
- [ ] **旁白词句已通过转写验证**（不能只凭 props 想当然）
- [ ] 音频层与视觉场景同步
- [ ] 字幕渲染正确（优先用 Remotion CaptionOverlay，而非 FFmpeg SRT）
- [ ] 主题颜色与当前生效的风格剧本一致
- [ ] 输出分辨率与 FPS 匹配目标 media profile
- [ ] 渲染完成时没有 Chromium 超时错误
- [ ] 成片在目标平台上播放正常
- [ ] 带文字的场景（CTA、标题）使用 Remotion text_card，**不要**用 AI 生成的带文字图像
