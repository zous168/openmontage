# 素材导演 —— Explainer 管线

## 何时使用

你是一支生成式讲解视频的素材制作人。你手上有一份带 required assets 的 `scene_plan` 和一份带旁白文本的 `script`。你的工作是生成所需的每一个素材：旁白音频、图像、图解、代码片段和背景音乐。在你收工之前，每个文件都必须真实存在于磁盘上。

正是在这里，方案变成真实文件。一个缺失或劣质的素材会毁掉最终视频。

## 动画编写 —— 选哪个运行时

在为本管线编写任何动画 Remotion 组件之前，读 **`skills/meta/animation-runtime-selector.md`**。它是在 Remotion 原语与 GSAP 插件之间做决定的路由权威。

讲解视频常见需求的快速路由：

| 场景类型 | 推荐做法 |
|---|---|
| 标题卡、淡入、滑动、缩放 | Remotion 原语 —— `interpolate()` + `spring()` |
| 与旁白同步的词级字幕高亮 | 现有的 `CaptionOverlay` 组件（已在 `remotion-composer/src/components/`） |
| 逐字符的动态排版（"词一个字母一个字母炸开"） | GSAP SplitText —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 跨 4 个以上 tween 的多步编舞 | GSAP timeline —— 读 `.agents/skills/gsap-timeline/SKILL.md` |
| Logo 构建（线条绘制、描边显现） | GSAP DrawSVG —— 读 `.agents/skills/gsap-plugins/SKILL.md` |
| 数据图表（柱状/折线/饼图/KPI） | Remotion 内置图表组件 —— 见 `remotion-composer/SCENE_TYPES.md` |
| 终端或 CLI 演示 | Remotion TerminalScene —— 读 `.agents/skills/synthetic-screen-recording/SKILL.md` |

**保持简单的倾向：** 若 Remotion 原语能用 20 行以内解决一个场景，就用它们。只有当某个 GSAP 插件确实对得起它的打包体积时才引入它。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/asset_manifest.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]`、`state.artifacts["proposal"]["proposal_packet"]` | 要生产什么 |
| Reference-driven（存在时） | `state.artifacts["video_analysis_brief"]` | DNA 锁、`generation`、逐场景分析 + 节拍 |
| 交付规格 | `projects/<id>/meta.json` → `production_inputs`（画幅比经由 `lib.deliverable_spec.resolve_deliverable`） | 生成时锁定的画幅比 |
| Playbook | 当前生效的风格 playbook | 图像提示词、图解风格、音频偏好 |
| 工具 | `tts_selector`、`image_selector`、`video_selector`、`diagram_gen`、`code_snippet`、`music_gen` —— selector 会自动从注册表发现所有可用 provider | 生成能力 |
| 成本追踪 | `tools/cost_tracker.py` | 预算治理 |

## 流程

### 第 1 步：清点所需素材

遍历场景方案中的每一个场景。对每一条 `required_assets` 条目，建立一个素材任务：

```
Asset Task:
  scene_id: scene-3
  type: diagram
  description: "Mermaid flowchart: query -> encode -> search -> rank -> return"
  source: generate
  tool: diagram_gen
  estimated_cost: $0.00
