# 监制（Executive Producer）—— Character Animation 管线

## 何时使用

当所要求的交付物依赖可复用的动画角色时使用本管线：卡通短片、
吉祥物讲解、音乐驱动的角色场景、简单角色之间的对白，
或受参考启发的本地动画。

不要把本管线用于没有"表演"的一次性动态图形。那些走
`animation`。也不要用于数字人主持的唇形同步。那些走
`avatar-spokesperson`。

## 契约

本管线产出本地的、确定性的角色动画。它不会静默地
用静图运动来冒充表演。若角色运动无法用现有的骨骼、素材或
运行时构建出来，就上报阻塞项。

## 阶段顺序

1. `research` —— 弄清参考、技法与可行性。
2. `proposal` —— 呈现概念、运行时选项、成本、音乐方案、样片方案。
3. `script` —— 写出适合动作的节拍以及对白/旁白。
4. `character_design` —— 定义角色、剪影、情绪、动作。
5. `rig_plan` —— 定义部件、枢轴、层级、约束、姿势。
6. `scene_plan` —— 把故事节拍映射到角色场景。
7. `assets` —— 生产或取得角色部件、背景、道具、音频。
8. `edit` —— 编排出带时序的动作时间线。
9. `compose` —— 通过已获批的运行时渲染并做 QA。
10. `publish` —— 打包最终产出。

## 治理规则

- 在 proposal 之前运行注册表 preflight。
- 若 Remotion 和 HyperFrames 都可用，在锁定
  `render_runtime` 之前把两者都呈现出来。
- 在全量生成素材之前，先做一段 10-15 秒的样片。
- 角色之间的差异应体现在骨骼数据里，而不是一次性的代码分支里。
- 每一个生成的或在运行时编写的素材，都必须列出已读的 Layer 3 技能。
- 交付之前使用 `character_animation_reviewer`，并做最终的 `final_review`。

## 打回触发条件

- `character_design` 缺少必需的动作或情绪幅度。
- `rig_plan` 缺少可动部件的枢轴。
- `pose_library` 中没有可读的表演姿势。
- `action_timeline` 中存在骨骼渲染不出来的动作。
- compose 使用了 proposal 中未获批的运行时。
