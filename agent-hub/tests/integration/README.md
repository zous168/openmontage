# Hub ↔ RPA(mock) 业务场景集成测试

按 agent-client 真实功能项组织的 6 渠道业务场景端到端测试，**运营逐步驱动、全程经 mock RPA worker**，CLI 自动化、日志逐步确认。

## 怎么看结果

- **结果报告**：[`last-run-report.md`](last-run-report.md) —— 每次运行自动覆盖生成。含每个业务步骤的
  HTTP 状态、任务终态、是否经 worker、**执行链 steps**（`dispatch(rpa_worker_ws) → mock_cli(cli)`，即过程证据）、业务结果与汇总表。
- **运行过程**：脚本运行时 stdout 实时打印每步 `[✓/✗] 步骤 status worker`。
- **worker 侧日志**：mock_worker 加 `--json-log` 时每行一个 JSON
  （`connected / task.dispatch / task.result`），是 RPA 侧收发的原始证据。
- **hub 侧日志**：agent-hub 控制台输出；单任务过程可查
  `GET /api/plugins/mxai/queue/tasks/{task_id}/steps`。

## 怎么跑

```powershell
# 1) 起 hub（确定性 Mock，不依赖真实 LLM）
$env:MXAI_MOCK='1'; .\scripts\start-agent-hub.ps1 -Env test          # :8642 + 自启 gateway :18789

# 2) 起 mock RPA worker（替代真实 automan，连 hub WS）
agent-hub\.venv\Scripts\python.exe automan\mock-rpa-cli\mock_worker.py --json-log --timeout 0

# 3) 跑业务场景集成测试（生成 last-run-report.md）
$env:HUB_DATA_DIR='C:/ProgramData/MarketingHub'
agent-hub\.venv\Scripts\python.exe agent-hub\tests\integration\scenario_e2e.py
```

退出码 `0` = 全部通过；非 0 = 有步骤未达「已完成且经 worker」。

## 覆盖的业务场景（按 client 功能项）

| 渠道 | 业务场景 | 功能项 |
|------|---------|--------|
| 抖音 | 公域获客漏斗 | 自动首评 → 评论采集 → AI评论回复 → 私信触达 → 入站应答 |
| 小红书 | 种草获客 | 评论采集 → AI评论回复 → 私信触达 |
| 视频号 | 公域获客 | 自动首评 → 评论采集 → AI评论回复 → 私信触达 |
| 个人微信 | 私域培育 | 入站应答 → 批量加好友 → 定时触达 |
| 企业微信 | 客户服务全流程 | 客户接待 → 发送文件 → 批量加客户 → 售后回访 |
| Boss直聘 | 招聘全流程 | 候选人搜索 → 打招呼 → 应聘回复 → 邀约 → 跟进 |

## 已知边界

worker（集成）模式下 `comment_collect` 采集结果**不回写 CRM 线索**（`save_leads` 仅在 hub 内置 fallback 路径）。
故本测试在 setup 阶段用 `save_leads` **预置高意向线索**模拟"采集已发生"，使「AI评论回复」步有合格线索可跑。
真实 automan 集成的"采集→回复"线索落库链路待团队确认。
