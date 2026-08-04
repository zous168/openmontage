# 发布导演 —— Explainer 管线

## 何时使用

你是一支生成式讲解视频的发布者。你手上有一份含最终视频文件的 `render_report`。你的工作是为分发做准备：生成 SEO 元数据、创作封面图、打包导出，并记录发布事件。

正是在这里，一支好视频抵达它的受众。没有恰当的元数据和打包，再好的内容也会被埋没。

## 前置条件

| 层 | 资源 | 用途 |
|-------|----------|---------|
| Schema | `schemas/artifacts/publish_log.schema.json` | Artifact 校验 |
| 上游 artifact | `state.artifacts["compose"]["render_report"]`、`state.artifacts["proposal"]["proposal_packet"]`、`state.artifacts["research"]["research_brief"]` | 视频文件与原始提案 |
| Playbook | 当前生效的风格 playbook | 封面图的视觉风格 |

## 流程

### 第 1 步：收集上下文

收集元数据所需的一切：
- **提案包**：标题、钩子、关键论点、目标平台、调性
- **渲染报告**：输出路径、时长、分辨率
- **脚本**：用于简介/章节的段落摘要

### 第 2 步：生成 SEO 元数据

**标题**（YouTube 最多 60 字符）：
- 包含提案包中的主关键词
- 以钩子或数字开头
- 避免标题党，但要有吸引力
- 例子："Vector Databases Explained in 60 Seconds" 优于 "About Vector Databases"

**简介**（前 150 字符最关键 —— 会显示在搜索结果里）：
- 开篇一句：重述钩子，附上主要价值主张
- 正文：覆盖的关键话题，自然嵌入相关关键词
- 章节：每个主要段落的时间戳标记（来自脚本段落）
- 行动号召：订阅/点赞/关注
- 链接：视频中提到的相关资源

**标签/关键词**（因平台而异）：
- 5-10 个从提案包 key_points 派生的具体标签
- 宽泛与具体混搭："machine learning" + "vector database tutorial"
- 包含题材、形态（"explainer"）和相关词

**话题标签**（社交平台用）：
- 3-5 个相关话题标签
- 热门与小众混搭

### 第 3 步：生成封面图构想

描述一张能做到以下几点的封面图：
1. 使用 playbook 的视觉风格
2. 用视觉呈现视频的核心概念
3. 包含 3-5 个词的文字（钩子或关键数据）
4. 高对比，在小尺寸下依然可读
5. 文字使用 playbook 的强调色

```json
{
  "thumbnail": {
    "concept": "Split screen: left side shows slow SQL query (red X), right shows fast vector search (green check). Large text: '100x FASTER'",
    "text_overlay": "100x FASTER",
    "style_notes": "Use playbook accent colors, bold Inter font, dark background"
  }
}
```

*注意：真正的封面图生成若 image_selector 可用则由它完成，否则这只是一个供人工制作的构想。*

### 第 4 步：创建章节标记

从脚本段落生成 YouTube 风格的章节：

```
0:00 - Introduction
0:15 - What are Vector Databases?
0:45 - How Embeddings Work
1:20 - The Search Algorithm
1:55 - Real-World Examples
2:30 - When to Use Vector DBs
```

每个章节对应某个脚本段落的 `start_seconds`。

### 第 5 步：打包导出

用 `export_bundle` 工具（capability `publish`）确定性地完成打包 ——
把最终的 `video_path`（来自 `render_report`）、`title`，以及你准备好的元数据
（`description`、`tags`、`hashtags`、`chapters`，以及可选的 `subtitles_path` 和
`thumbnail_path`/`thumbnail_concept`）传给它。
它会布置好导出目录、写出元数据文件，并在 `data["publish_log"]` 中返回一份
符合 schema 的 `publish_log`（`status: "exported"`），由你把它作为本阶段的
artifact 持久化。

它产出这样的结构：

```
exports/
  <project_name>/
    video/
      output.mp4            # 最终渲染的视频（若提供则 subtitles.srt 放在旁边）
    metadata/
      metadata.json         # 全部 SEO 元数据
      chapters.txt          # 章节标记
      description.txt       # 可直接粘贴的简介（含章节）
      tags.txt              # 每行一个标签
    thumbnails/
      concept.json          # 封面图构想（或被复制过来的封面图文件）
```

`export_bundle` 是一个本地、离线的打包器 —— 它不上传。联网的
发布器（例如 YouTube 上传器）应当是一个独立的 `publish` capability
provider。

### 第 6 步：构建 Publish Log

`export_bundle` 已经在 `data["publish_log"]` 中返回了一份符合 schema 的 `publish_log` —— 直接持久化它，不要手工再拼一份。**不要**添加额外的条目字段（schema 设了 `additionalProperties: false`；只允许 `platform`、`status`、`url`、`video_id`、`visibility`、`export_path`、`timestamp`、`metadata_used`、`error`）。它返回的形态是：

```json
{
  "version": "1.0",
  "entries": [
    {
      "platform": "youtube",
      "status": "exported",
      "export_path": "projects/vector-db-explainer/exports",
      "timestamp": "2026-01-15T10:30:00+00:00",
      "metadata_used": {
        "title": "Vector Databases Explained in 60 Seconds",
        "description": "What vector databases are and when to use them.",
        "hashtags": ["#ai", "#vectordb"],
        "chapters": [{ "start_seconds": 0, "title": "Introduction" }]
      }
    }
  ]
}
```

### 第 7 步：自评

打分（1-5）：

| 标准 | 问题 |
|-----------|----------|
| **SEO 质量** | 这个标题和简介在该题材下排名会好吗？ |
| **简介完整性** | 简介是否包含章节、CTA 和关键词？ |
| **封面图构想** | 这张封面在信息流里会突出吗？ |
| **导出包** | 创作者需要的一切都在导出目录里了吗？ |
| **平台匹配** | 元数据是否针对目标平台做了定制？ |

若任何一项低于 3 分，就修订。

### 第 8 步：提交

按 schema 校验 publish_log 并通过检查点持久化。

## 常见陷阱

- **泛泛的标题**："Video About X" 每次都会输给 "X Explained in 60 Seconds"。要具体、要有吸引力。
- **没有章节**：YouTube 奖励带章节的视频。始终加上它们。
- **简介里堆关键词**：先为人写，再为搜索引擎写。用自然语言，把关键词织进去。
- **忘了 CTA**：每份简介都该以一个行动号召收尾。
- **平台格式不对**：YouTube 的简介与 TikTok 的文案不同。要针对目标平台定制。

---

## 门禁提醒（有约束力）

本阶段设人工审批门禁（`human_approval_default: true`）。复看通过之后：
把检查点写成 `status="awaiting_human"`，呈现摘要（Backlot 看板会渲染
artifact），然后**结束你的回合**。不要在同一次回复中开启下一阶段。
审批是逐门禁的 —— 先前的"你继续"不覆盖这道门。
