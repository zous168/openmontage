# OpenMontage 的 B-Roll 规划

> 如何从脚本推导出 B-roll 需求、在素材库与生成素材之间做取舍、
> 构造有效的检索词，以及评估素材质量。

## 何时使用

你正在为一支视频规划视觉素材，需要补充性画面（B-roll）来配合
旁白、交代背景，或增加视觉变化。本技能教你何时该用
素材库、何时该用 AI 生成，以及如何从两者中取得好结果。

## 决策矩阵：素材库 vs 生成

| 场景需求 | 优先用素材库 | 优先用生成 |
|------------|-------------|-----------------|
| 真实世界的定场镜头（城市、办公室、自然） | **是** —— 素材库在这方面很强 | 仅当找不到合适素材时 |
| 现实场景中的人物 | **是** —— 生成的人物常有恐怖谷感 | 仅在使用高质量模型时 |
| 抽象概念的可视化 | 否 | **是** —— AI 能创造现实中不存在的东西 |
| 定制图表/信息图 | 否 | **是** —— 使用 `diagram_gen` 或 `image_selector` |
| 品牌化/风格化图像 | 否 | **是** —— AI 能贴合你的 playbook 风格 |
| 历史/档案影像 | **是** —— 素材库有档案资源 | 否 |
| 特定技术设备 | **是** —— 真实照片更可信 | 仅当该设备并不存在时 |
| 运动/动作片段（海浪、车流、云） | **是** —— 素材视频最适合这个 | AI 视频正在追赶 |
| 隐喻性图像（成长、连接） | 都可以 | **是** —— 创意控制力更强 |

**经验法则：** 若场景需要看起来*真实*，用素材库。若它需要看起来*贴合你的独特概念*，就去生成。

## 从脚本中提取 B-Roll 需求

逐段过一遍脚本。对每一段自问：

1. **旁白在讲什么？** —— 主题本身就暗示了画面。
2. **有增强提示吗？** —— 脚本作者可能已经埋了 `[B-ROLL: ...]` 提示。
3. **这一段是否指向某个具体事物？** —— "数据中心里的服务器" → 服务器的素材片段。
4. **这一段是否在解释一个抽象概念？** —— "算法为每个因素加权" → 生成的图表。
5. **这一段有多长？** —— 决定了所需片段的时长。

### 产出：B-Roll 简报

对每一条识别出的需求，建立一个条目：

```
Scene: s3 (15s-22s)
Need: 现代数据中心的定场镜头
Source: stock
Keywords: ["data center", "server room", "rack servers blue light"]
Duration: 4-6 秒
Orientation: 横屏
Mood: 冷色调、科技感、干净
Fallback: AI 生成的服务器机架图像
```

## 构造有效的素材库检索词

### 检索词构造规则

1. **要具体，但别过分具体。** "aerial city skyline sunset" 有效。"aerial shot of downtown San Francisco financial district at 6:47pm golden hour" 什么也搜不到。

2. **用 2-4 个关键词。** 素材库检索基于关键词，不是语义。词越多，结果越少。

3. **主体放在最前。** 写 "ocean waves"，不要写 "beautiful calm serene ocean waves at dawn"。

4. **把你需要的画面属性写进去：**
   - 俯瞰镜头加 "aerial" 或 "drone"
   - 特写加 "close-up" 或 "macro"
   - 延时素材加 "timelapse"
   - 慢动作片段加 "slow motion"

5. **失败时换同义词。** 若 "programmer coding" 结果不佳，试试 "developer laptop" 或 "software engineer workspace"。

### 按场景类型划分的检索词模板

给每条检索词都加上一个 **POV 关键词**。素材库（Pexels、Pixabay、Storyblocks、Artgrid）会显式索引 POV 术语 —— drone、aerial、OTS（过肩）、macro、top-down、dashcam、FPV、handheld、locked-off —— 而加上 POV 往往比继续打磨主体词更能解锁好结果。CMU/Harvard CHAI 的分类法同样把 POV 视作 Scene 维度的一等要素，原因也在于此：它决定了你在素材库的哪一层货架上搜索。

| 场景类型 | 检索词模板 | 带 POV 的示例 |
|-----------|---------------|---------|
| 定场 | `[地点] [时间] [POV]` | "tokyo skyline night drone" |
| 活动 | `[人物] [动作] [POV]` | "scientist microscope OTS" |
| 物件 | `[物体] [风格] [POV]` | "circuit board macro top-down" |
| 自然 | `[元素] [属性] [POV]` | "ocean waves aerial drone" |
| 抽象运动 | `[运动] [风格] [POV]` | "light trails timelapse locked-off" |
| 职场 | `[场景] [活动] [POV]` | "modern office meeting handheld" |

若场景描述本身没有暗示 POV，就去问脚本/场景导演 —— 不要默认成"无 POV"。POV 选错（场景需要航拍却给了手持）比色调错误更难补救。

## 评估素材库画面的质量

素材工具返回结果后，先评估再使用：

### 图像标准
- **分辨率：** 达到目标（视频画面至少 1080p）
- **相关性：** 确实呈现了场景所需的内容（而不只是命中了关键词）
- **风格兼容：** 与 playbook 的视觉风格不冲突
- **无水印：** Pexels/Pixabay 是免授权的，但仍要确认
- **构图：** 主体取景得当，没有被别扭地切掉
- **POV 匹配：** 素材实际的 POV（drone、OTS、macro、handheld、locked-off 等）是否符合场景所需？POV 错误 —— 例如场景要航拍却给了手持 —— **比色调错误更难补救**。宁可否决并重新检索，也不要指望靠裁剪蒙混过关。

### 视频标准（在图像标准之外还要加上）
- **时长：** 至少不短于场景所需（可以剪短，不能延长）
- **运动：** 平滑，没有突兀的镜头晃动（除非那正是意图）
- **帧率：** 与目标输出匹配（24/30fps 为标准）
- **音频：** 素材视频的音轨通常直接丢弃 —— 不要把它算进考量

### 打分启发式

给每个结果打 1-5 分：
- **5：** 完美匹配，可直接使用
- **4：** 匹配良好，需要轻微裁剪或修剪
- **3：** 可接受，若做调色以贴合 playbook 会更好
- **2：** 勉强 —— 先换关键词再试
- **1：** 不对 —— 与场景完全不符

**阈值：** 使用 3 分及以上的结果。低于 3 分就优化检索词，或改用生成。

## 失败上报

当素材库检索失败（无结果，或全部低于 3 分）时：

1. **换关键词重试** —— 试同义词、更宽泛的词，或换个切入角度
2. **换另一个素材库** —— Pexels 与 Pixabay 的库并不相同
3. **改用 AI 生成** —— 用 `flux_image` 或 `openai_image` 配合场景描述
4. **上报给用户** —— "我没能为 [场景] 找到合适的素材。以下是目前最好的几个选项：[展示结果]。或者我可以改为生成一张图。你倾向哪种？"

只有当素材检索**和**生成兜底都会产出次优结果时，agent 才应该去问用户。多数情况下，兜底链会静默处理掉。

## 署名追踪

Pexels 与 Pixabay 都可免费商用且不强制署名。
不过最佳实践是在 asset manifest 中记录来源：

```json
{
  "id": "broll-scene-3",
  "type": "image",
  "source_tool": "pexels_image",
  "provider": "pexels",
  "attribution": {
    "photographer": "Joey Farina",
    "source_url": "https://www.pexels.com/photo/...",
    "license": "Pexels License"
  }
}
```

这些数据可从工具的返回中取得（`photographer`、`pexels_url` / `page_url`）。把它写进 asset manifest 以保持透明。
