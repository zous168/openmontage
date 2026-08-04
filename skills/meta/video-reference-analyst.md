# 参考视频分析师 —— 元技能

## 何时使用

当用户提供一个视频 URL（YouTube、Shorts、Instagram、TikTok，或任意 URL）
或一个本地视频文件作为**参考**时 —— 也就是"帮我做个像这样的"，而不是
"剪辑这段素材"。

若用户说的是"剪这个视频"或"把它切成片段"，则改走相应的
素材主导管线（clip-factory、talking-head、hybrid）。本技能针对的是
**基于参考**的生产。

## 识别信号

以下情况触发本技能：
- 用户贴了 YouTube/Shorts/Instagram/TikTok 链接
- 用户说"像这样的"、"受它启发"、"这种风格"、"类似于"
- 用户上传了一个视频并说"我想要一个像这样的"
- 用户说"我看到这个视频，想做个类似的"

以下情况**不要**触发：
- 用户提供素材并说"剪这个"或"切这个" → 用 source_media_review
- 用户提供音频并说"给这个配个视频" → 走标准管线
- 用户只想要一份转写稿 → 直接用 TranscriptFetcher

## 协议

### 第 1 步：分析参考视频

以 `analysis_depth: "standard"` 运行 VideoAnalyzer：

```python
video_analyzer.execute({
    "source": "<url or path>",
    "analysis_depth": "standard",
    "max_keyframes": 20
})
```

读取产出的 VideoAnalysisBrief。在继续之前，先向用户呈现一份摘要。
这**不是**原始数据的倾倒，而是一种对话式的解读，并且**必须**
按五要素来组织，好让下游阶段能直接取用字段：

```
"我看完这支视频了。我看到的是：

**内容：** [两句话概括这支视频讲什么]
**风格：** [一句话 —— 节奏、视觉处理、能量]
**结构：** [Y 秒内有 X 个场景，节奏风格]
**运动：** [M 个场景中有 N 个是动态片段 / 动画静图 / 静态图像。
这支视频使用的是 [AI 生成的视频片段 / 带平移缩放的静图 / 混合]。]

**五要素拆解（逐镜头或逐镜头组）：**
- Subject：[类型、数量、属性；跨镜头的主体转换：revealing / disappearing / switching / complex-alternating；或 N/A]
- Subject Motion：[按时间顺序的动作；互动；或 N/A]
- Scene：[叠加层（文字/图形）单独列出；POV（drone/OTS/macro 等）；环境；时段；动态]
- Spatial Framing：[景别；主体位置；纵深；相对高度；如何变化]
- Camera：[播放速度；镜头；高度；角度；对焦/景深；稳定度；运动]

**它为什么奏效：** [2-3 件具体的事 —— 钩子技法、节奏、
视觉转场、旁白风格]

**保真度备注：** [DNA 锁摘录 —— 一行写清主体 + 场景锚点]
[时间密度 —— 实时感 vs 压缩感；若有则注明空帧风险]
[音频 —— 有唇形同步/对白吗？有值得克隆的微声学细节吗？]
[分段 —— 已把 N × 13 秒的生成提示词写入 brief]

现在让我看看在你当前的配置下能做什么……"
```

上面那段五要素块是 `proposal-director`、`script-director` 和 `scene-director` 将会读取的**规范形式**。不要把它压回成散文 —— 保留标签。

**运动分类至关重要。** VideoAnalysisBrief 现在包含逐场景的
`motion_type`（"motion_clip"、"animated_still"、"static_image"）和 `flow_variance`。
用它来判断生产方式：

- 若多数场景是 `motion_clip` → 参考视频用的是**视频生成**（Kling、
  MiniMax 等）→ 围绕视频生成工具做规划，而不是图像生成
- 若多数场景是 `animated_still` → 参考视频用的是**带 Ken Burns / 平移缩放的
  静图** → 图像生成 + Remotion/FFmpeg 合成是合适的
- 若是混合 → 注明哪些段落用运动、哪些用静图

**绝不要猜**参考视频用的是图像还是视频。去读 `motion_type` 字段。
这一步搞错，会导致提出错误的管线和错误的工具路径。

