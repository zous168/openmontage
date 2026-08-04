# 能力扩展协议

## 何时使用

当你遇到现有工具都覆盖不了的制作需求时。agent 可以扩展系统 —— 但要有护栏。本协议取代了那条一刀切的"不要写临时 Python 脚本"规则。

## 先做评估

在动手写任何东西之前，先给这个缺口分类：

| 缺口类型 | 示例 | 措施 |
|----------|---------|--------|
| **一次性变换** | 自定义图像裁切、颜色调整、格式转换 | 写一个项目作用域的 Python 脚本 |
| **反复出现的视觉需求** | 新的插画风格、自定义图表类型 | 生成自定义 playbook 或 Remotion 组件 |
| **缺少 provider** | 用户想用某个不在注册表里的 API | 创建一个最小的工具包装器 |
| **缺少知识** | agent 不知道如何为某个特定模型写提示词 | 用网络检索去学，然后写成一份 Layer 3 技能文档 |

## 临时脚本的规则

**仅**在满足以下全部条件时才允许写脚本：
1. 没有现成工具能覆盖该需求（已通过 preflight 对照注册表核实）
2. 脚本是幂等的（可以安全重跑）
3. 脚本在项目工作区中产出一个文件 artifact
4. 脚本已记入 decision log：`category: "capability_extension"`
5. 已告知用户："我为 X 写了一个自定义脚本，因为没有现成工具能处理 Y"
6. 脚本在未经用户批准的情况下**不**调用外部 API

脚本放在：`projects/<project-name>/scripts/`

**绝不要用脚本来替代管线。** 一个脚本必须只执行**一项**有界的变换（裁切、重命名、格式转换）。它**不得**串联多个管线阶段（例如 assets → edit → compose）、在未经用户批准的情况下把受门禁的检查点写成 `completed`，也不得放在仓库根目录的 `scripts/rerun_*.py`。多阶段生产属于 director 技能 + 注册表工具 + `write_checkpoint`。见 AGENT_GUIDE.md → Pipeline Bypass Prohibition。

仓库根目录的工具（例如只做检查点重置的 `scripts/reset_project_pipeline.py`）是允许的；会生成媒体的绕行脚本必须带上 `OPENMONTAGE_NON_PRODUCTION_SCRIPT` 标记，且仅供维护者自测使用。

```python
"""<一句话描述这个脚本做什么>

由能力扩展协议创建，原因：<为什么没有现成工具能覆盖这件事>
Decision log 条目：<decision_id>
"""
import sys
from pathlib import Path

def main(input_path: str, output_path: str) -> None:
    # 幂等：先检查输出是否已存在
    out = Path(output_path)
    if out.exists():
        print(f"Output already exists: {out}")
        return

    # ... 变换逻辑 ...

    print(f"Created: {out}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

## 自定义 Playbook 的规则

当现有 playbook 都不匹配 brief 时：
1. 用 `lib/playbook_generator.py` 创建一个新 playbook
2. 尽可能以最接近的现有 playbook 为基础
3. 按 `schemas/styles/playbook.schema.json` 校验
4. 保存到 `styles/custom/<project-name>.yaml`
5. 记入决策：`category: "playbook_selection"`、`subject: "custom playbook created"`

## 新技能的规则（技法学习）

当 agent 在网络调研中发现了技法知识时：
1. 把它写成项目作用域的技能：`projects/<project-name>/skills/<name>.md`
2. 遵循 Layer 3 技能格式：
   - provider 名称与版本
   - provider 专属的提示词范式
   - 针对该用途的最佳参数
   - 质量技巧与已知失败模式
   - 信息的来源 URL
3. 在 decision log 中引用它
4. 若它具有普遍价值，建议把它提升到 `.agents/skills/`

## 工具包装器的规则

当用户需要某个不在注册表里的 provider 时：
1. agent 可以创建一个最小的 `BaseTool` 子类
2. 保存到 `projects/<project-name>/tools/<name>.py`
3. 它**必须**继承 `BaseTool` 并实现完整契约（input_schema、execute、capabilities 等）
4. 使用前**必须**先注册
5. 记入决策：`category: "capability_extension"`
6. 首次付费 API 调用之前需要用户批准

## 仍然被禁止的事

- 绕过管线（所有生产仍然要走各阶段）
- 在用户不知情的情况下调用外部 API
- 修改 `tools/` 中的现有工具（写包装器，不要改原件）
- 跳过 decision log
- 编写有超出其输出文件之外副作用的脚本（不发邮件、不推送远端、不删除项目工作区之外的文件）

## Decision Log 条目格式

每一次扩展都必须记录：

```json
{
  "decision_id": "ext-001",
  "stage": "<当前阶段>",
  "category": "capability_extension",
  "subject": "Created custom <script|playbook|skill|tool> for <purpose>",
  "options_considered": [
    {"option_id": "existing-tool", "label": "<最接近的现有工具>", "rejected_because": "<为什么它不行>"},
    {"option_id": "extension", "label": "<创建了什么>", "reason": "<为什么选这个做法>"}
  ],
  "selected": "extension",
  "reason": "<简明的论证>",
  "user_visible": true,
  "confidence": 0.8
}
```
