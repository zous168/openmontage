# 剪辑导演 —— Cinematic 管线

## 何时使用

本阶段把节拍图转化成一条有节奏的电影感时间线。律动与克制比特效数量更重要。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/edit_decisions.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["assets"]["asset_manifest"]`、`state.artifacts["scene_plan"]["scene_plan"]`、`state.artifacts["script"]["script"]` | 素材、主画面、节拍图 |
| Playbook | 当前生效的风格 playbook | 排版与转场一致性 |

## 流程

### 1. 先按情绪下刀

剪辑点应当跟随：

- 情绪重音，
- 揭示时机，
- 音乐转折，
- 视觉反差。

不要只为信息密度做优化。

### 2. 保护有力的时刻

若一个眼神、一句台词或一个手势正在起作用，就让它活着。不要用额外插入镜头把它覆盖掉。

### 3. 用声音推动剪辑

环境声、冲击音、突然抽空和音乐变化，都应当帮助在场景之间制造势能。

### 4. 用元数据表达时序逻辑

推荐的元数据键：

- `beat_timing`
- `audio_turns`
- `title_card_windows`
- `reframe_notes`

### 5. 质量门

- 情绪弧线完整，
- 揭示落得清楚，
- 标题卡稀疏且时序有意图，
- 有力的时刻没有被大量覆盖镜头淹没。

## 常见陷阱

- 把情绪素材剪得过碎。
- 默认使用变速或花哨的转场。
- 让标题卡取代了剪辑上的清晰表达。
