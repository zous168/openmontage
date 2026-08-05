# 剪辑导演 —— Animation 管线

## 何时使用

本阶段把场景方案转化成一份动态分镜级别的剪辑方案。时序就是产品本身。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["assets"]["asset_manifest"]`、`state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]` | 素材、时序方案与节拍 |
| Playbook | 当前生效的风格 playbook | 运动与排版规则 |

## 流程

### 1. 保护停留时长

在关键揭示之后，给观众留出足够时间去消化这一帧。不要把每个场景都塞满、首尾相接全是运动。

### 2. 让次要元素错峰

主元素先，辅助元素后。剪辑决策应当强化层级关系。

### 3. 让运动有意义

运动应当传达：

- 强调，
- 转场，
- 变形，
- 对比。

### 4. 用元数据表达时序细节

推荐的元数据键：

- `hold_windows`
- `stagger_rules`
- `transition_map`
- `scene_timing_notes`

### 5. 质量门

- 关键信息有足够的停留时间，
- 运动澄清了层级关系，
- 转场保持一致，
- 剪辑在目标平台上依然可读。

## 常见陷阱

- 用连续不断的运动把时间线塞满。
- 一次性揭示所有元素。
- 让风格化的运动损害了可读性。
