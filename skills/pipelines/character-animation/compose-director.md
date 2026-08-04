# 合成导演 —— Character Animation 管线

## 目标

渲染已获批的角色动画，并证明它经过了复看。

## 运行时路由

先读 `edit_decisions.render_runtime`。除非有一条 `render_runtime_selection`
决策明确更改过它，否则它必须与 proposal 中锁定的运行时一致。

- `remotion`：把素材暂存到 `remotion-composer/public`，构建 composition
  JSON，通过 `video_compose` 渲染。
- `hyperframes`：物化一个 HyperFrames 工作区，让 `video_compose`
  委派给 `hyperframes_compose`。`hyperframes lint` 和 `validate` 都必须通过。
- `ffmpeg`：只用于后期处理或简单的视频装配；单靠它不足以
  完成角色表演。

## 复看流程

1. 运行 `character_rig_renderer` 生成或刷新 HyperFrames 包。
   浏览器预览只是 QA/调试产物，不是渲染路径。
2. 确认渲染器输出了 HyperFrames 的 `workspace_path`、composition HTML、
   `asset_manifest`，以及 `edit_decisions.render_runtime: "hyperframes"` 的交接。
3. 针对骨骼、姿势、时间线和预览运行 `character_animation_reviewer`。
4. 使用渲染器的交接结果或已获批的 Remotion/HyperFrames 包，通过 `video_compose`
   渲染最终视频。交付路径是
   `projects/<project-name>/renders/final.mp4`，与 OpenMontage 标准
   项目约定一致。
5. 运行标准的 `final_review`：ffprobe、抽帧、视觉抽查、音频
   抽查、承诺保持。

## 浏览器 QA

当 Playwright 可用时：

- 打开预览，
- 捕获开头/中间/结尾的帧，
- 检查控制台错误，
- 确认角色可见，
- 比较帧差以确认确实存在运动。

当 Playwright 不可用时，改用静态产物检查和 FFmpeg 抽帧，
并报告这样做置信度会下降。

## 质量底线

当 `character_qa_report.status` 为 `revise` 或 `fail` 时，
不要把产出当作已完成呈现出去。