**视觉分析：** 呈现完结构化数据之后，亲自查看抽取出来的
关键帧。你**就是**多模态模型 —— 看那些关键帧图片，并用以下内容
丰富 VideoAnalysisBrief：
- 逐帧描述（主体、文字、构图、色彩）
- 跨帧的视觉连续性与风格一致性
- 类型归类与制作质量评估
- 配色提取（跨关键帧的主导色）
- 若有屏幕文字，其排版风格
- 相邻关键帧之间可见的转场规律

用你的视觉观察更新 brief 的 `content_analysis`、`style_profile` 和
`replication_guidance` 字段。分析正是在这里变得真正
全面 —— 工具提供结构；你的视觉提供理解。

### 高保真逆向工程标准（视觉增强阶段强制）

查看关键帧并撰写场景级数据时，把参考视频当作一份
**带时间码的规格说明**，而不是情绪板。下游的视频生成和
scene-director 阶段会把你的产出当作可执行的提示词来消费。目标是
避免三种经典的 AI 视频失败：**时间压缩（快进感）**、
**动作冻结（空帧）** 和 **音画失同步**。

**OpenMontage 的政策边界：** 高保真逆向提示词描述的是*参考视频
如何运作*（结构、时序、手艺）。用户的*那一版*仍然需要在
`replication_guidance.creative_differentiation_seeds`
和 proposal（第 4 步）中做创意差异化 —— 除非用户明确要求近乎克隆，
否则不要跳过差异化。

#### A. 全局 DNA 锁（角色与场景一致性）

从参考视频中提取一次，存放在
`replication_guidance.playbook_customizations.dna_lock`：

- **主体 DNA：** 骨骼结构、肤色、头发（长度、质地、颜色）、
  服装（材质、颜色、剪裁、磨损痕迹）、可辨识标记
- **场景 DNA：** 核心版式、锚点道具、光线方向、色温、
  主导配色、机位距离基线
- **光照 DNA：** 主光/补光/轮廓光方向、对比度、LUT/调色感觉
- **控制 token（追加到每一段的提示词末尾）：**
  `real-time physics, constant speed, no time-lapse, no dead frames,
  maintain exact character and scene consistency`

第 1 段**建立**这把锁。sidecar 中后续的每一段（见 G）
都必须以 `[INHERIT DNA LOCK]` 开头，并声明与上一段末帧和音频尾部的
延续关系 —— 不要从头重新描述主体/场景
（防止漂移）。

#### B. 物件的物理锚定

对每一件手持、佩戴或桌面道具，在场景描述中记录：

| 字段 | 示例 |
|-------|---------|
| 绝对尺寸 | `12cm ceramic cup` |
| 画面占比 | `~8% of frame width` |
| 材质 / 反射率 | `matte black ceramic / glossy metal` |
| 接触 | `fingers wrap lower third of cup body` |
| 阴影 | `cast lower-left, ~45° from key light` |

当参考视频展示的是一件具体物品时，绝不要只用泛称（`a cup`、`a phone`）——
歧义会导致跨片段的物件漂移。

#### C. 时间密度 —— 秒级动作与微动态

把每个镜头拆成带明确时长的**以秒为界的节拍**：

```
[00:00-00:03] weight shifts left over 3s, chest rises/falls with breath,
              fingers tap table once per second
```

**反快进：** 每一个位移性动作都必须带 `duration: Xs` 和
物理 token（`real-time physics`、`constant velocity`、`no temporal compression`）。

**反空帧：** 在任何超过 0.5 秒的静止区间里，至少注入 1 个微动态：
呼吸（胸口起伏 2–3mm）、自然眨眼（0.2–0.4 Hz）、手指微调、
布料摆动、光线闪烁、背景枝叶晃动。

动作数量必须与墙钟秒数相符 —— 不要把好几秒的运动压缩成
一句话。

#### D. 后期与合成（画中画、贴纸、转场）

把叠加层作为 Scene 要素里的**独立一层**列出 —— 绝不要并进
背景描述。使用归一化坐标（原点在左上）：

```
[00:05.0-00:09.5] PiP @ [75%, 70%, 20%, 25%] — rounded rect, 2px white stroke,
light drop shadow, content: [describe], 0.5s fade in, 4.0s hold, 0.5s fade out
```

用精确到帧的时间码标注切点与转场：

