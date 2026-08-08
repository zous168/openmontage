# agent-hub

Hermes Agent **源码集成**后端：Gateway、Agent 运行时、CLI、插件与 MxAI 业务扩展。与桌面客户端 **agent-client** 通过 localhost HTTP/WebSocket（默认 **8642**）通信。

> **启动**：`.\scripts\start_dev.cmd`（dev / test / prod 三档），或仓库根统一入口 `scripts\start-agent-hub.ps1` → http://127.0.0.1:8642。停止 `.\scripts\stop_dev.ps1`，播种演示数据 `.\scripts\seed-demo.ps1`。总览见 [../scripts/README.md](../scripts/README.md)。
>
> **Agent CLI（默认对话，含 OpenMontage `om_*`）**：仓库根 `.\start_agent_cli.cmd`，或本目录 `.\scripts\start_agent_cli.cmd`（可选 `-Tui` / `-Query "..."`）。数据面默认仓库根 `.data`。
>
> **打包**：`..\scripts\build-hub.ps1 -Stage` → 单文件 `agent-hub.exe`（onefile，~133MB，作 MxAI sidecar）。冻结入口 `packaging\hub_entry.py` + `agent-hub.spec`。详见 [../docs/打包规范.md](../docs/打包规范.md)。

## 目录（`src/`）

| 目录 | 说明 |
|------|------|
| `gateway/` | 消息网关与 WS 推送；调试入口 `python -m gateway.run` |
| `agent/` | 对话循环、工具执行、记忆、`profile_scope` |
| `hermes_cli/` | `hermes` CLI、Profile/看板/Gateway 子命令 |
| `plugins/` | 插件总线挂载点（见下表） |
| `core/platform/` | 本机 IPC、设备鉴权、租户 ContextVar |
| `middlewares/` | Trace 中间件 |
| `tools/` `skills/` `cron/` | Hermes 内置能力与定时任务 |
| `main.py` | 组合 ASGI：`hermes_cli.web_server` + `core.platform` |
| `runtime_paths.py` | `HUB_DATA_DIR` 解析与启动引导 |

### 主要 MxAI 插件（`src/plugins/`）

| 插件 | 说明 |
|------|------|
| `hub-knowledge/` | 知识库检索、切片、入库 API；数据 SSOT：`{HUB_DATA_DIR}/hub.db` |
| `hub_crm/` | CRM 只读/管理路由（依赖 `src/hub` 仓储） |
| `hub_materials/` | 物料与对象存储桥接 |
| `browser/` `kanban/` `memory/` | Hermes 上游：浏览器 RPA、看板、记忆 |

## 运行期数据

与 Agent 共用 **`HUB_DATA_DIR`**（Windows 默认 `C:\ProgramData\MarketingHub`）。  
**不使用** `HERMES_HOME` 或 `~/.marketing_hub/`。

解析顺序见 `src/runtime_paths.py`。

## 本地开发

**前置条件**

- Python **3.12+**（完整 Hermes 依赖建议 3.12；3.14 可跑通子集）
- [uv](https://docs.astral.sh/uv/) 包管理

**安装依赖**（SSOT：`pyproject.toml` + `uv.lock`）

```powershell
cd agent-hub
uv sync
```

> 含 Dashboard / Agent 所需：`fastapi`、`uvicorn`、`httpx`、`requests`、`openai`、`pywinpty`（Windows）等；见 ``pyproject.toml`` 的 ``[project.dependencies]``。

> 本机 IPC / 设备鉴权在 ``core.platform`` + ``hermes_cli.dashboard_auth``；``HERMES_DASHBOARD_GATED`` 默认开启。

**环境变量（常用）**

```powershell
$env:HUB_DATA_DIR = "C:\ProgramData\MarketingHub"
$env:PYTHONPATH = ".\src"   # 从 agent-hub 目录运行
# 开发 ai_worker 凭据（可选，配合 /login 页；默认见 .env.dev 种子）
$env:HUB_DEV_SEED_AI_WORKER_LOGIN = "aw_1d8c23200075fe43bf0881c5"
$env:HUB_DEV_SEED_PASSWORD = "Seed@Pass123"
```

> ``HERMES_DASHBOARD_GATED`` **默认开启**；IPC token 落在 ``{HUB_DATA_DIR}/device/local_ipc.token``。显式 ``=0`` 可关闭 gated。
> ``HERMES_GATEWAY_AUTOSTART`` **默认开启**；起 Dashboard 时自动拉起 Gateway 子进程（``=0`` 关闭）。

**启动**

```powershell
cd agent-hub   # 仓库根下
$env:HUB_DATA_DIR = "C:\ProgramData\MarketingHub"
$env:PYTHONPATH = ".\src"   # 从 agent-hub 目录运行
uv run python -m uvicorn main:app --host 127.0.0.1 --port 8642 --reload
```

健康检查：`GET http://127.0.0.1:8642/health`

## 与设计文档

结构约定 → [docs/marketing-hub-design/11-项目结构与目录设计.md](../docs/marketing-hub-design/11-项目结构与目录设计.md) §3、§4。
