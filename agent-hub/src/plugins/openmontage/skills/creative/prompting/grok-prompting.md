# Grok 提示词

当选定的 provider 是 `grok_image` 或 `grok_video` 时使用本文。

## Grok 是正确选择的场景

- 你需要编辑一张已有图像，而不是从零生成
- 你需要把多张源图合并成一张输出
- 你需要一段受参考图影响、但不锁定首帧的短视频
- 你希望图像和视频用同一个 provider，提示词语言也相近

## Grok Image

### 最佳提示词结构

```
[主体] + [动作或改动] + [环境] + [一个风格锚点] + [光照]
```

### 编辑类提示词

做图像编辑时，直接描述想要的变换：

- "Render this as a pencil sketch with detailed shading."
- "Replace the plain t-shirt with a dark green bomber jacket."
- "Combine these two people into the same sunny park scene."

除非保持原样至关重要，否则不要把每个不变的细节都写一遍。

### 多图合成

告诉 Grok 如何组合这些输入：

- 谁来自哪张源图
- 什么应当保持分离
- 最终场景发生在哪里

示例：

```
Place the person from image 1 and the person from image 2 on the same subway platform at dusk,
standing shoulder to shoulder, cinematic sodium-vapor lighting, realistic photography.
```

## Grok Video

### 最佳提示词结构

```
[景别] + [镜头运动] + [主体] + [主要动作节拍] + [环境] + [光照] + [基调]
```

### 参考图驱动的视频

Grok 支持在提示词中用 `<IMAGE_1>` 这类占位符指代源图。
当你需要保持人物身份、服装或产品的一致性时使用它。

示例：

```
Medium full shot, slow push-in. The model from <IMAGE_1> walks onto a clean white runway wearing
the jacket from <IMAGE_2>. Soft studio lighting, premium fashion campaign, confident expression.
```

### 图生视频 vs 参考图生视频

- 当源图应当充当开场画面时，用图生视频。
- 当源图应当影响内容但不冻结构图时，用参考图生视频。

## 常见错误

- 把 Grok 的参考图当成严格的分镜。它们是影响性输入，不是精确的画面锁定。
- 在一次片段请求里写进多个场景切换。
- 堆了太多风格标签，却几乎没有场景信息。
- 用 "make it better" 这类含糊的编辑提示词，而不说清要改什么。

## OpenMontage 指引

- 图像编辑或合成，优先用 `grok_image`，而不是 selector 默认的主力工具。
- 参考图约束的视频，当 brief 依赖把输入图中的人物、服装或产品带入运动时，优先用 `grok_video`。
- 若交付物是纯粹的电影感运动、没有参考图约束，那就在锁定 provider 之前把 Grok 与 Runway、Veo、Kling 做个比较。
