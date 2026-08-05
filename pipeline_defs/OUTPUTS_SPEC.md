# Pipeline Stage Outputs 规范

Flow 节点「看」区 **本节点内容** 只读 `stages[].outputs` 声明（`declaredOutputs`），不在前端另写推断逻辑。

**输入 · 上游产物** = **紧邻上游** `stages[].outputs` 声明（上游输出即下游输入）。Flow 用与「本节点内容」相同的 `declaredFromManifest` 推导。

`required_artifacts_in` 仅用于后端校验，不在输入区单独展示。

## 四种 kind

| kind | 含义 | 配置 |
|------|------|------|
| **text** | **整份产物 JSON** | `label` = artifact 名（与 `produces` 一致），**不写 source** |
| **image** | 图片路径 | `source` 如 `asset_manifest.assets[].path` |
| **video** | 视频路径 | `source` 如 `render_report.outputs[].path` |
| **audio** | 音频路径 | `source` 如 `asset_manifest.assets[].path` |

## text 规则

每个 `produces` 主产物一条 `text`（`decision_log` 除外）：

```yaml
produces:
  - scene_plan
outputs:
  - kind: text
    label: scene_plan
  - kind: image
    label: 参考帧
    source: video_analysis_brief.keyframes[].path
```

## 媒体 source 语法

- 根为 `artifacts` 顶层，**以产物名开头**：`render_report.outputs[].path`
- compose 成片、publish 待审成片均用 `render_report.outputs[].path`（见 `STAGE_MEDIA`）
- publish 导出：`publish_log.entries[].export_path`

## 维护

- **本节点输出**：`outputs`（text + STAGE_MEDIA 媒体项）
- **输入区**：紧邻上游 stage 的 `outputs`

改 `produces` 或媒体规则后：

```bash
python scripts/sync_pipeline_outputs.py
```

`STAGE_MEDIA` 在 `scripts/sync_pipeline_outputs.py` 中维护。
