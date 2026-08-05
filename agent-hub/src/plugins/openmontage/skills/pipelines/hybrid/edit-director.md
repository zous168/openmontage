# 剪辑导演 —— Hybrid 管线

## 何时使用

本阶段为一支带辅助元素、源素材主导的视频建立分层剪辑逻辑。顺序很重要：先主线剪辑，后辅助层。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["assets"]["asset_manifest"]`、`state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]` | 源/辅助素材与时间线意图 |
| Playbook | 当前生效的风格 playbook | 排版与运动的一致性 |

## 流程

### 1. 先锁定主线剪辑

在加入辅助叠加层之前，观众就应当能看懂这个故事。若主线剪辑本身就弱，辅助层救不了它。

### 2. 按优先级加辅助层

典型顺序：

1. 字幕，
2. 说话人或背景标签，
3. 图解或数据卡，
4. 可选的插入镜头，
5. CTA 元素。

### 3. 保住可读性

绝不要在同一时刻堆太多辅助层。若字幕、标签、图表和叠加层撞在一起，就做减法。

### 4. 用元数据表达分层逻辑

推荐的元数据键：

- `anchor_cut_notes`
- `layer_order`
- `overlay_windows`
- `variant_edit_rules`

### 5. 质量门

- 主线剪辑单独看也成立，
- 辅助层是在澄清而不是在分散注意力，
- 移动端可读性没有被牺牲，
- 各变体保持一致。

## 常见陷阱

- 试图用额外图形去补救一个弱剪辑。
- 让辅助层与源素材争夺注意力。
- 把每个平台变体当成一套独立的剪辑哲学来做。
