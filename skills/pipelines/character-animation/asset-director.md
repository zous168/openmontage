# 素材导演 —— Character Animation 管线

## 目标

产出包含角色部件、背景、道具、音频、音乐和预览产物的 `asset_manifest`。

## Layer 3 门禁

在编写或生成动画素材之前，读相关的 Layer 3 技能：

- `character-rigging`
- `svg-character-animation`
- `pose-library-design`
- 使用 p5/canvas 特效时读 `canvas-procedural-animation`
- 复看之前读 `character-animation-qa`
- 做 GSAP/Remotion 工作时读 `gsap-core`、`gsap-timeline` 和 `gsap-react`
- 做 Remotion 渲染工作时读 `remotion` 和 `remotion-best-practices`
- 做 HyperFrames 工作时读 `hyperframes` 和 `hyperframes-cli`

在图像/TTS/音乐生成之前，从注册表读取该工具的 `agent_skills`。

## 素材组织

角色素材写入：

```text
projects/<project-name>/assets/characters/<character-id>/
```

使用子目录：

```text
parts/
poses/
previews/
```

生成的背景放在：

```text
projects/<project-name>/assets/backgrounds/
```

## 流程

1. 只生产或取得 `rig_plan` 所需的那些部件。
2. 让每个可动部件保持独立。
3. 部件要保留透明背景。
4. 记录提示词、seed、provider 和模型名称。
5. 在全面铺开素材之前先做一个小预览。

## 质量底线

`rig_plan` 引用的所有部件在 compose 之前都必须存在。缺少部件是
阻塞项，除非动作时间线把需要它们的那个动作删掉了。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
