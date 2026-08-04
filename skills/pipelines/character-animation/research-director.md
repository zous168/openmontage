# 调研导演 —— Character Animation 管线

## 目标

让角色动画方案扎根于真实参考和当下的技法。
对参考视频，从 `video_analysis_brief` 出发：内容、节奏、运动
分类、关键帧、色彩和制作复杂度。

## 流程

1. 弄清参考视频实际用的是什么：
   - 本地绑定骨骼的动画，
   - 逐帧的传统动画，
   - 视频生成，
   - 静图运动，
   - 混合技法。
2. 调研 3-5 个相关案例或技法。
3. 把"本管线能在本地复现的"与"需要人工插画、视频生成或
   更大素材库才能做的"区分开。
4. 记录可复用的动画原语：
   - 走路循环，
   - 眨眼，
   - 转头，
   - 伸手，
   - 振翅，
   - 挤压/拉伸，
   - 镜头平移/视差，
   - 粒子/天气。

## 产出指引

`research_brief` 应当包含：

- `character_animation_fit`：high/medium/low，
- `reference_motion_type`，
- `required_character_actions`，
- `rig_complexity`，
- `manual_asset_risks`，
- `local_runtime_candidates`。

## 质量底线

当参考是手绘或逐帧动画时，要明确说出来。用户仍然可以
选择一种受其启发的本地骨骼风格，但提案绝不能暗示一个自动骨骼
能达到传统动画那样的品质。
