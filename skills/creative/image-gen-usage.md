# OpenMontage 中的图像生成用法

> 资料来源：OpenAI GPT Image 文档、FLUX/BFL API 文档，以及位于
> `.agents/skills/flux-best-practices/` 和 `.agents/skills/bfl-api/` 的现有 Layer 3 技能

## 速查卡

```
FLUX 分辨率：    1920x1088（16:9） | 1088x1920（9:16）—— 必须是 16 的倍数
最大总量：       4 百万像素（宽 x 高）
一致性：         把主图作为后续画面的 input_image
风格体系：       由 主题 + 受众 + 调性 推导，再逐场景适配
批量策略：       主图用最高质量 → 用 klein 迭代 → 最后用 pro 收尾
```

## 视频画面的分辨率

所有 FLUX 尺寸**必须是 16 的倍数**。总量上限为 4MP。

| 目标 | FLUX 分辨率 | 成本（FLUX.2 pro） |
|--------|----------------|-------------------|
| YouTube 16:9 | `1920x1088` | 每张 $0.03 |
| YouTube 4K | `3840x2160` | 需要 pro/max |
| TikTok/Reels 9:16 | `1088x1920` | 每张 $0.03 |
| 正方形 1:1 | `1024x1024` | 每张 $0.03 |
| 封面图 | `1280x720` | 每张 $0.03 |

## 保持视觉一致性

最大的挑战：让 8-12 张生成图看起来像是同一支视频里的。

### 策略 1 —— 共享视觉体系（始终采用）

先为项目定义一套共享的视觉体系，再逐场景适配。
抓住这个项目的：

- 主导情绪与质感，
- 配色方向，
- 光照倾向，
- 呈现媒介，
- 角色/环境的一致性锚点。

playbook 的 `image_prompt_prefix` 是素材来源，不是拿来
逐字粘贴到每条提示词里的。把它提炼成更短的、贴合场景的锚点。

### 策略 2 —— 主参考图（推荐）

1. 用最高质量（`FLUX.2 [max]`，$0.07）生成一张"主图"
2. 把它作为后续所有画面的 `input_image`：

```
画面 1：用详细提示词做 T2I → hero.png
画面 2：用 hero.png 做 I2I + "Same style, camera pans right to show..."
画面 3：用 hero.png 做 I2I + "Same style, zoomed in on..."
```

FLUX.2 最多支持 4 张参考图（klein）或 8 张参考图（pro/max/flex）。用编号引用："The character from image 1 in the environment from image 2."

### 策略 3 —— 锁定 seed

在提示词相近的多次生成中使用相同的 `seed` 参数。能产生相似的构图，但对提示词改动很敏感 —— 作为补充手段，而非主要策略。

## 提示词构造 —— 三段式情境化方法

**不要把 playbook 的 `image_prompt_prefix` 逐字复制到每条提示词里。** 那正是让所有场景长得一样的原因。相反，用三层情境来构建每条提示词：

### 第 1 部分：场景专属的风格指导（来自 shot_language + texture_keywords）

用场景的 `shot_language` 字段来设定镜头与光照：
```
[来自 shot_language.shot_size 的景别，例如 "medium close-up"]。
[来自 shot_language.lighting_key 的光照，例如 "golden hour warm light"]。
[来自 shot_language.depth_of_field 的景深，例如 "shallow depth of field with bokeh"]。
[来自 scene.texture_keywords 的质感，例如 "film grain, warm tones"]。
```

若场景没有 shot_language，退回到下面的模板。

### 第 2 部分：playbook 一致性锚点（适配，而非逐字照搬）

提取 playbook 视觉语言的**精髓** —— 不要复制那个前缀。例如：
- playbook 写的是 "Clean, minimal illustration with soft shadows, muted color palette" → 适配为："muted color palette, soft shadows"
- playbook 写的是 "Bold flat motion graphics, vibrant gradients" → 适配为："vibrant flat style"

这个锚点让各场景视觉连贯，同时不至于变得雷同。

### 第 3 部分：场景描述

场景的实际内容。要具体 —— 用具体细节替换笼统词汇。