- 硬切：`[Cut @ MM:SS:FF]`
- 叠化 / 划像：`[Transition: CrossDissolve @ MM:SS:FF, duration: 1.0s]`

若可见，记录边缘处理（圆角像素、描边、阴影模糊/偏移）和混合模式。

#### E. 音频、微声学与唇形同步

在 `narration_transcript.segments` 中，把**逐字**的语音与时间戳对齐。
在 `structure_analysis.scenes[].narration_text` 中加入逐场景对白，
并把微声学备注写在 `description` 末尾；若该事件只有画面，
则写在 `on_screen_text` 中：

- 开口前的吸气、咂嘴、吞咽、气声、布料窸窣
- 房间底噪 / RT60 / 早期反射（明显时写 `exact room impulse response`）
- 对白镜头要声明：`lip-sync perfectly, viseme timing matches phonemes`

跨段音频必须写明：`audio seamlessly continues from previous segment,
zero pitch/timbre discontinuity, identical noise floor`。

#### F. 以场景为中心的分析（不要另开文案轨）

在参考视频中观察到的一切，都归入 **`structure_analysis.scenes[]`**：

| 字段 | 记录什么 |
|-------|-----------------|
| `description` | 视觉分析 + 结构化节拍，以散文形式呈现 |
| `on_screen_text` | 烧录字幕、下三分之一条、屏幕图形（可见则逐字记录） |
| `narration_text` | 该场景中说出的对白/旁白（参考视频没有则留空） |
| `beats[]` | 可选的秒级定时视觉/运动动作（`start_seconds`、`end_seconds`、`kind`、`description`） |

当 ASR/Whisper 产出了语音时，同时在 brief 根部填充 `narration_transcript`。

**不要**创建 `copy_track`、`copy` 或其他生产侧的文案层 —— 只用分析类词汇。

可选的共享 AI 视频生成默认值 → brief 根部的 `generation`（`prompt_profile`、`delivery`、`environment`……）。

**逆向推导出的提示词（必交付物）** → brief 根部的 `generation_spec`：

- 把参考时长切分成 **13 秒的段**（依据 `反推视频提示词.md`；更短的参考视频就一段）。
- 每一段都**必须**包含 `assembled_prompt` —— 最终可直接交给 provider 的 UGC 六段式字符串。
- 在为 `reference_analysis` 写检查点之前，用 `lib.generation_spec.attach_generation_spec_to_brief()`
  构建它。不要把拼装工作只留给 scene_plan。

逐场景的原始素材仍然存放在 `structure_analysis.scenes[].beats[]`；`generation_spec`
是下游阶段会**优先读取**的**已编译的逆推结果**。

#### G. 持久化到 VideoAnalysisBrief（符合 schema，供管线消费）

使用**已有的** artifact 字段 —— 不要依赖没人读的孤儿键。

**DNA 锁** → `replication_guidance.playbook_customizations.dna_lock`：

```json
"replication_guidance": {
  "playbook_customizations": {
    "dna_lock": {
      "subject": "...",
      "scene": "...",
      "lighting": "...",
      "control_tokens": "real-time physics, constant speed, ..."
    }
  }
}
```

**逐场景逆向规格** → 丰富每一条 `structure_analysis.scenes[]`：

| 字段 | 内容 |
|-------|---------|
| `description` | 完整五要素 + 秒级节拍，以结构化散文呈现 |
| `on_screen_text` | 该场景中可见的屏幕文字 |
| `narration_text` | 该场景中说出的内容 |
| `beats[]` | 定时的视觉/运动微动作 |
| `shot_language` | 镜头、运动、光照、景深 |
| `motion_type` | 来自工具，或视觉复分类结果 |

可选的根部 `generation` 块用于共享的视频生成默认值（见 F 节）。

下游消费方（已接线完毕）：

- `backlot/state.py` → `build_scene_storyboard_prompt()` 会为每张分镜卡读取 `dna_lock`、
  `style_profile` 和内容丰富的参考场景（仅用于 UI 预览草稿）
- `scene-director` → `description` / `required_assets` 中的结构化方案 + 定时节拍
- `asset-director` → **最终的 `video_selector` 提示词**；六段式表格与附录 A 在
  `skills/pipelines/explainer/asset-director.md`（那是执行门禁 —— 不要在此重复）

