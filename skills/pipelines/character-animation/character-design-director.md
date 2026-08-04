# 角色设计导演 —— Character Animation 管线

## 目标

产出 `character_design`：一组小规模角色阵容，各自有清晰的剪影、定位、
情绪、动作和风格锚点。

> **手绘墨线"涂鸦"角色？**（一个会自己画出来、然后走路 / 跳舞 / 挥手 / 跳跃的火柴人或铅笔人）→ 使用 **Ink Puppet** 系统：`skills/creative/ink-theater.md` + `ink-theater/README.md`。这套骨骼与身材比例无关，并通过 `InkPuppet.choreograph([{clip:'wave'},{clip:'twist'},…])` 播放**真实动捕**片段 —— 片段名来自 `ink-theater/mocap/catalog.json`（12 个来自 CMU 的动作）；agent 只负责挑选具名动作，**绝不手工调运动**；用 `node ink-theater/mocap/add-motion.mjs` 添加新动作。命令：`/ink-art`。

## 流程

1. 列出每个角色的 `id`、定位、体型和风格。
2. 找出这个故事所需的最小情绪幅度。
3. 找出这个故事所需的最小动作清单。
4. 决定需要哪些视角：正面、四分之三、侧面、背面。MVP 保持在一到两个视角。
5. 记下附着在角色身上的道具，例如围巾、羽毛、包、眼镜。

## 约束

- 一到两个角色是 MVP 的甜点。
- 动物角色需要物种专属的部件和动作循环。
- 视角越多，素材和姿势需求成倍增加。
- 不要发明超出已获批时长所能用到的姿势数量。

## 工具使用

用 `character_spec_generator` 起结构化草稿。只有在视觉风格和角色设定表
要求都明确之后，才使用 `image_selector`。使用图像生成之前，
先从注册表读取该工具的 Layer 3 技能。

## 质量底线

只有当动画师或工具能据此推断出必须存在哪些部件、
表情和动作时，这份角色设计才算就绪。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
