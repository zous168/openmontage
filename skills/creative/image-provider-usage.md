# OpenMontage 中的图像 Provider 用法

> 如何在图像生成与素材库 provider 之间做选择，以及如何有效使用各自的能力。
> 本文是对现有 `image-gen-usage.md`（深入讲 FLUX 提示词）的补充。

## Provider 全景

### 生成类 Provider（由 AI 创作图像）

| 工具 | Provider | 成本 | 速度 | 适用于 |
|------|----------|------|-------|----------|
| `flux_image` | 经 fal.ai 的 FLUX 2 Pro | 约 $0.03-0.05 | 约 5-10 秒 | 写实照片、通用、主力工具 |
| `grok_image` | Grok Imagine Image（xAI） | 每张输出 $0.02 + 每张输入编辑图 $0.002 | 约 5-15 秒 | 图像编辑、风格迁移、多图合成 |
| `openai_image` | GPT Image 2（OpenAI） | 约 $0.01-0.21 | 约 5-15 秒 | 复杂指令、图中文字、多元素 |
| `recraft_image` | 经 fal.ai 的 Recraft V4 | 约 $0.04-0.25 | 约 5-10 秒 | Logo、SVG 矢量、品牌素材、文字渲染（注意下文的告诫） |
| `local_diffusion` | Stable Diffusion（本地） | 免费 | 约 30 秒以上 | 离线、隐私、免费 |
| `image_gen` | 多 provider（遗留，已弃用） | 视情况 | 视情况 | **已弃用** —— 请用 `image_selector` 或各 provider 专属工具 |

### 素材库 Provider（检索并下载已有图像）

| 工具 | Provider | 成本 | 速度 | 适用于 |
|------|----------|------|-------|----------|
| `pexels_image` | Pexels | 免费 | 约 2-5 秒 | 高质量摄影，支持按颜色筛选 |
| `pixabay_image` | Pixabay | 免费 | 约 2-5 秒 | 库容量大，支持按分类筛选，有插画 |

### Selector

| 工具 | 用途 |
|------|---------|
| `image_selector` | 根据偏好和可用性路由到最合适的 provider |

## 按场景类型选择 Provider

| 场景类型 | 首选 Provider | 理由 | 兜底 |
|-----------|-----------------|-----|----------|
| **真实世界照片**（城市、自然、人物） | `pexels_image` | 论真实感，真照片胜过 AI | `pixabay_image` → `flux_image` |
| **技术图表** | `diagram_gen` | 结构化、可编辑 | 用图表提示词的 `flux_image` |
| **抽象/概念插画** | `flux_image` | AI 擅长定制概念 | `openai_image` |
| **风格迁移 / 对已有图像重绘** | `grok_image` | 原生编辑流程，可提示的变换能力强 | `openai_image` |
| **多图合并 / 合成** | `grok_image` | 能把多张源图合成到同一场景 | `openai_image` |
| **Logo 或品牌素材** | `recraft_image` | 支持 SVG，文字准确 | `openai_image` |
| **带文字/标签的图像** | `openai_image` | 文字渲染最好（GPT Image 2） | `recraft_image` |
| **复杂多元素构图** | `openai_image` | 指令跟随最好 | `flux_image` |
| **主图（核心视觉）** | `flux_image` | 视觉质量最高 | `openai_image` |
| **封面图** | `flux_image` 或 `recraft_image` | 需要抓眼球 | — |
| **预算/免费项目** | `pexels_image` 或 `pixabay_image` | 免费、即时 | `local_diffusion` |
| **离线/物理隔离环境** | `local_diffusion` | 无需联网 | — |

## Provider 专属告诫

### 经 fal.ai 的 Recraft V4
- **`style` 参数会导致 422 错误**（截至 2026-04）。`style` 枚举值（`digital_illustration`、`realistic_image` 等）会被 fal.ai 的 Recraft V4 端点拒绝。**绕行方案：** 把风格方向写进提示词文本（例如写 "digital illustration of a tooth cross-section"，而不是 `style="digital_illustration"`）。`image_size` 和 `colors` 参数工作正常。
- **对确切商号的文字渲染并不可靠。** Recraft（和所有 AI 图像模型一样）可能幻觉出错误的文字。任何要求文字必须一字不差的场景（CTA 画面、商号、电话号码），请改用 Remotion `text_card`，而不是生成带文字的图像。

## 成本与质量的权衡

```

制作路线：高端
├── 主图：flux_image（每张 $0.05）
├── 辅助视觉：flux_image（每张 $0.03）
├── 文字叠加：openai_image（medium 每张 $0.05）
├── B-roll 静图：pexels_image（$0.00）
└── 10 张图合计：约 $0.35

制作路线：标准
├── 全部生成：flux_image（每张 $0.03）
├── B-roll 静图：pexels_image（$0.00）
└── 10 张图合计：约 $0.25

制作路线：省钱
├── 全部走素材库：pexels_image + pixabay_image（$0.00）
├── 图表：diagram_gen（$0.00）
└── 合计：$0.00

制作路线：离线
├── 全部生成：local_diffusion（$0.00）
├── 图表：diagram_gen（$0.00）
└── 合计：$0.00（但更慢、质量更低）
```

当任务从一张已有图像出发、且应当只路由到具备编辑能力的 provider 时，使用 `generation_mode="edit"`。

## 使用 Image Selector

多数情况下直接用 `image_selector`，让它去路由：

```python
# selector 会找到当前最合适的可用 provider
result = image_selector.execute({
    "prompt": "aerial view of a modern data center",
    "preferred_provider": "auto",  # 或 "flux"、"pexels" 等
    "output_path": "assets/images/scene-3.png"
})
```

当你确知某个 provider 最适合该场景类型时，用 `preferred_provider` 覆盖。
用 `allowed_providers` 把范围限制在免费或本地选项：

```python
# 省钱模式：只用免费 provider
result = image_selector.execute({
    "prompt": "server room interior",
    "allowed_providers": ["pexels", "pixabay", "local_diffusion"],
    "output_path": "assets/images/scene-3.jpg"
})
```

## 混合来源之间的一致性

在同一支视频中混用素材库图像与生成图像时，视觉一致性就是挑战所在。

### 策略：对所有素材统一调色
在 compose 阶段，对素材库图像和生成图像都应用 playbook 的调色 LUT。
这能统一整体观感。`color_grade` 增强工具负责这件事。

### 策略：匹配视觉识别，而不是复制粘贴前缀
生成图像时，把 playbook 的情绪、配色、质感和媒介
适配成一个简短的、贴合场景的锚点。检索素材库时，按相同的
情绪与视觉属性筛选：颜色、光照、环境、构图、年代
和质感。把 playbook 当作一致性的来源，而不是拿来粘贴的脚本。

### 策略：不要在同一场景内混用风格
不要在同一场景里一个元素用素材照片、另一个元素用 AI 插画。
保持每个场景内部一致 —— 要么全是素材库，要么全是生成。