呈现用户摘要（第 1 步）时，包含一段**精简的** DNA 锁摘录、
一个示例场景的节拍块，并说明完整的 13 秒分段存放在 sidecar 中。

### 五要素结构化输出（强制）

分析师的报告**必须**把参考视频拆解为来自 CMU/Harvard CHAI 研究的**五个要素**（也是 `skills/creative/video-gen-prompting.md` 中使用的规范结构）。仅有叙述性摘要已经不够 —— 下游阶段（proposal、script、scene-director）会直接消费五要素形式，不再重新解析散文。

**决策树式描述策略。** 对每个识别出的镜头，按顺序走完全部五个要素：

> - **Subject：** 类型、属性（数量、年龄、角色、服装、可辨识特征）、多主体时的区分方式、跨镜头的转换（revealing / disappearing / switching / complex-alternating）。
> - **Subject Motion：** 按时间顺序的动作；群体/互动模式（并行、顺序、反应式）；位移 vs 手势 vs 面部。
> - **Scene：** **叠加层单独列**（文字、下三分之一条、图形、水印 —— 把它们作为独立一层点出来，不要并进环境描述）+ POV（drone、aerial、OTS、macro、top-down、dashcam、FPV、handheld、locked-off）+ 环境 + 时段 + 动态（天气、粒子、人群移动）。
> - **Spatial Framing：** 景别（ECU/CU/MS/WS/EWS）、主体在画面中的位置、纵深（前景/中景/背景的使用）、相对高度（高于/齐平/低于主体）—— 以及当相机或主体移动时，这些在镜头内如何**变化**。
> - **Camera：** 播放速度（实时 / 慢动作 / 延时）、镜头畸变（变形宽银幕、鱼眼、移轴）、高度（地面 / 视平线 / 高处）、角度（俯角 / 仰角 / 荷兰角）、对焦/景深（rack focus、深焦、浅景深）、稳定度（固定 / 手持 / 稳定器）、运动（推 / 拉 / 摇 / 俯仰 / 推轨 / 横移 / 升降 / 环绕）。
>
> **不适用的要素要明确标为 N/A**（例如 "Subject: N/A —— 纯风景镜头"，或 "Scene overlays: N/A —— 无图形"）。**静默省略是分析师最常见的失败**，它会产出含糊的下游提示词。

原语定义和各要素使用的规范词汇表见 `skills/creative/video-gen-prompting.md`。

### 第 2 步：能力审计

运行标准 preflight：

```bash
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.support_envelope(), indent=2))"
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu(), indent=2))"
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.capability_catalog(), indent=2))"
```

把参考视频的需求与可用能力做映射：

```
参考视频所需            你的能力                   缺口
─────────────────────    ─────────────────────      ──────────
视频片段（科幻）         视频生成：0/12 已配置      无 key，阻塞
旁白（低沉男声）         TTS：ElevenLabs 可用       就绪
背景音乐                 音乐：MusicGen 可用        就绪
合成引擎                 Remotion：可用             就绪
                         HyperFrames：可用          就绪
                         FFmpeg：可用               就绪（独立操作）
```

**合成引擎选择：** Remotion 和 HyperFrames 是并列、无高低之分的
合成运行时 —— 在这里**不要**预先锁定任何一个。当两者都可用时，
`AGENT_GUIDE.md` 中的 "Present Both Composition Runtimes (HARD RULE)" 门禁支配这个
选择：在 proposal 阶段把两个选项连同权衡一起呈现给用户，并在锁定
`render_runtime` 之前等待明确批准。静默取默认值是
被禁止的。在这个流程里 FFmpeg 不算合成运行时 —— 它保留给
合成管线之外的独立操作（修剪、转码、字幕烧录）。

对缺口要如实说明。若需要视频生成而它不可用，就清楚地说出来：

```
"这个参考视频用的是生成出来的科幻画面。目前你还没有配置任何视频
生成 provider。你有这些选择：

• 添加 `provider_menu()` 为视频生成推荐的网关或 provider key
• 若有多个 provider 可选，总结权衡并根据用户 brief 推荐一个
• 不用视频生成继续 → 我改用素材库画面 + Remotion 动画
  （观感不同，但同样能做）

你更倾向哪一种？"
```