**差：** "A person using a computer in a modern office"
**好：** "Software developer in a dimly lit home office, blue monitor glow reflecting off glasses, desk cluttered with energy drinks and sticky notes"

### 完整提示词示例（带 shot_language）

```
Medium close-up, golden hour warm lighting, shallow depth of field.
Muted earth tones, soft shadows.
Beekeeper in white protective gear lifting a frame dripping with honey,
late afternoon sun catching golden droplets, lavender field blurred
in the background. Film grain, warm amber tones.
16:9 aspect ratio.
```

### 兜底模板（没有 shot_language 时）

```
[从 playbook 适配来的风格锚点 —— 5-10 个词，不是完整前缀]。
[场景描述：具体的主体、动作、环境]。
[光照：golden hour / overcast / studio softbox / dramatic side-light]。
[构图：wide shot / medium shot / close-up / overhead / isometric]。
[相机：Shot on [相机] with [镜头] at [光圈]]（仅用于写实照片风格）。
16:9 aspect ratio.
```

### 使用 lib/shot_prompt_builder.py

若要以程序方式构造提示词，使用 shot prompt builder，它把三段式方法自动化了：

```python
from lib.shot_prompt_builder import build_shot_prompt
prompt = build_shot_prompt(scene, style_context=playbook_data)
```

它会把结构化的 shot_language 字段转换成针对图像/视频生成
provider 优化过的自然语言提示词。

### 各风格专属的提示词范式

| 风格 | 提示词范式 |
|-------|---------------|
| **扁平插画** | "Flat vector illustration, bold colors, clean edges, no gradients, white background" |
| **等距视角** | "Isometric 3D illustration, 30-degree angle, clean geometric shapes, soft shadows" |
| **写实照片** | "Photorealistic, shot on Canon EOS R5 with 85mm f/1.4, shallow depth of field" |
| **图示风格** | "Technical diagram, labeled components, clean lines, minimal color, white background" |
| **水彩** | "Soft watercolor illustration, muted tones, visible brush strokes, paper texture" |

## 批量生成策略

| 阶段 | 模型 | 单张成本 | 目的 |
|-------|-------|-----------|---------|
| 1. 风格基准 | FLUX.2 [max] | $0.07 | 一张主图，最高质量 |
| 2. 分镜迭代 | FLUX.2 [klein] 9B | $0.015 | 规划期的快速变体 |
| 3. 最终画面 | FLUX.2 [pro] | $0.03 | 以主图为参考重新生成成片画面 |

**速率限制：** 最多 24 个并发请求。据此安排流水。

**8 张图的讲解视频预算：** $0.07（主图）+ $0.12（8 次 klein 迭代）+ $0.24（8 张 pro 成片）= 约 $0.43

## 常见陷阱

1. **图中文字** —— AI 图像生成器处理文字并不可靠。绝不要在提示词里包含文字；文字应在 compose 阶段作为叠加层加上
2. **手与手指** —— AI 图像模型至今仍吃力。避免需要精细手部姿势的提示词
3. **角色不一致** —— 没有参考图时，同一个角色每次都会长得不一样。始终采用主参考图策略
4. **提示词过度堆砌** —— 又长又复杂的提示词产生的结果不可预测。控制在 2-3 句话
5. **提示词过度统一** —— 把完全相同的风格短语硬塞进每条提示词，会让场景显得雷同。视觉体系要保持一致，但要让每个场景表达自己的主体、镜头和情绪节拍。

## 应用到 OpenMontage

在 assets 阶段使用 `image_selector` 工具时：

1. **先从 proposal 或自定义 playbook 设计视觉体系**：情绪、配色、质感、运动能量
2. **先生成一张最高质量的主图**，作为其余全部图像的参考
3. 16:9 视频画面**使用 `1920x1088`**（FLUX 要求 16 的倍数）
4. **绝不要求图中出现文字** —— 文字叠加在 compose 阶段加
5. **预算核对** —— 生成前先估算图像总成本；超预算就切到本地 diffusers
6. 规划期**用 klein 迭代**，成片用 pro 定稿
7. **提示词控制在 2-3 句** —— 场景专属的镜头/光照 + 适配后的视觉锚点 + 具体主体
8. **与场景规划对齐** —— 每张图对应脚本中的一个具体场景
