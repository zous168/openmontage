# 视频生成提示词 —— 通用指南

## 何时使用

为视频生成家族（`video_selector`、`seedance_video`、
`heygen_video`、`wan_video`、`hunyuan_video`、`ltx_video_local`、`ltx_video_modal`、
`cogvideo_video`）撰写提示词时。本技能涵盖在所有视频生成模型上
都适用的通用提示词词汇表。关于**首选的高端默认项**，见下表中的 Seedance 2.0
一行。

模型专属技巧见下面链接的指南。

## 模型专属指南

| 模型 | 指南 | 关键要点 |
|-------|-------|-------------|
| **Seedance 2.0（standard / fast）** | `creative/prompting/seedance-prompting.md` + Layer 3 `.agents/skills/seedance-2-0/` | 配置了 `FAL_KEY` 或 HeyGen 时的**首选高端默认项**。单次生成即带同步音频、多镜头生成、导演级镜头控制、由引号内对白驱动的唇形同步、参考图转视频（9 图 + 3 视频 + 3 音频）。Elo 1269（Artificial Analysis 榜首）。 |
| **Sora 2 / Sora 2 Pro** | [OpenAI Sora 2 Cookbook](https://developers.openai.com/cookbook/examples/sora/sora2_prompting_guide) | 结构化模板最丰富。进阶字段：镜头、滤镜、调色、有源声、服装、后期。 |
| **VEO 3.1 / VEO 3** | [Vertex AI 提示词指南](https://cloud.google.com/vertex-ai/generative-ai/docs/video/video-gen-prompt-guide) | 词汇参考表最好。14 组件提示词结构。 |
| **Grok Imagine Video** | `creative/prompting/grok-prompting.md` | 当提示词需要 `<IMAGE_1>` 这类参考图占位符，以及需要身份/产品延续时最合适。 |
| **LTX-2** | [LTX 提示词指南](https://docs.ltx.video/api-documentation/prompting-guide) | 6 要素结构。音频/人声提示词。"该避免什么"一节很强。 |
| **HunyuanVideo 1.5** | [腾讯提示词手册](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/assets/HunyuanVideo_1_5_Prompt_Handbook_EN.md) | 公式：Subject + Motion + Scene + [Shot] + [Camera] + [Lighting] + [Style] + [Atmosphere]。 |
| **Runway Gen-4** | [Runway 提示词指南](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide) | "聚焦运动，而非外观。" 一个片段一个场景。简洁取胜。 |
| **Kling 2.6** | [Kling 提示词指南](https://fal.ai/learn/devs/kling-2-6-pro-prompt-guide) | 4 段式结构。支持用 `++emphasis++` 语法强调关键元素。 |
| **Kling 官方版** | Layer 3 `.agents/skills/kling-official/` | 官方直连 API。用 `provider="kling_official"` 与 fal.ai 版 Kling 区分。`api_family` 选择 Classic、Turbo 或 Omni；Turbo 的图生视频需要 URL 形式的参考图。 |
| **Wan 2.1 / CogVideoX** | 用本通用指南 | 没有官方提示词指南。标准的电影摄影词汇很好用。 |

## 顺序很重要

列举多个主体或事件时：

- 当事件随时间展开时用**时间顺序**（"先是 X 进入，然后 Y 做出反应"）。
- 当时间顺序不相关时用**重要性顺序** —— 人先于物，最大/最居中的先写，然后是次要主体。

## 自包含的提示词

> 提示词要写到：一个从未见过目标视频的人，仅凭你的文字就能想象出主体、场景、运动和镜头调度。如果读者想象不出来，生成模型也渲染不出来。

## 通用提示词公式

前人工作（CMU/Harvard，《Building a Precise Video Language with Human-AI Oversight》）表明，VLM 能可靠描述主体 + 场景，但在运动、空间和镜头上失败。**强制提示词填满全部五个槽位，是杠杆率最高的改动。**

OpenMontage 规范的五要素骨架：

```
[Subject]        类型 + 关键视觉属性 + 多个主体时如何区分
[Subject Motion] 按时间顺序排列的动作；主体↔物体、主体↔主体的互动；群体动作
[Scene]          叠加层（单独列！）+ POV + 环境 + 时段 + 场景动态
[Spatial]        景别 + 画面内位置 + 纵深（前景/中景/背景）+ 相对相机高度
                 —— 以及这些在片段中如何**变化**
[Camera]         播放速度 → 镜头畸变 → 高度 → 角度 → 对焦/景深 → 稳定度 → 运动
```

**提示词越短 = 创作自由度越大。提示词越长 = 控制力越强。**

### 各模型的提示词长度

来自论文第 6 节的经验甜点区间 —— 不同模型奖励不同的提示词密度：

| 模型 | 甜点区间 | 备注 |
|---|---|---|
| Seedance 2.0 | 主镜头 200–400 词，插入镜头 80–150 词 | 奖励长而结构化的五要素提示词 |
| Wan 2.2 | 200–400 词 | 在长字幕上做过微调 |
| Sora 2 / VEO 3.1 | 100–250 词 | 超过约 250 词后收益趋平 |
| LTX-2 | ≤ 80 词 | 超过就退化，要写紧凑 |
| Runway Gen-4 | ≤ 60 词 | "聚焦运动，而非外观" |

### 叠加层不属于场景纵深

> 叠加层（标题、HUD、字幕、水印、边框图形）**不**属于场景的 前景/中景/背景 纵深轴。把它们单独列出，写明内容和位置。绝不要说"前景里的叠加层"。

---

## 镜头景别

| 景别 | 何时使用 |
|------|-------------|
| **远景 / 定场镜头** | 开启一个场景，交代地点 |
| **全景** | 主体从头到脚，连同环境 |
| **中景** | 腰部以上，兼顾细节与环境 |
| **中近景** | 胸部以上，有对话式的亲近感 |
| **特写** | 面部或关键物体，强调情绪 |
| **大特写** | 孤立的细节（眼睛、水滴、纹理） |
| **过肩镜头** | 对话构图，建立联系 |
| **主观视角（POV）** | 观众成为角色本人 |
| **鸟瞰 / 俯拍** | 地图式总览，全知视角 |
| **虫瞰视角** | 直直向上看，强调高度 |
| **荷兰角 / 倾斜角** | 地平线倾斜，不安或紧张 |
| **仰角** | 主体显得强大、有支配感 |
| **俯角** | 主体显得渺小、脆弱 |

## 镜头运动

论文表明当前模型会混淆平移、旋转和纯镜头变化 —— 要把提示词分组，让模型无法把它们混为一谈：

| 分组 | 原语 | 规则 |
|---|---|---|
| **平移**（相机物理移动） | dolly in/out、truck left/right、pedestal up/down | "dolly forward toward subject" |
| **旋转**（相机原地转动） | pan left/right、tilt up/down、roll CW/CCW | "pan right across the room" |
| **纯镜头**（相机不动） | zoom in/out、rack focus、pull focus、focus tracking | "zoom in" ≠ "dolly in" |
| **混合 / 标志性** | dolly zoom（眩晕变焦）、arc/orbit、crane、whip pan、tracking/follow、handheld | "vertigo" 只在揭示时刻使用 |
| **静止状态** | static（完全不动 —— 严格）、micro-shake、locked-off | "static" 要求零运动、零对焦变化、零变焦 |

> **dolly ≠ zoom。** dolly 是相机平移；zoom 是焦距变化。模型会跟随占主导的那个词。**pan ≠ truck。** pan 是旋转，truck 是横向平移。

> **静止镜头是严格的。** 静止镜头意味着零运动、零对焦变化、零变焦。若其中任何一项发生了，就**不要**写 "static camera" —— 去挑正确的运动原语。

## 相机高度（相对地面）

| 原语 | 示例 |
|---|---|
| 航拍高度 | "drone-altitude wide of the city" |
| 高处高度 | "rooftop height looking across the street" |
| 视平线高度 | "framed at eye level" |
| 臀部高度 | "hip-height tracking shot" |
| 地面高度 | "low to the ground, ankle height" |
| 水面高度 | "skimming the water surface" |
| 水下 | "submerged below the surface" |

## 相机角度（相对主体）

| 原语 | 定义 |
|---|---|
| **鸟瞰** | 严格的正俯拍。与"航拍"不是一回事。 |
| 俯角 | 从上往下看主体 |
| 平角 | 相机与主体等高 |
| 仰角 | 从下往上看主体 |
| 虫瞰 | 直直向上看 |
| **荷兰角（固定）** | 地平线倾斜并保持稳定 |
| **荷兰角（滚动）** | 拍摄过程中地平线倾斜度变化 |

> **鸟瞰 = 严格正俯拍。航拍 = 高度。** 一个 45° 俯视的无人机镜头，是航拍高度上的俯角，**不是**鸟瞰。

## 视角（POV）

| POV | 示例 |
|---|---|
| 第一人称 | "the camera follows the character's viewpoint as they walk" |
| 无人机 | "aerial drone footage of city skyline" |
| 过肩 | "OTS framing of the laptop screen" |
| 俯视斜角 | "top-down view of the chess board, tilted slightly" |
| 行车记录仪 | "vehicle dashcam framing of the road" |
| 客观 / 中性 | （默认 —— 没有特定 POV 时使用） |

## 光照词汇

| 术语 | 效果 |
|------|--------|
| **自然光** | 柔和、真实（晨光、阴天、月光） |
| **黄金时刻** | 暖色阳光、长影子、浪漫 |
| **高调光** | 明亮、均匀、愉快 —— 喜剧、生活方式 |
| **低调光** | 暗、高对比 —— 惊悚、剧情 |
| **伦勃朗光** | 脸颊上的三角形光斑，经典肖像 |
| **黑色电影** | 深重阴影、突兀高光 |
| **体积光** | 穿过空气介质的可见光束（雾、尘） |
| **逆光** | 光在主体后方，剪影效果 |
| **侧光** | 强方向性，戏剧化阴影 |
| **实用光源** | 画面内的光源（台灯、蜡烛、霓虹招牌） |
| **轮廓光 / 边缘光** | 勾勒主体轮廓，与背景分离 |

**光照方向修饰词**：主光、补光、反光、轮廓光、溢光、负补光。

**色温**：暖（钨丝、琥珀）、冷（日光、蓝）、混合。

## 镜头与光学效果

| 效果 | 结果 |
|--------|--------|
| **广角镜头**（24-35mm） | 视野更广，透视被夸张 |
| **长焦**（85mm 以上） | 透视压缩，主体从背景中分离 |
| **变形宽银幕** | 拉伸画幅，标志性的镜头光晕 |
| **镜头光晕** | 强光射入镜头产生的光条 |

### 镜头畸变

论文区分了两个模型会当作不同效果处理的原语 —— 它们**不能**互换：

| 原语 | 效果 |
|---|---|
| **鱼眼** | 极端弯曲，边缘强烈外凸 |
| **桶形** | 轻微畸变，直线略微外弓 |

### 对焦 / 景深

| 原语 | 定义 |
|---|---|
| 深焦 | 从前景到背景全部清晰 |
| 浅景深 | 主体清晰，背景虚化 |
| 极浅景深 | 焦平面薄如刀刃 |
| Rack focus | 拍摄中途在两个主体之间切换焦点 |
| Pull focus | 渐进式焦点转移（比 rack 更慢） |
| Focus tracking | 焦点跟随移动的主体 |

当景深在一个镜头内变化时，要同时标注**起始**和**结束**的焦平面（前景/中景/背景/失焦）。

## 主体转换

当主体进入、离开或交接焦点时，明确写出这个转换：

| 原语 | 何时 |
|---|---|
| **主体显现** | 新主体进入画面（由主体移动**或**相机移动造成） |
| **主体消失** | 某个主体离开画面 |
| **主体切换** | 焦点从一个主体转向另一个（常通过 rack focus 或相机运动） |
| **复杂交替** | 主体之间多次交替焦点 |

始终写明成因："by subject movement" 或 "by camera movement"。这能在多镜头提示词中解锁揭示式的镜头调度。

## 多镜头提示词的身份锚定

> 除非你反复重述，否则模型会在切换镜头时丢失角色身份。在多镜头提示词的每一个镜头里，都要为每个具名主体**逐字重复**同样的 3–6 条可区分的视觉属性。代词和"同一个角色"这类说法不管用。
>
> 示例："Aang — bald, blue arrow tattoo on forehead, orange-and-yellow robes — plants his staff. … Aang — bald, blue arrow tattoo on forehead, orange-and-yellow robes — turns to camera."

## 风格与美学参照

### 电影风格
- 黑色电影、时代剧、惊悚、现代爱情
- 纪录片、艺术电影、实验电影
- 史诗太空歌剧、奇幻、恐怖
- 1970 年代爱情剧、90 年代纪录片风

### 动画风格
- 吉卜力工作室 / 日式动画
- 经典迪士尼、皮克斯式 3D
- 定格动画、黏土动画
- 手绘 2D/3D 混合
- 卡通渲染、低多边形 3D

### 艺术流派
- 印象派、超现实主义、装饰艺术、包豪斯
- 水彩、炭笔素描、水墨
- 图像小说、蓝图示意

### 胶片 / 调色
- 柯达暖调、富士冷调
- 16mm 黑白、35mm 光化学对比
- 复古颗粒叠加、高光处的光晕溢出
- 青橙调色

## 时间效果

### 播放速度

论文定义了六个明确的播放速度原语。用对那一个 —— 它们并不同义：

| 原语 | 定义 |
|---|---|
| 延时摄影 | 事件远快于真实时间（云在飞奔） |
| 快动作 | 略快于真实（1x–3x） |
| 慢动作 | 慢于真实 |
| 定格动画 | 逐帧的离散运动 |
| 变速 | 同一镜头内快慢混合 |
| 倒放 | 反向播放 |

### 其他时间手法

| 效果 | 用途 |
|--------|-----|
| **定格画面** | 戏剧性停顿 |
| **快速剪辑** | 能量、紧迫感 |
| **连续 / 长镜头** | 沉浸感、张力 |
| **淡入 / 淡出** | 场景转场 |
| **匹配剪辑** | 场景之间的视觉连续 |

## 音频描述

支持音频生成的模型（LTX-2、Sora 2、VEO 3）会响应：

**环境声**：风、雨、车流、人群嘈杂、林中鸟鸣、机械嗡鸣
**有源声**：脚步、门吱呀、玻璃碰撞、键盘敲击
**人声风格**：耳语、平静旁白、激昂播报、庄重
**音乐情绪**："soft piano in background"、"upbeat electronic"

对白要放进引号里：`Character says: "Hello world."`

## 该避免什么

> **用情绪的视觉成因来替换情绪形容词。**
> - "sad character" → "tears on cheek, shoulders slumped, staring at empty chair"
> - "cinematic mood" → "low-key Rembrandt key + 35mm anamorphic + crushed shadows, lifted-by-2-stops shadow detail"
> - "epic" → "low-angle, 24mm wide, sun directly behind subject, lens flare on the rim"
>
> "Inspiring"、"powerful"、"moody"、"epic" 约束不了像素。

> **静止镜头是严格的。** 静止镜头意味着零运动、零对焦变化、零变焦。若其中任何一项发生了，就**不要**写 "static camera" —— 去挑正确的运动原语。

| 不要 | 为什么 | 改用 |
|-------|-----|-----------|
| "Beautiful scene" | 太笼统，没有视觉信息 | "Wet cobblestone street, warm streetlamp glow reflecting in puddles" |
| "Person moves quickly" | 没有可见的动作 | "Woman sprints three steps and vaults over the railing" |
| "Cinematic look" | 每个模型本来就在往这个方向努力 | 写具体："anamorphic lens, shallow DOF, golden hour lighting" |
| "Sad character" | 内心状态是看不见的 | "Tears on cheek, shoulders slumped, staring at empty chair" |
| 可读文字 / Logo | 模型无法可靠渲染文字 | 避开带文字的招牌，或接受渲染不完美 |
| 复杂物理 | 混沌运动会产生伪影 | 保持物理简单；跳舞/走路可以，爆炸有风险 |
| 多角色对话 | 多人对话会破坏同步 | 一个片段一个说话人，或改用反应镜头 |
| 塞太满的提示词 | 元素太多 = 不连贯 | 从简单开始，一次只叠加一个元素的复杂度 |
| 冲突的光照 | "Bright noon" + "dark shadows" | 挑一套光照方案并坚持到底 |

## 提示词迭代策略

1. **从简单开始** —— 主体 + 动作 + 环境。看看模型给你什么。
2. **一次加一个元素** —— 先镜头，再光照，再风格。
3. **某个镜头翻车了** —— 往回剥。冻住相机、简化动作、再试一次。
4. **要让多个片段保持一致** —— 重复完全相同的风格/光照/调色描述。
5. **使用 seed 值** —— 找到好结果时，保存 seed 用于做变体。
6. **Grok 的参考图视频** —— 在提示词中用 `<IMAGE_1>`、`<IMAGE_2>` 等为每张源图指派清晰的角色。

## 示例：通用提示词模板

```
[Shot]: Medium close-up, slight low angle
[Camera]: Slow dolly-in
[Subject]: A weathered fisherman in his 60s, salt-and-pepper beard,
           dark wool sweater, calloused hands gripping a rope
[Action]: He pulls the rope hand-over-hand, muscles straining,
          then pauses and looks out to sea
[Setting]: Wooden dock at dawn, calm grey ocean, distant fog bank,
           seagulls wheeling overhead
[Lighting]: Soft overcast with warm break in clouds on the horizon,
            gentle rim light from the rising sun
[Style]: Documentary cinematography, 35mm film grain,
         muted earth tones with a cold blue-grey palette
[Audio]: Rope creaking, water lapping, distant gull cries, wind
```