对每个不可用的工具，从注册表读取 install_instructions —— **不要**
硬编码 key 名、provider 名或安装链接。

### 第 3 步：问关键问题

在给出提案之前，把 VideoAnalysisBrief 告诉不了你的信息问清楚：

1. "你这一版要旁白吗，还是只要画面加音乐？"
2. **若要旁白：现在就把音频架构定下来。** 问：
   "这个故事该怎么讲？可选："
   • **单一旁白** —— 一个声音讲完整个故事（像皮克斯短片）
   • **角色对白** —— 角色之间对话，没有旁白者
   • **旁白 + 角色声音** —— 旁白推进故事，角色偶尔有台词"
   这个决定会影响脚本、配音选角和预算。它**必须**在
   提案之前定下来 —— 不要拖到 script 或 compose 阶段。
3. "你的视频要多长？参考视频是 [X] 秒。"
4. "你有特定的主题/题材吗，还是让我沿着参考视频
   同样的主题发挥？"
5. "参考视频里有没有你特别喜欢或特别不喜欢的元素？"

**不要**一次全问完。先问那个最重要的空白。若用户的第一条
消息已经回答了其中一些，就跳过它们。

### 第 3b 步：轻量调研

**这一步是强制的。** 即便已经有清晰的参考视频和用户方向，
agent 在提出概念之前也必须做有针对性的调研。**不要**跳过这一步、
只靠参考分析加你自己的知识。

调研范围（保持聚焦 —— 这不是完整的 research-director 阶段）：

1. **内容格局：** 检索 3-5 支与用户想要的东西类似的现有视频。什么有效？
   什么已经被做烂了？哪些角度还新鲜？这能让你的提案扎根于
   真实存在的东西，而不只是你想象出来的。

2. **风格/技法调研：** 检索与该生产方式相关的最佳实践：
   - 若用 AI 视频生成：哪个模型最擅长这个题材？有哪些已知的提示词
     范式？角色一致性技巧？
   - 若做动画：哪些动画风格适合这个内容？
   - 若参考视频有某种独特技法：它是怎么实现的？

3. **题材调研：** 若用户的主题包含事实性内容（科学、
   历史、原理），收集 3-5 个具体数据点或事实，让视频更
   有意思。即便是娱乐/喜剧类视频，也去调研
   类似内容为什么抓人（套路、钩子、回报模式）。

**如何呈现：** 不要倒出原始调研。把发现织进你的提案：
- "我看了类似的频道 —— 多数食物拟人化视频都用 X，所以我们
  这个 Y 的转折会很突出"
- "在用 [某个具体技法] 时，Kling 对拟人化角色处理得不错"
- "表现最好的 60 秒喜剧短片都用三拍结构：铺垫、
  升级、意外回报"

**时间预算：** 2-3 分钟的网络检索。这是一次轻量扫描，不是
深度调查。若需要，完整的 research-director 阶段会在
管线内部稍后运行。

### 第 4 步：创意提案（2-3 个变体）

强制：agent **绝不**能提出一个翻版。参考视频是灵感，
不是模板。每个提案都必须有清晰的创意差异化。

每个变体使用这个结构：

