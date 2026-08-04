# 创意导演 —— Animation 管线

## 何时使用

当视频主要靠设计出来的运动来构建时使用本管线：动态图形、动态排版、图解主导的讲解、数学视觉，或插画式动画。

若项目其实是素材主导、只加了几个叠加层，就不要用本管线。那属于 `hybrid`。

## 参考输入

- `docs/animation-best-practices.md`
- `skills/creative/animation-pipeline.md`
- `skills/creative/storytelling.md`
- `skills/creative/ink-theater.md` —— 用于手绘**墨线"涂鸦"** 类 brief：一个会自己画出来并表演的角色，或一个面无表情的装置讲解（Ink Theater 引擎 + Ink Puppet 动捕；命令 `/ink-art`）。会走路或跳舞的火柴人/铅笔角色属于 `character-animation` 管线。

## 流程

### 1. 归类动画模式

选定主模式：

- `diagrammatic`
- `motion_graphics`
- `kinetic_type`
- `math_animation`
- `illustrative`
- `mixed_animation`

### 2. 尽早确定视觉路径

搞清楚该由哪些工具来干活：

- `diagram_gen`
- `math_animate`
- `code_snippet`
- `image_selector`
- `video_selector` 或某个具体的视频 provider 工具
- 源素材提供的美术资源

若所请求的模式依赖不可用的工具，立刻在 brief 的元数据中说明。

### 3. 选定复用策略

当每个场景都独一无二时，动画就会变得昂贵。定义：

- 反复出现的母题，
- 版式体系，
- 转场家族，
- 排版层级。

### 4. 构建 Brief

推荐的元数据键：

- `animation_mode`
- `visual_path`
- `narration_strategy`
- `reuse_strategy`
- `timing_style`
- `blocked_capabilities`

### 5. 质量门

- 动画模式明确，
- 视觉路径可行，
- 项目是为复用而设计的，
- brief 对缺失的工具如实说明。

## 常见陷阱

- 把所有动画当成一个笼统的类别。
- 为每个场景都规划定制视觉。
- 把缺失的工具路径藏到 assets 阶段才暴露。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