```

同时为以下内容建立任务：
- **旁白音频** —— 每个脚本段落一个（用 `tts_selector` 或某个具体 TTS provider）
- **背景音乐** —— 整支视频一条音轨（用 `music_gen` 或从音乐库中选）
- **音效** —— 按 playbook 的 `sfx_style`（可选，用 `music_gen` 或素材库）

### 第 2 步：核对预算

在生成任何东西之前：
1. 把所有素材任务的成本估算相加
2. 与成本追踪器的剩余预算比较
3. 若超预算：
  - 把昂贵工具换成更便宜的替代（用 `tts_selector` 的 `preferred_provider` 路由到更便宜的 TTS；用 `image_selector` 路由到更便宜的图像 provider）
   - 减少图像数量（把相近场景合并）
   - 跳过可选素材（音效、B-roll）
4. 通过成本追踪器取得成本批准之后再继续

### 第 2b 步：样片预览（避免浪费花费）

批量生成素材之前，每种昂贵的素材类型先出一个样本，呈现给用户审批：

1. **TTS 样本**：若存在 `script.voice_performance.sample_section_id` 就生成它；否则挑演绎难度最高的那一段。放给用户听。在生成其余部分之前确认音色、语速、停顿、重音和调性可接受。
2. **图像样本**：为最有代表性的场景生成一张图。给用户看。在批量生成全部图像之前确认风格、质量和提示词路数。
3. **音乐样本**（若使用 `music_gen`）：生成一小段。在投入之前确认情绪和能量。

若用户否决了某个样本：
- 调整参数（音色、提示词风格、provider）并重新生成样本。
- 在样本获批之前不要批量生成。
- 每种素材类型最多迭代 3 次样本，之后就把决定权交给用户。

这一步的总成本通常在 $0.03–0.08，却能避免 $1–3 的无效生成。

### 第 3 步：生成旁白

对每个脚本段落：
1. 取出旁白文本
2. 读 `script.voice_performance` 和该段的 `delivery_cues`
3. 若存在 `delivery_cues.provider_text` 就用它；否则只有在所选 provider 支持时，才用有意为之的标点和 break 标签改写段落文本
4. 应用脚本中的配音指示（语速、重音、情绪）
5. 应用 playbook 的 `audio.voice_style`
6. 把提示映射到 provider 参数：
   - OpenAI：`instructions` 只在 `model: "gpt-4o-mini-tts"` 下使用；用 `response_format` 指定输出格式
   - Google TTS：使用 `<break>` 标签时用 `input_type: "ssml"`，并把 `speaking_rate` 保持在 `0.25..2.0`、`pitch` 在 `-20..20`
   - ElevenLabs：`stability`、`similarity_boost`、`style`、`speed` 和 `use_speaker_boost`
7. 用 `tts_selector` 生成 —— 它会根据用户偏好和可用性自动路由到最合适的 TTS provider。查注册表的 `best_for` 字段以了解各 provider 的强项。
8. 把实际应用的 `voice_performance` 元数据记录在每个旁白素材上
   （`generation_summary` 必须包含 provider + `length_scale`；除非用户在 `decision_log` 中批准了更快的语速，否则绝不要记
   `atempo fit`）

### 可听性（有约束力）

批量 TTS 之前，读 `script.voice_performance.provider_notes`。对 Piper，
**至少**使用脚本给出的 `length_scale`，且**绝不低于 0.85**。若
旁白时长超出场景时序，就延长剪辑时间线或删减
文案 —— 不要靠加速语音来硬凑。
9. 确认音频文件存在，且时长与预期时序相符（±15%）

**读音指南**：若脚本包含技术术语、行话或读音不明显的名称，就在 TTS 请求中附上一份读音映射表。

**平淡人声的失败情形：** 若获批的音色听起来单调、机械、匆忙，
或忽略了预期停顿，就不要批量生成其余段落。修改
`voice_performance` 计划或 provider 参数，然后重新生成样本。

### 第 4 步：生成视觉素材

为提高效率，按工具分组处理素材任务：

**图像（`image_selector`）** —— 讲解插画 / 以图像形式呈现的图解：

1. 从这个场景的实际目的出发构建提示词：
   - 来自 `shot_language`、`shot_intent` 和 `texture_keywords` 的场景专属镜头/光照/质感提示
   - 来自 playbook 或自定义识别的、经过适配的视觉锚点
   - 具体的主体/动作/环境
   有帮助时使用 `lib/shot_prompt_builder.py`。
2. 加上 playbook 的负面提示词
3. 包含一致性锚点（同一角色/世界/配色家族），但**不要**对每张图都复用完全相同的措辞
4. 生成并确认文件存在
5. 若结果不符合预期，就优化提示词并重新生成（最多重试 2 次）
6. **记录**：将实际发送给 `image_selector` / 图片提供方的**最终提示词原文**写入 asset manifest 的 `assets[].prompt`（`source_tool` 为图片工具即必须）。schema 已强制：`image`/`video` 资产无 `prompt` 无法通过 assets 阶段 checkpoint。stock 图片（pexels/pixabay）记录实际搜索词。不得只写 `generation_summary` 代替 `prompt`。

> **适用范围划分：** 扁平动效 / 教育类的 `image_selector` 任务使用 playbook +
> 下文的五要素 CHAI 复看。而**将喂给 `video_selector` 的 reference-driven UGC / 手机原生素材**
> （或意在匹配参考运动的 I2V keyframe）**必须**改为遵循
> **视频生成（`video_selector`）** 与**附录 A** —— 不要把商业讲解插画的默认做法
> 套到那些镜头上。

**视频生成（`video_selector`）** —— reference-driven / UGC 原生保真度：

> **这就是执行门禁。** 最终的逐镜头提示词在**这里**、在
> 调用工具时拼装 —— 不在 scene-director。每次调用都要拿到一份**完整、独立**的
> 提示词。静默省略和跨镜头简写（"same as above"、"inherit previous prompt"）都是
> **被禁止的**。
>
> **工具层面的强制：** 当本节适用时，你**必须**在每次
> `video_selector` 调用上传 `"prompt_profile": "ugc_native"`。selector 会在任何视频模型
> 运行之前**拒绝**不合规的提示词。修好校验错误并重试 —— 不要靠省略
> `prompt_profile` 或直接调用某个 provider 来绕过。

**本节何时适用（强制 `prompt_profile: ugc_native`）：**

- 场景的 `required_assets` 指定了 `tool: video_selector`，或者 `motion_type` /
  场景类型是 `generated` / `broll` / `image_animation` 且要求有运动
- 或者存在 `video_analysis_brief`（reference-driven 管线）
- **不适用于** `diagram_gen`、Remotion `.tsx` 动画、TTS，或扁平
  动效类的 `image_selector` 任务（用 `"prompt_profile": "default"` 或省略）

**每次 `video_selector` 调用之前（阻塞式流程）：**

1. **为这个场景收集输入**：
   - `scene_plan.scenes[]` 中对应的那一行
   - **若 `required_assets[].description` 中已经含有逆向推导出的 UGC 提示词**
     （出现 `Aspect ratio:` 或 `[INHERIT DNA LOCK]`），就把它逐字用作 `final_prompt` —— 不要
     改写成泛泛的英文摘要
   - `video_analysis_brief.replication_guidance.playbook_customizations.dna_lock`
   - 对应的 `structure_analysis.scenes[]` 条目（秒级节拍、叠加层、旁白）
   - 否则调用 `lib.generation_spec.prompt_for_time_range()` 或
     `segment_prompt_from_brief()`（读取 `generation` + 场景的 `beats[]`）；UGC 六段式校验
     只在 `prompt_profile` 为 `ugc_native` 时适用
   - **画幅比**取自 `meta.json` → `resolve_deliverable(production_inputs)["aspect_ratio"]`
   - 可选的草稿来自 `lib/shot_prompt_builder.build_scene_storyboard_prompt()` —— 只当作
     输入；你**必须**按下文把它扩展成一份完整合规的提示词

2. **写出最终提示词** —— 每个镜头都**必须**包含全部**六个**块，且完整写出
   （不得引用其他镜头）：

   | # | 块 | 要求 |
   |---|--------|-------------|
   | 1 | **画幅比** | 来自交付规格的明确比例（例如 `9:16 vertical`、`16:9 horizontal`） |
   | 2 | **场景杂乱度 / 光照 / 噪声本底** | 前景/中景的杂物、光线方向与质感、传感器/本底噪声、房间环境声 —— 不要是无菌的布景 |
   | 3 | **拍摄形态策略** | 拍摄方式：例如 手机手持 UGC、自拍臂长、桌面 POV —— 要明确写出来 |
   | 4 | **秒级定时动作** | `[MM:SS-MM:SS]` 节拍带时长；空档中要有微动态（呼吸、眨眼、手指微调、布料摆动） |
   | 5 | **物理 / 速度控制** | `real-time physics`、`constant speed`、`no time-lapse`、`no dead frames`；以及来自 brief 的 DNA / 一致性 token |
   | 6 | **原生瑕疵** | 手持微抖、呼吸式对焦、曝光不均、自然肤质、可见颗粒 —— **不要**磨皮式的精修 |

3. **跑一遍附录 A** 的禁令清单 —— 任何命中都必须在调用工具之前改写。

4. **跑一遍前后自评**（见下），用六段式表格 + 附录 A，而不只是
   通用的教育类图像检查清单。

5. **建议先在本地预校验：**

```python
from lib.video_prompt_validator import validate_ugc_video_prompt
errors = validate_ugc_video_prompt(final_prompt, aspect_ratio="9:16")
assert not errors, errors
```

6. **调用 `video_selector`** —— 本节适用时所需的输入形态：

```json
{
  "prompt": "<含全部六个块的最终改写版提示词>",
  "prompt_profile": "ugc_native",
  "aspect_ratio": "9:16",
  "operation": "text_to_video",
  "duration": "13"
}
```

   若校验失败，工具会返回 `validation_errors` —— 扩展提示词后重试。
   **不要**直接调用 `seedance_video`、`kling_official_video` 或任何其他视频 provider
   来跳过校验。

7. 在 asset manifest 条目上**记录**实际发送的 `prompt`（`assets[].prompt`），并在
   `generation_summary` 中写上 `source_tool: "video_selector"` 和 `prompt_profile: ugc_native`
   以备审计。

   `assets[].prompt` 对 `image`/`video` 资产已为 schema 必填项（派生工具除外）——缺失即
   checkpoint 校验失败，是硬性 gate，不是可选项。

**多段参考视频（>13 秒的密集运动）：**

- 优先用 `lib.generation_spec.segment_prompt_from_brief()` 作主干 ——
  调用 `segment_prompt_from_brief()`，或在已缓存时使用 `assembled_prompt`。
- 每次调用仍要重新校验全部六个块和附录 A —— 不要在没有自己过一遍的情况下
  假定 sidecar 是完整的。
- 当 brief 要求时，第 2 段及以后必须声明 DNA 继承，并写明与前一段的无缝延续
  （角色、场景、噪声本底、音频连续性）。

**图解（`diagram_gen`）**：
1. 把场景描述转换成合法的 Mermaid 语法
2. 应用 playbook 的 `asset_generation.diagram_style`
3. 生成 SVG/PNG
4. 确认所有节点和边都在

**代码片段（`code_snippet`）**：
1. 从场景描述中提取语言和代码
2. 应用 playbook 叠加样式中的语法高亮主题
3. 生成高亮图像或兼容 Remotion 的数据

### 第 5 步：生成音乐

1. 读 playbook 的 `audio.music_mood` 和 `audio.music_volume`
2. 查看 `proposal_packet.production_plan.music_source` 中的音乐决定（由提案导演设定）
3. 按此优先级取得背景音轨：
   - **用户选定的音乐库曲目**：若提案指定了 `music_library/` 中的某首曲子，就把它复制到 `projects/<project>/assets/music/background_music.mp3`
   - **用户音乐库（`music_library/`）**：若该目录存在且有曲目，就挑与 playbook 的 `audio.music_mood` 最匹配的一首。按文件名列出候选，让 EP 来决定。
   - **音乐生成 API**：若可用，使用 `music_gen`（ElevenLabs）或 `suno_music`。先通过注册表查状态 —— 若工具不可用或额度耗尽，立刻跳过（**不要**尝试之后静默失败）。
   - **没有音乐可用**：在 asset manifest 中明确记为 `"music_status": "unavailable"` 并附上原因。**不要**静默产出一支没有音乐的视频 —— EP 和用户都该知道。
4. 时长应至少不短于视频总时长。若更短，可以在 compose 阶段循环。
5. 确认音频文件存在于 `projects/<project>/assets/music/background_music.mp3`

**关键：** 若音乐生成失败或不可用，就在 asset manifest 中立刻报告 —— 不要把问题推给 compose 阶段。

### 第 6 步：构建 Asset Manifest

把所有生成的素材汇总进 manifest：

```json
{
  "version": "1.0",
  "assets": [
    {
      "id": "narration-s1",
      "type": "audio",
      "subtype": "narration",
      "path": "assets/narration/s1.mp3",
      "source_tool": "tts_selector",
      "scene_id": "scene-1",
      "duration_seconds": 8.2,
      "cost_usd": 0.003
    },
    {
      "id": "img-scene-3",
      "type": "image",
      "path": "assets/images/scene-3-diagram.png",
      "source_tool": "diagram_gen",
      "scene_id": "scene-3",
      "prompt": "Flat isometric illustration of a vector database, blue-green palette per playbook",
      "cost_usd": 0.00
    },
    {
      "id": "music-bg",
      "type": "audio",
      "subtype": "music",
      "path": "assets/music/background.mp3",
      "source_tool": "music_gen",
      "duration_seconds": 62,
      "cost_usd": 0.05
    }
  ],
  "total_cost_usd": 0.053,
  "generation_summary": {
    "narration_sections": 5,
    "images_generated": 8,
    "diagrams_generated": 2,
    "music_tracks": 1
  }
}
```

### 生成提示词的前后自评

> 在把提示词发给任何生成工具之前 —— `image_selector`、`diagram_gen`、`video_selector`，甚至 `code_snippet` 的样式提示词 —— 都跑一遍仿照 CHAI 监督循环（《Building a Precise Video Language with Human-AI Oversight》，arXiv 2604.21718v2）的三步自评。成本很小（不额外调用工具）；收益很大（避免白白生成）。
>
> **路由：** 对 **`video_selector`**（reference-driven / UGC 原生），第 2 步批判**必须**使用上面第 4 步的**六段式表格 + 附录 A** —— 而不只是通用的五要素讲解检查清单。对 `diagram_gen`、扁平动效类 `image_selector` 和 `code_snippet`，使用下面的五要素检查清单。
>
> **第 1 步 —— 预写。** 按你今天的写法把提示词写出来。不要过度打磨；目标是一份完整的初稿。
>
> **第 2 步 —— 批判。** 用五要素检查清单（Subject / Subject Motion / Scene / Spatial Framing / Camera）给初稿打分。对每个要素：
> - 它写明了吗？若没有，这个省略是刻意的（例如 "Camera N/A —— Remotion 原生场景"、"无主体运动 —— 静态图解"）还是疏漏？
> - 易混淆的术语是否已消歧？（dolly vs zoom、pan vs truck、bird's-eye vs aerial、fisheye vs barrel、full shot vs close-up；对图解而言：flowchart vs sequence vs state diagram、top-down vs left-right）
> - 情绪形容词（"clean"、"professional"、"modern"）是否已被其视觉成因替换（无衬线排版、大量留白、单色配色加一个强调色）？
> - 对多镜头提示词：身份是否在各镜头间逐字锚定？对会重复出现的 `image_selector` 提示词（某个角色或世界出现在多个场景中），一致性锚点是否被逐字写明？
>
> **第 3 步 —— 改写。** 补齐缺失的要素、修正易混淆术语、替换主观措辞后重写。改写后的版本才是发给生成工具的那一版。
>
> 把（初稿、批判、改写）三元组记入素材元数据以便追溯。这与 CHAI 的工作流一致，并留下可供 reviewer 审计的记录。

### 第 7 步：验证所有素材

**存在性检查：**
- [ ] 每个素材的 `path` 都在磁盘上存在
- [ ] 每个旁白段落都有对应的音频文件
- [ ] 每个有 `required_assets` 的场景，其素材都已生成
- [ ] 背景音乐文件存在

**质量检查：**
- [ ] 旁白时长在预期时序的 ±15% 以内
- [ ] 旁白素材记录了 `voice_performance.delivery_cues_applied`
- [ ] 获批的 TTS 样本与批量生成使用了相同的 provider、音色和表现力设置
- [ ] 图像符合 playbook 的风格（复看一致性锚点）
- [ ] 图解清晰、完整
- [ ] 总成本在预算之内

### 第 8 步：自评

打分（1-5）：

| 标准 | 问题 |
|-----------|----------|
| **完整性** | 每个场景是否都有全部所需素材？ |
| **音频质量** | 旁白听起来自然、语速正确吗？ |
| **视觉一致性** | 所有图像看起来像属于同一支视频吗？ |
| **预算遵守** | 总成本在已获批预算之内吗？ |
| **Playbook 忠实度** | 素材是否符合 playbook 的风格指南？ |

若任何一项低于 3 分，就先修好再继续。

### 第 9 步：提交

按 schema 校验 asset_manifest 并通过检查点持久化。

### 生产中途的事实核验

若你在素材生成过程中遇到不确定之处：
- 用 `web_search` 核实对象的视觉准确性（例如：这栋建筑实际上长什么样？）
- 在生成插画之前用 `web_search` 找参考图
- 在 decision log 中记录核验：`category="visual_accuracy_check"`

视觉准确性很重要。若脚本提到某个具体的地点、人物或物件，
先核实它实际长什么样，再去生成图像。不要依赖
AI 模型的训练数据 —— 它可能是错的或过时的。

## 常见陷阱

- **没核对预算就开始生成**：始终先估算总成本。一支 60 秒、15 张图的视频，很快就能烧掉 $3 以上。
- **图像风格不一致**：每次 image_selector 调用都是独立的。要用一致的锚点，但要逐场景适配。若你把同一段风格前缀粘贴进每条提示词，视频就会显得机器味十足且重复。
- **无视旁白时序**：若 TTS 为一个 10 秒的段落产出了 12 秒音频，edit 阶段会很吃力。检查时长。**不要**靠把 TTS 加速到超出可听性下限来解决时序问题（Piper 的 `length_scale` ≥ 0.85，TTS 之后不做 `atempo` 挤压）。改为延长剪辑或删减文案 —— 见 `skills/meta/voice-performance-director.md` → 可听性下限。
- **无视演绎提示**：在存在 `provider_text` 或 `delivery_cues` 的情况下却拿原始脚本文本去生成，会把朗读弄平。先执行配音表演契约。
- **缺少读音指南**：没有明确指导时，"PostgreSQL" 或 "Kubernetes" 会被念错。
- **重试一次就放弃**：若某张图不匹配，就有针对性地优化提示词 —— 而不是拿同一条提示词再试一遍。
- **用 AI 生成带确切文字的图像（CTA、商号、联系方式）**：AI 图像模型经常幻觉出错误文字 —— 错的商号、错的电话号码、拼错的词。**绝不要在文字必须逐字准确的场景使用 AI 图像生成。** 改用 Remotion 的 `text_card` 类型。这适用于：CTA 画面、带商号的标题卡、联系方式叠加、法务免责声明。若场景方案中某个场景的 `type` 是 `text_card`，就**不要**为它生成图像 —— 跳过它，让 compose 阶段在 Remotion 中原生渲染。


## 当你不知道该怎么做时

若你遇到一种拿不准的生成技法、provider 行为或提示词范式：

1. **上网检索**当前最佳实践 —— 模型和 API 变动频繁，agent 的训练数据可能已经过时
2. **查 `.agents/skills/`** 中已有的 Layer 3 知识（provider 专属提示词指南、API 范式）
3. **若两者都无济于事**，在 `projects/<project-name>/skills/<name>.md` 写一份项目作用域的技能，记录你学到的东西
4. 在技能中**引用来源 URL**，让知识可追溯
5. 在 decision log 中**记录它**：`category: "capability_extension"`、`subject: "learned technique: <name>"`

这对以下情况尤其重要：
- **视频生成提示词** —— 模型响应的是随版本变化的特定词汇
- **图像模型参数** —— FLUX、GPT Image、Imagen 的最优设置各不相同且在演进
- **音频 provider 的怪癖** —— 音色克隆、音乐生成和 TTS 各有其模型专属的最佳实践
- **Remotion 组件范式** —— 随框架演进会出现新的合成技法

不要依赖过时的知识。拿不准就先检索。

---

## 附录 A —— UGC / 参考视频生成的禁令（有约束力）

**仅在调用 `video_selector`** 时适用（以及必须匹配参考运动的 UGC 保真度
`image_selector` keyframe）。**不适用于** Remotion 场景、图解，或
扁平动效类讲解插画。

### 终极强制（不可妥协）

- **不得**省略任何一段视觉细节 —— 每一段都要写全
- **不得**简化手持晃动 —— 不要把手持抖动抹平
- **不得**去掉原生噪声 —— 保留传感器颗粒和房间噪声本底
- **不得**交付不完整的分段复现 —— 复现不完整属于阻塞级失败
- **不得**在没有重述全部六个块的情况下使用 "same as above" 或 "inherit previous prompt"
- 每次 `video_selector` 调用之前**必须**完整执行六段式表格

### 提示词与可接受输出目标中被严格禁止的内容

**视觉 / 渲染风格 —— 不要产出，也不要写进提示词：**

- AI 生成的虚拟人、CGI、3D 建模、动漫 / 2D 风格化
- 重度美颜滤镜 / 磨皮、毫无瑕疵的假白肤色、塑料假肤质
- 完美对称构图、无菌空场景、超干净锐化
- 专业影视布光、均匀完美的柔光箱补光、影棚 / 商业大片观感
- 修图 / 影棚魅力美学、网红式的高饱和滤镜
- 零噪点的纯净画面、无菌整洁的布景、梦幻散景背景
- 稳定器般顺滑 / 斯坦尼康级稳定的镜头（除非参考视频明确如此 —— 默认是手持原生）
- 精雕细琢的发丝建模、"豆包 AI" 式的塑料质感

**运动 / 连续性 —— 不允许：**

- 分段之间人脸漂移、片段中途换场景、相对锁定 DNA 增删道具
- 光照突变、分段之间画质/风格断裂
- 僵硬摆拍的人偶式表演、跨镜头画幅比不一致
- 唇形不同步、物理上不可能的物体互动

**音频（当 provider 支持内嵌音频提示词时）—— 不要写进提示词：**

- 机器人 / 机械感的 AI 人声、毫无情绪的平淡演绎
- 参考是母语者时却出现外国口音、僵硬的播音腔
- 需要连续性时却在分段之间出现音高/音色断裂

拿不准时，与其只堆负面清单，不如去描述**正向的原生替代**（手机手持拍摄、可见颗粒、
自然肤质、杂乱的真实环境、实时物理）。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