```
## 方案 [A/B/C]："[标题]"

**受启发之处：** [从参考视频保留了什么 —— 节奏、结构、调性]
**创意转折：** [改变了什么 —— 角度、题材、视觉处理、钩子]

**视觉方案：**
- Playbook：[最接近的匹配项 + 定制]
- 视觉处理：[画面如何创作 —— 用哪些工具、哪些 provider]
- 合成：[Remotion（可用时的默认）/ FFmpeg（仅作兜底）]
- 运动：[视频生成片段 / 静图上的 Remotion 弹簧动画 / 等等]
- 片段时长策略：[把片段时长最大化，以减少 API 调用与成本。
  多数 provider 支持 5 秒和 10 秒片段。优先用 10 秒片段，并在叙事连贯的前提下
  把相邻场景合并成一个片段。一支 60 秒视频
  需要 6×10 秒片段，而不是 12×5 秒 —— 成本减半、切点更少、运动更顺。]

**音频方案：**
- 音频架构：[单一旁白 / 角色对白 / 旁白 + 角色]
- 配音选角：[每个角色的音色名 + ID —— 旁白、角色 A 等]
- TTS provider：[从 tts_selector preflight 得到的可用 provider 中选 ——
  Google Chirp3-HD（性价比最高：近乎免费、有表现力、24kHz）、
  ElevenLabs（仅在需要音色克隆时）、OpenAI gpt-4o-mini-tts（配合
  instructions 参数效果好）、Piper（离线/免费）。**不要**硬编码 provider ——
  跑一遍 preflight 看配置了什么，然后推荐可用项中最好的那个。
  **默认推荐：Google Chirp3-HD**，除非需要音色克隆。]
- 音乐：[库中曲目 / 生成 / 无]
- 声音设计：[任何特殊音频需求]

**时长：** [X] 秒
**按 provider 分列的成本估算：**
呈现一张 provider 对比表，让用户自己选：
```
Provider        质量       速度       成本（N 段）      合计
─────────      ────────   ─────      ──────────────    ─────
VEO 3.1        最高       慢         $X.XX             $X.XX
Kling Pro      高         中         $X.XX             $X.XX
Sora V2        高         中         $X.XX             $X.XX
LTX Distilled  较低       最快       $X.XX             $X.XX
```
+ 图像生成：$X.XX（N 张 × 每张 $X.XX，经 [provider]）
+ TTS 旁白：$X.XX（N 词，经 [provider]）
+ 音乐：$X.XX（[来源]）

**不要替用户选 provider。** 把选项连同成本一起呈现，
推荐一个并给出简短理由，然后让他们决定。

**如实评估：** [现实中它大概会是什么样 —— 不要吹过头]

**Layer 3 技能：** [列出将要用到的每个工具的 agent_skills。
  在写任何生成提示词之前**必须**先读它们。例如：
  - 视频生成：`ai-video-gen` 技能，了解 provider 专属提示词范式
  - 图像生成：`flux-best-practices`，了解 FLUX 提示词工程
  - TTS：`elevenlabs` 或 `openai-docs`，了解音色调节
  跳过 Layer 3 技能属于违反治理规则。]
```

**差异化范式：**

| 范式 | 示例 |
|---------|---------|
| **同结构，换题材** | 参考："黑洞如何运作" → 我们："中子星如何运作"，节奏相同 |
| **同题材，换角度** | 参考："Kubernetes 讲解" → 我们："从安全工程师视角看 Kubernetes" |
| **同调性，换视觉处理** | 参考：素材片段 + 配音 → 我们：动态图形 + 配音 |
| **同内容，换平台** | 参考：10 分钟 YouTube → 我们：60 秒 Shorts 版，节奏更快 |
| **反向观点** | 参考："AI 为什么会取代工作" → 我们："AI 为什么取代不了**你的**工作" |

**成本透明是强制的。** 每个概念都必须包含：
- 在用户要求的时长下的逐项成本估算
- 按 图像生成、视频生成、TTS、音乐、合计 拆分的成本
- 每条成本对应的 provider 名称
- 如实说明这笔预算买得到什么、买不到什么

**推荐：** 始终推荐其中一个方案并给出简短理由。不要让
用户面对几个等价选项而无从下手。

### 第 4b 步：Layer 3 技能门禁（强制）

**在任何素材生成之前**（样片或全量生产），agent **必须**：

1. 从 `skills/` 目录读取每个工具的 **Layer 2 技能**（用法指导、输入 schema、最佳实践）
2. 检查每个将要使用的工具的 `agent_skills` 字段
3. 读取 `.agents/skills/` 中每一个被引用的 **Layer 3 技能**（provider 专属提示词）
4. 把 provider 专属的提示词指导应用到所有生成提示词上

**绝不要为了搞懂怎么用某个工具而去读工具源码（*.py）。**
技能之所以存在，正是为了让 agent 不必去读实现代码。
Layer 2 技能描述*是什么*和*何时*。Layer 3 技能描述*怎么做*。

这**不是**可选项。AGENT_GUIDE 明确写着：*"Layer 3 不是可选的。
每个生成工具都有 agent_skills 字段。写提示词之前先读它们。"*

生成前的检查清单示例：
```
工具              agent_skills              已读？
────────────      ────────────────────      ─────
video_selector    ai-video-gen              [ ]
flux_image        flux-best-practices       [ ]
elevenlabs_tts    elevenlabs, text-to-speech [ ]
video_compose     remotion-best-practices   [ ]
```

