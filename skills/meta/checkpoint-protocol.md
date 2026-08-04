# 检查点协议 —— 元技能

## 何时使用

在完成某个阶段的工作**并且**通过自评之后。本技能教你何时、如何写检查点，以及何时该请求人工审批。它用一套指令驱动的协议取代了 Python 的 `checkpoint_policy.py`。

检查点是管线的存档点。它们支撑失败续跑、人工监督和审计轨迹。

## 协议

### 第 1 步：查看 manifest 策略

从管线 manifest 中读取当前阶段的配置：

```yaml
- name: idea
  checkpoint_required: true      # 必须写检查点吗？
  human_approval_default: true   # 必须问人吗？
```

| `checkpoint_required` | `human_approval_default` | 措施 |
|----------------------|------------------------|--------|
| true | true | 写检查点 + 呈现给人工审批 |
| true | false | 写检查点 + 自动继续 |
| false | * | 完全跳过检查点（少见） |

### 第 2 步：准备检查点数据

收集检查点所需的一切：

1. **阶段名** —— 刚刚完成的是哪个阶段
2. **状态** —— `"completed"`（或需要审批时为 `"awaiting_human"`）
3. **Artifacts** —— 该阶段产出的规范 artifact
4. **元数据** —— 自评发现、成本快照、耗时信息

### 第 3 步：写检查点

调用检查点工具：

```python
write_checkpoint(
    pipeline_dir,      # 项目工作目录
    project_name,      # 项目标识
    stage_name,        # 例如 "idea"
    status,            # "completed" 或 "awaiting_human"
    artifacts,         # {"brief": {...}} —— 该阶段的输出
)
```

检查点工具会：
- 按 schema 校验 artifact
- 强制执行审批门禁（受门禁的阶段在没有 `human_approved=True` 时不能写成 `completed`）
- 把被取代的检查点归档到 `projects/<id>/history/`（阶段版本与门禁变迁永不销毁）
- 把检查点 JSON 写入磁盘
- 附上时间戳与阶段元数据

规范位置：`projects/<project_id>/checkpoint_<stage>.json` —— 始终把仓库的
`projects/` 目录作为 `pipeline_dir` 传入（或使用
`lib.checkpoint.PROJECTS_DIR`）。始终传 `pipeline_type` —— 门禁执行
要通过它来读取 manifest。

在管线初始化时（任何阶段之前）调用 `init_project()`：

```python
from lib.checkpoint import init_project
init_project("my-project", title="My Project", pipeline_type="cinematic")
```

这会创建规范的目录布局并写出 `project.json` —— 这是 Backlot 看板在
第一个检查点出现之前显示该项目所需的标记文件。然后启动看板：`python -m backlot open my-project`
（不可用时不致命 —— 看板只是观察者，绝不是阻塞项）。

### 第 4 步：阶段内检查点（续跑支持 + 存活信号）

**进入任何阶段时，先写一个 `in_progress` 检查点。** 正是它告诉用户
（通过 Backlot 看板）这个阶段是活着的、而不是卡住了 ——
确定性比速度更重要。

长时间运行的阶段（如 `assets` 或 `compose` 循环）可能因 API 错误、限流或会话中断而中途失败。为了能从确切的失败点（例如第 4 个场景）续跑：

1. **写入部分进度**：每当你成功生成一个有意义的单元（例如某个场景的素材、一个片段），就写一个 `in_progress` 检查点。

   `in_progress` 检查点可以省略该阶段的规范 artifact，但任何以已知 artifact 名存放的内容仍会按 schema 校验。若部分数据还不是合法的规范 artifact，就把它存进 `metadata.partial_progress`，而不是 `artifacts`。
   ```python
   write_checkpoint(
       pipeline_dir, project_name,
       stage="assets",
       status="in_progress",
       artifacts={},  # 尚无完整的规范 artifact
       metadata={
           "partial_progress": {
               "asset_manifest_draft": partial_manifest_dict,
               "completed_scene_ids": completed_scene_ids,
           }
       },
   )
   ```
   若部分 artifact 已经满足其 schema（例如一个带 `version: "1.0"` 和合法 `assets[]` 条目的 `asset_manifest`），就可以直接放进 `artifacts`。
2. **从部分进度续跑**：开始某个阶段时，**始终**检查是否已存在该阶段的 `in_progress` 检查点。处理方式见第 7 步（续跑协议）。

### 第 5 步：人工审批（若需要）

**manifest 中的取值具有约束力。** 管线 manifest 中的
`human_approval_default` 是"某阶段是否设门禁"的唯一事实来源。本技能
从不推翻它，你也不行 —— 不存在"这次情况特殊"。
（`lib/checkpoint.py` 会强制执行：为受门禁的阶段写 `status="completed"` 而
没有 `human_approved=True` 时，会抛出 `GATE VIOLATION` 错误。）

当 `human_approval_default: true` 时：

1. **把检查点写成 `status="awaiting_human"`**（不是 `completed`）。

2. **向人工呈现一份摘要**：
   ```
   ## 阶段完成：[stage_name] —— 等待你的审批

   ### Artifact 摘要
   [artifact 的关键细节 —— 标题、时长、关键决策]
   [若 Backlot 看板正在运行，指向它：artifact 会在那里渲染]

   ### 自评发现
   [reviewer 的摘要：N 个 critical（已全部修复）、N 条建议]

   ### 目前成本
   [已花费 / 总预算，按工具拆分]

   ### 需要你做的事
   请审阅并批准以继续，或给出修改意见。
   ```

3. **结束你的回合。** 在同一次回复中做任何进一步的管线工作，都属于
   门禁违规。"呈现完就继续"不算等待 ——
   这一回合必须以提问结束，下一个管线动作必须是由
   用户的回复触发的。

