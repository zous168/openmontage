# 调研导演 —— Character Animation 管线

## 目标

让角色动画方案扎根于真实参考和当下的技法。
对参考视频，从 `video_analysis_brief` 出发：内容、节奏、运动
分类、关键帧、色彩和制作复杂度。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/research_brief.schema.json` | Artifact 校验 |
| 可选上游 | `video_analysis_brief` | 参考片的运动分类与制作复杂度 |

## 流程

1. 弄清参考视频实际用的是什么（无参考时 `reference_motion_type` 填 `none`）：
   - 本地绑定骨骼的动画 → `rigged_local`
   - 逐帧的传统动画 → `frame_by_frame`
   - 视频生成 → `video_generation`
   - 静图运动 → `still_image_motion`
   - 混合技法 → `hybrid`
2. 调研 3-5 个相关案例或技法 → 写入 `comparable_examples`。
3. 把「本管线能在本地复现的」与「需要人工插画、视频生成或
   更大素材库才能做的」区分开 → `manual_asset_risks`。
4. 记录可复用的动画原语 → `reusable_animation_primitives` 与
   `required_character_actions`（走路循环、眨眼、转头、伸手、振翅、
   挤压/拉伸、镜头平移/视差、粒子/天气等）。

### 有参考视频时

若存在 `video_analysis_brief`，**同时**填写 `reference_context`（字段定义见
explainer `research-director` 第 0 步 / `research_brief.schema.json`），
用于题材与角度的差异化；**本管线的制作可行性**仍写在
`character_animation_context` 里，两者不要混用。

## 产出指引

在 `research_brief` 顶层增加 **`character_animation_context`** 对象（本管线
**必填**）：

| Schema 字段 | 含义 |
|-------------|------|
| `character_animation_fit` | `high` / `medium` / `low` —— 题材是否适合本地角色动画 |
| `reference_motion_type` | 参考（或 `none`）的主要运动技法 |
| `required_character_actions` | 脚本/场景需要的角色动作列表 |
| `rig_complexity` | `low` / `medium` / `high` |
| `manual_asset_risks` | 离不开人工或视频生成的环节 |
| `local_runtime_candidates` | 可行的本地 runtime：`remotion` / `hyperframes` / `ffmpeg`（至少 1 个） |
| `comparable_examples` | 至少 3 个可比案例（`title`、`technique`、`takeaway`；`url` 可选） |
| `reusable_animation_primitives` | 可复用的动画原语（可选） |
| `traditional_animation_note` | 参考为手绘/逐帧时，对骨骼方案的能力边界说明（可选） |

其余 `research_brief` 标准字段（`landscape`、`data_points`、`angles_discovered`、
`sources` 等）按 explainer 调研导演的质量底线填写；无参考时可省略
`reference_context`。

提交之前按 `schemas/artifacts/research_brief.schema.json` 校验。

## 质量底线

当参考是手绘或逐帧动画时，必须在 `traditional_animation_note`（或
`manual_asset_risks`）里明确说出来。用户仍然可以选择一种受其启发的本地骨骼
风格，但提案绝不能暗示一个自动骨骼能达到传统动画那样的品质。
