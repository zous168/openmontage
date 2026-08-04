# VEO 3.1 / VEO 3 —— 提示词指南

> 来源：[Vertex AI 视频生成提示词指南](https://cloud.google.com/vertex-ai/generative-ai/docs/video/video-gen-prompt-guide)
> 通用词汇表见：`skills/creative/video-gen-prompting.md`

**字数：** VEO 3.1 的甜点区间是 100–250 词；更长的提示词不再带来帮助。

## VEO 专属的 14 组件结构

VEO 能响应所有模型中最完整的提示词结构：

1. **Subject（主体）** —— 动作围绕着谁/什么展开
2. **Action（动作）** —— 移动、互动、表情
3. **Scene / Context（场景/背景）** —— 地点、时间、天气、年代
4. **Camera Angles（相机角度）** —— 景别与视角
5. **Camera Movements（相机运动）** —— 动态移动
6. **Lens / Optical Effects（镜头/光学效果）** —— 相机"如何看"
7. **Lighting（光照）** —— 光源、方向、质感
8. **Tone / Mood（基调/情绪）** —— 情绪基调
9. **Artistic Style（艺术风格）** —— 写实、电影感、动画、艺术流派
10. **Ambiance（氛围）** —— 配色、大气效果、质感
11. **Temporal Elements（时间要素）** —— 节奏、时间流动、律动
12. **Audio（音频）** —— 音效、环境声、对白（VEO 3 会生成对白）
13. **Cinematic Terms（电影术语）** —— 剪辑技法（匹配剪辑、蒙太奇、分离柔焦镜）
14. **Negative Prompt（负面提示词）** —— 要排除什么

## VEO 的专属长处

- **对白生成**：VEO 3 原生生成角色语音。自然地写对白即可。
- **音频集成**：环境声、音乐和人声与视频一起生成。
- **负面提示词**：明确支持 —— "no text overlays, no watermarks, no lens flare"
- **剪辑词汇**：能把 "match cut"、"jump cut"、"montage"、"split diopter" 当作提示词术语理解。

### VEO 会照字面执行的镜头词汇

VEO 3.1 区分三个镜头运动家族，并把它们的词当作彼此独立的原语。混淆它们（例如想要 "dolly" 却写了 "zoom"）会得到错误的运动。

- **平移（机位物理移动）：** `dolly`（沿镜头轴推拉）、`truck`（左右横移）、`pedestal`（上下升降）
- **旋转（机位不动，相机转动）：** `pan`（偏航，左右）、`tilt`（俯仰，上下）、`roll`（荷兰角 / Z 轴）
- **纯镜头（机位与机身都不动）：** `zoom`（焦距变化）、`rack focus` / `pull focus` / `focus tracking`（焦平面变化）

dolly ≠ zoom；pan ≠ truck。VEO 会跟随写在前面的那个词。

## VEO 的镜头效果（独有）

VEO 对多数模型会忽略的光学效果有专门响应：

| 效果 | 提示词写法 |
|--------|----------------|
| **Rack focus** | "rack focus from foreground flower to background figure"（快速切换） |
| **Pull focus** | "slow pull focus from the candle in the foreground to the doorway behind"（渐进，比 rack 更慢） |
| **Focus tracking** | "focus tracks the runner as she crosses frame; background stays soft"（焦点跟随移动主体） |
| **变焦推轨（眩晕）** | "vertigo effect as character realizes the truth" |
| **鱼眼** | "fisheye lens distortion, skatepark POV" |
| **变形镜头光晕** | "anamorphic lens flare streaking horizontally from setting sun" |

这三种对焦模式（rack、pull、tracking）是不同的 —— 按论文所述，VEO 3.1 会遵守这个区分。

## VEO 的艺术流派参照

VEO 对具体的艺术流派作为风格锚点响应良好：
- "Van Gogh-inspired swirling sky"
- "Surrealist Dalí-esque melting landscape"
- "Art Deco geometric patterns in the architecture"
- "Bauhaus clean lines and primary colors"
- "Gritty graphic novel illustration style"
- "Chinese ink wash painting animation"

## 防止自动加字幕

VEO 在有对白时可能默认加上字幕。防止办法：
- 在负面提示词里加上："no subtitles, no captions, no text overlays"

## 示例

```
Subject: A lone astronaut in a weathered white spacesuit
Action: Slowly turns to face the camera, visor reflecting a dying star
Scene: Surface of a barren moon, cracked grey terrain, massive ringed
       planet filling the horizon
Camera: Low-angle medium shot, slow arc around subject
Lens: Wide-angle, deep focus keeping both astronaut and planet sharp
Lighting: Harsh rim light from the star behind, cool blue fill from
          planet reflection, no atmosphere diffusion
Mood: Awe, isolation, quiet grandeur
Style: Photorealistic sci-fi cinematography, IMAX-scale
Audio: Breathing inside helmet, faint radio static, low rumble
Negative: No text, no HUD overlay, no lens flare
```