在所有相关的 Layer 3 技能都读完之前，不要进入第 5 步。
一条泛泛的提示词与一条被技能武装过的提示词之间的差别，
就是"能用"与"有电影感"之间的差别。

### 第 5 步：样片优先的生产（强制）

用户选定变体之后，**始终**这样说：

```
"选得好。在投入完整的 [X] 秒视频之前，我先做一段
10-15 秒的样片 —— 开场钩子 + 一个中段场景。这样你能先
听到配音、看到视觉风格、感受节奏，然后我们再全力投入。

样片预计成本：$[X.XX]
要我先做样片吗？"
```

样片**不是**可选的。即便用户说"直接做整个吧"，也要温和地
劝一句：

```
"我还是强烈建议先做样片 —— 它只占成本的很小一部分，
却能让我们尽早发现风格上的不匹配。你要是满意，我立刻推进到
完整视频。"
```

只有在已经建议过、用户仍然坚持时才跳过样片。

**样片内容：**
- 1-2 个有代表性的场景（钩子 + 一个中段场景）
- 用选定音色实际生成的 TTS 旁白
- 实际生成/取自素材库的画面
- 音乐铺底片段
- 字幕样式预览

**样片检查点：**
呈现样片时说："这是一段预览。感觉对吗？我可以调整的有：
配音、视觉风格、节奏、音乐、配色。"

按样片反馈迭代，直到获批。样片存放在：
`projects/<name>/assets/sample/sample_v{N}.mp4`

### 第 6 步：进入管线（硬性转向）

样片获批之后，agent **必须**进入管线。这不是可选项。

**必做步骤：**
1. 读取管线 manifest：`pipeline_defs/animation.yaml`（或与该生产类型
   匹配的那条管线）
2. **逐阶段**按序执行 —— research → proposal → script →
   scene_plan → assets → edit → compose → publish
3. 在**每个**阶段之前，读取它的 director 技能：
   `skills/pipelines/<pipeline>/<stage>-director.md`
4. 在每个阶段产出所需的 artifact
5. 在每一个 `checkpoint_required: true` 的地方都写检查点
6. 在每一个 `human_approval_default: true` 的地方都取得用户批准

**不要合并阶段。** 不要从"用户批准了提案"直接跳到
"生成所有素材"。管线阶段的存在是为了强制质量门、
artifact 依赖和复看检查点。跳过它们属于违反治理
规则。

**要带进管线的上下文：**
- VideoAnalysisBrief 作为 research/proposal 阶段的落地上下文
- 当产出了高保真逆向提示词时，还要带上
  `replication_guidance.playbook_customizations.dna_lock` 和
  `video_analysis_brief.generation_spec` —— scene-director 和 asset-director 必须遵守
  这些 artifact 中的时序、DNA 锁和微动态
- 用户选定的变体作为已获批的方向
- 已吸收进 brief 的样片反馈
- 所有创意差异化决策，记录在 decision_log 中
- 第 3 步中确定的音频架构与配音选角决策
- 第 4b 步中已经读过的 Layer 3 技能

从这里开始由管线接管。VideoAnalysisBrief 与标准 artifact 一同
流转，在每个阶段提供参考依据。

## 多个参考视频

当用户提供多个参考 URL 时：

1. 分别分析每个视频（对每个都跑一次 VideoAnalyzer）
2. 呈现一份对比摘要："视频 A 在 X 方面做得好，视频 B 在 Y 方面做得好"
3. 在提案中注明哪些元素受哪个参考启发
4. 主参考的 VideoAnalysisBrief 随管线流转；
   次要参考在 research_brief 中记录

## 错误处理

| 失败 | 措施 |
|---------|--------|
| URL 下载失败 | 报告错误，并建议：换一个 URL、提供本地文件，或不带参考继续 |
| 没有字幕可用 | 下载视频，在本地用 Whisper 转写 |
| 场景检测失败 | 退回到均匀抽帧 |
| 全部分析都失败 | 请用户口头描述这个参考视频，然后走标准的创意需求收集流程 |

绝不要静默跳过分析步骤。若某处失败了，告诉用户发生了什么，
以及它对分析质量有什么影响。
