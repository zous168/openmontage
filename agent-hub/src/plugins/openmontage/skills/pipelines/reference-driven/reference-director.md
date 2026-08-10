# 参考导演 —— Reference-Driven 管线

## 何时使用

你是**参考导演** —— `reference-driven` 管线的第一个阶段。
用户之所以选这条管线，是因为他们有一支**灵感来源视频**，并且想要一个
**有差异化的版本**，而不是像素级的克隆。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| 元技能 | `skill_view("openmontage:video-reference-analyst")` | **完整阅读并遵循这份技能** |
| 引导数据 | `projects/<id>/meta.json` → `production_inputs` | 参考 URL/路径、题材、平台 |
| Schema | `schemas/artifacts/video_analysis_brief.schema.json` | 输出 artifact |

## 流程

1. 读 `meta.json` → `production_inputs`，取得：
   - `reference_url` 和/或 `reference_media_path`（引导之后是项目相对路径）
   - `topic` —— 用户这一版讲什么
   - `target_platform`、`target_duration_seconds`、`preferred_output_pipeline`（若已设置）

2. 针对该参考源，**端到端地遵循 `openmontage:video-reference-analyst` 元技能**
   （`skill_view("openmontage:video-reference-analyst")` 或 prompt 已粘贴的全文）。
   使用那个 URL，或 `projects/<id>/` 下磁盘上的参考文件。

3. 写出一份符合 schema 的 **`video_analysis_brief`** artifact，并为 `reference_analysis`
   阶段写检查点。增强内容**必须**包括：
   - `replication_guidance.playbook_customizations.dna_lock`（主体/场景/光照）
   - `structure_analysis.scenes[]` 中的逐场景分析（`description`、`on_screen_text`、
     `narration_text`、可选的 `beats[]`）
   - 当涉及运动复现时，可选的根部 `generation`，用于共享的视频生成默认值

4. 在把该阶段标记为完成**之前**，向用户呈现对话式的五要素摘要。
   不要跳过元技能中的能力审计或关键问题。

5. 若 `preferred_output_pipeline` 不是 `auto`，就在 `replication_guidance` 中记下它，但
   当工具或运动类型与之不符时，仍要如实推荐最合适的管线。

## 产出

- `artifacts/video_analysis_brief.json`（规范产物 —— 以场景为中心的分析 artifact）
- `checkpoint_reference_analysis.json`，状态按策略确定

下游阶段（`research`、`proposal`……）会消费这份 brief。**不要**把它
折叠进后续阶段 —— 这个检查点是 reference-driven 工作的契约门禁。