4. **收到用户回复后：**
   - **批准** → 把检查点重写为 `status="completed"`、
     `human_approved=True`，然后进入下一阶段
   - **要求修改** → 带着人工反馈回到该阶段的 director 技能，
     产出修订后的 artifact，重新自评，重新写检查点
     （被取代的检查点会自动保留在 `history/`）
   - **中止** → 停止管线

5. **审批是逐门禁的。** 先前的批准，无论说得多宽泛（"看着挺好，
   你继续把整个做完吧"），都不覆盖后面的门禁。若用户
   明确对整轮运行做了预授权，就在他们说出那句话的当下把它
   记成一条 `decision_log`（`category: "approval_policy"`）—— 没有那条记录，
   就在每个门禁处停下。

6. **assets 门禁审的是分镜 —— 在任何草稿渲染之前。**
   现在每条管线的 `assets` 都设门禁：逐场景呈现生成的素材
   （Backlot 看板的胶片条是天然的复看界面），
   包括目前花费和预计的 compose 成本。在这里抓出一个
   坏素材，能省下一次完整重渲染。

   **不要为了换取这次复看而去渲染草稿/完整 composition。** 复看的
   界面是填满了逐场景素材的胶片条 —— 素材库选图、生成的静图、旁白波形 ——
   **而不是**一支渲染好的视频。对于那些"素材"本身是定制/atelier
   composition 的场景（没有可缩略的文件），
   agent 要为每个场景写一张**复看用静帧**到
   `projects/<id>/snapshots/<scene_id>.png`（在有代表性的帧上跑一次
   `remotion still` —— 见 `skills/meta/bespoke-composition.md`）；看板
   会把它们显示在胶片条上。静帧陆续落盘时刷新 `metadata.partial_progress`，
   然后在门禁处**停下**。草稿/最终渲染属于 **compose**
   阶段 —— 它只在 assets 门禁获批之后才运行。在 assets 阶段内渲染完整
   草稿，就是越过了本该由用户把守的那道门。

### 第 6 步：确定下一个阶段

检查点写好并（如需要）获批之后：

```python
next_stage = get_next_stage(pipeline_dir, project_name)
```

它会读取所有已有检查点，返回下一个需要运行的阶段；若管线已完成则返回 `None`。

### 第 7 步：续跑协议

在**任何**管线运行的开始（不只是某个阶段之后），始终检查是否已有进度：

```python
next_stage = get_next_stage(pipeline_dir, project_name)
```

若 `next_stage` 不是第一个阶段：
1. 告知人工："发现已有进度。从阶段 [next_stage] 续跑"
2. **检查部分进度**：读取 `next_stage` 的检查点：
   ```python
   current_cp = read_checkpoint(pipeline_dir, project_name, next_stage)
   ```
   若 `current_cp` 存在且状态为 `"in_progress"`，告知人工你正在从该阶段中途续跑。
3. **加载 artifact**：从检查点加载先前的 artifact 作为上下文。若从 `"in_progress"` 续跑，先从 `current_cp["artifacts"]` 加载任何符合 schema 的部分 artifact。若部分数据存放在 `current_cp["metadata"]["partial_progress"]`，就使用那份草稿数据及其完成标记（例如 `completed_scene_ids`）来跳过已完成的子任务。
4. **继续**：从下一个尚未成功的步骤继续生成，把结果追加到部分 artifact 中。

若存在状态为 `"awaiting_human"` 的检查点：
1. 告知人工："阶段 [name] 正在等待你的审批"
2. 呈现检查点数据供审阅
3. 在继续之前等待批准

### Sample 检查点（reference-driven 类生产）

当一次生产是 reference-driven 时（存在 VideoAnalysisBrief），在
proposal 获批与全量生产之间会多出一道检查点：

| 阶段 | checkpoint_required | human_approval_default | 备注 |
|-------|--------------------|-----------------------|-------|
| `sample` | true | true | 始终需要人工审批 |

Sample 检查点：
1. 呈现：渲染好的样片（10-15 秒）
2. 成本：样片成本 vs 预计的整片成本
3. 措施：批准（→ 进入 script）、修改（→ 重新生成样片）、中止

Sample 检查点**不是**一个管线阶段 —— 它是 proposal 阶段内部的
子检查点。它不产出规范 artifact。它产出一段渲染好的
预览片，存放在 `projects/<name>/assets/sample/sample_v{N}.mp4`。

**呈现格式：**
```
## 样片已就绪

**样片文件：** [sample_v1.mp4 的路径]
- 时长：[X] 秒（钩子 + 1 个中段场景）
- 配音：[TTS provider + 音色名]
- 画面：[说明 —— AI 图像、Remotion 动画等]
- 音乐：[来源]

**样片成本：** $[X.XX]
**预计整片成本：** $[X.XX]

感觉对吗？我可以调整：配音、视觉风格、节奏、音乐、配色。
```

## 关键原则

1. **已完成的工作一律写检查点。** 即便 `checkpoint_required: false`，若该阶段耗费了大量时间或成本，也值得写一个。丢掉工作比磁盘上多一个文件糟糕得多。

2. **创意阶段绝不跳过人工审批。** `idea` 和 `script` 决定了后面的一切。为了省时间而匆匆略过，产出的会是没人想要的视频。

3. **附上成本快照。** 在批准昂贵的下游阶段（assets、compose）之前，人工应当知道已经花了多少、还剩多少。

4. **检查点让续跑成为可能。** 若管线在 `compose` 崩溃，人工可以重启并从 `compose` 接着跑 —— 而不是从 `idea` 重来。这正是检查点的全部意义。

5. **请求审批时要透明。** 不要只把 artifact 摆出来 —— 把自评发现、成本和任何担忧一并给出。帮助人工做出知情的决定。
