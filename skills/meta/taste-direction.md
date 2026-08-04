# 审美方向 —— 元技能

## 何时使用

在敲定视觉识别、情绪板、proposal packet、自定义 playbook、atelier composition、图像参考批次或品牌向视频之前使用本技能。

本技能定义的是 OpenMontage 的**视频审美档案契约**。不要把它当作前端样式配方。它的产出是一份紧凑的视频审美档案，会一路穿过 proposal、场景规划、素材提示词、edit、compose 和 review。

## 产出契约

当 proposal 或 playbook 需要一份更有力的创意契约时，写一份 `taste_profile`：

```json
{
  "design_read": "Premium expert explainer: calm authority, high trust, low ornament.",
  "visual_variance": 4,
  "motion_intensity": 3,
  "information_density": 5,
  "palette_discipline": "Neutral base, one accent, no decorative gradients.",
  "layout_variation": "Alternate editorial split frames with data-forward full-frame scenes.",
  "reference_strategy": "One reference still per scene family before asset generation.",
  "anti_patterns": ["generic AI-purple gradient backgrounds"],
  "quality_gates": ["Every scene should carry the design read without explanatory labels."]
}
```

`visual_variance`、`motion_intensity` 和 `information_density` 是 1-10 的整数旋钮：

| 旋钮 | 低 | 中 | 高 |
|------|-----|-----|------|
| `visual_variance` | 紧致的体系，重复的语法 | 有规律，并划分出有意图的场景族 | 每个节拍都可以使用不同的视觉模式 |
| `motion_intensity` | 平静的停留，小幅转场 | 明确的运动重音与揭示 | 快速的动感语言，频繁的方向变化 |
| `information_density` | 每帧一个想法 | 主要想法加辅助细节 | 密集的仪表盘、图表或多层标注 |

## 流程

### 1. 做出一个"设计判读"

在选 playbook 或配色之前，先说清这支视频需要给人什么感觉、以及为什么。把它与受众、承诺、平台和题材挂钩。

好的判读是具体的：

- "面向投资人的 AI 发布：精确、克制、可信；避免炒作式视觉。"
- "青少年科普短片：明亮、好奇、有动感；让看不见的物理变得可触摸。"
- "安全事件讲解：紧张而精准；高对比、少装饰、证据可读。"

差的判读只有形容词：

- "现代、干净"
- "电影感"
- "专业"

### 2. 拨定三个旋钮

在写概念之前先确定 `visual_variance`、`motion_intensity` 和 `information_density`。这些数字应当能解释后续的选择：

- 高运动 + 低信息量意味着短促的动感节拍，而不是密集图表。
- 低运动 + 高信息量意味着稳定的画面、图表逐步搭建，以及较长的可读停留。
- 高变化度意味着场景族需要更强的锚点：反复出现的字体、配色、构图或声音母题。

### 3. 选择一条风格路径

用旋钮值在三条路径中选一条：

| 路径 | 何时使用 | Artifact |
|------|----------|----------|
| 现有 playbook | 某个预设确实与判读相符 | `production_plan.playbook` |
| 自定义 playbook | 题材有它自己的视觉世界 | 生成的 `styles/<name>.yaml`，附带 `taste_profile` |
| Atelier 艺术指导 | 旗舰作品需要一套一次性的语言 | `production_plan.art_direction` 加 `taste_profile` |

不要让"有现成预设"压过设计判读。若内容需要一个定制的视觉世界，就去写自定义 playbook 或艺术指导。

### 4. 规划参考

若这项工作用到 AI 图像/视频、情绪板、品牌素材或 atelier composition，就制定一套参考策略：

- 每个场景族或主要节拍用一张参考静图。
- 不要把整套方向压缩进一张情绪板图片里。
- 品牌/产品类工作，在素材生成之前先创建或检视一份品牌套件。
- 屏幕演示类，先检视真实 UI，并在设计叠加层之前写一份改版/审计说明。

### 5. 把档案带向下游

在 proposal 阶段：

- 添加 `production_plan.taste_profile`。
- 在 `decision_log` 中记录风格/playbook 的选择。
- 解释这些旋钮如何影响运行时、合成模式和素材生成。

在场景规划阶段：

- 按 `visual_variance` 变化版式。
- 把屏幕文字和标注控制在 `information_density` 之内。
- 按 `motion_intensity` 设定转场家族和镜头运动。

在 assets 阶段：

- 把配色、质感、构图和参考策略写进图像/视频提示词。
- 当档案依赖视觉细腻度时，先生成参考静图再跑整批。

在 edit/compose 阶段：

- 让停留时长和剪辑律动匹配运动旋钮。
- 不要添加违背设计判读的装饰性叠加层。

## 反默认清单

往前推进之前，先标出这些问题：

- 毫无题材理由的通用 AI 紫色渐变或默认企业蓝视觉。
- 当 `visual_variance` 为 4 或更高时，每个剪辑点却都用同一个转场。
- 让旁白更难跟上的动感运动。
- 当 `information_density` 为 4 或更低时却堆了密集标注。
- 纯文字幻灯片 —— 除非设计判读有意要走排版叙事。
- 看着好看但无法映射到具体场景族的情绪板。
- 从头到尾都没展示或检视过真实品牌/产品界面的品牌/产品视频。

## 复看挂钩

Reviewer 应当检查：

- `taste_profile.design_read` 是否解释了一个真实的创意选择？
- 场景规划和剪辑是否尊重这三个旋钮？
- 反模式是否真的被避免了？
- 当 AI 图像/视频或 atelier 工作依赖视觉细腻度时，参考策略是否到位？
- 把标题换掉之后，这支视频是不是可以属于任何题材？如果是，说明审美方向太笼统了。
