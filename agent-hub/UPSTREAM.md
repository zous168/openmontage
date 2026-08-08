# agent-hub 上游台账

`agent-hub/` 是 [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent) 的**深度分叉**，
原本作为 MxAI（Marketing Hub）后端维护，2026-08 并入 OpenMontage 仓库统一跟踪。

本文件是回溯上游变更的唯一依据，改动 `src/` 下内核文件时请同步更新。

## 上游锚点

| 项 | 值 |
|---|---|
| 上游仓库 | `github.com/NousResearch/hermes-agent` |
| 分叉版本 | `0.16.0`（见 `src/hermes_cli/__init__.py` 的 `__version__`） |
| 分叉 commit SHA | **不可考** |

SHA 不可考的原因：这份代码在并入本仓库前没有独立的 `.git`，也不是 submodule，
是以纯文件形式从 MxAI 仓库移植过来的，上游提交历史随之丢失。
`0.16.0` 是唯一可靠的版本锚点。

若将来需要与上游对齐，建议先 clone 上游 `v0.16.0` 标签做一次三方 diff 重建基线，
再把下方登记的改动逐块 rebase。

## 分叉规模

| 指标 | 数值 |
|---|---|
| `src/` 下 Python 文件 | 745 |
| `src/` 下 Python 行数 | 约 496,000 |
| 含 MxAI / Marketing Hub 标记的文件 | 201 |

这不是一层薄封装，而是贯穿内核的改造。升级上游需要按模块评估，不存在无冲突的整体合并。

## 被改动的内核区域

按 MxAI 标记（`MxAI`、`marketing_hub`、`HUB_DATA_DIR`、`营销中枢` 等）统计的文件分布：

| 目录 | 文件数 | 说明 |
|---|---|---|
| `src/hermes_cli/` | 55 | CLI、Dashboard、Profile、Gateway 子命令 |
| `src/agent/` | 29 | 对话循环、工具执行、记忆、`profile_scope` |
| `src/tools/` | 29 | Hermes 内置工具 |
| `src/gateway/` | 10 | 消息网关与 WS 推送 |
| `src/hermes_cli/web_routes/` | 10 | Dashboard 路由 |
| `src/hermes_cli/subcommands/` | 7 | CLI 子命令 |
| `src/tools/environments/` | 6 | 工具运行环境 |
| `src/core/platform/device/` | 5 | 本机 IPC 与设备鉴权（MxAI 新增） |
| `src/hermes_cli/dashboard_auth/` | 4 | Dashboard 鉴权（MxAI 新增） |
| `src/gateway/platforms/` | 4 | 平台适配器 |
| 其余 | 42 | cron、acp_adapter、plugins/platforms 等 |

### 最主要的语义改动

**数据根**：上游用 `HERMES_HOME` / `~/.hermes`，本分叉改为 `HUB_DATA_DIR`，
解析逻辑在 `src/runtime_paths.py` 与 `src/hermes_constants.py`。
`get_hermes_home()` 的 docstring 明确写着"不读取 `HERMES_HOME` 环境变量"。

**鉴权**：新增 `core/platform/device`（本机 IPC + 设备鉴权）与
`hermes_cli/dashboard_auth`，`HERMES_DASHBOARD_GATED` 默认开启。上游无此机制。

### 并入后的内核改动

并入 OpenMontage 之后对 `src/` 内核所做的改动，逐条登记在此。这些与 MxAI 遗留无关，
多数是上游本身就有的缺陷，将来对齐上游时应优先尝试回推而不是保留分叉。

| 文件 | 改动 | 上游是否也有此问题 |
|---|---|---|
| `src/tools/environments/local.py` | `_find_bash()` 优先 Git for Windows，并排除 WSL 的 `bash.exe`（新增 `_is_wsl_bash()`） | 是，建议回推 |

**`_find_bash()` 的 WSL 问题**：装了 WSL 的 Windows 机器上，`C:\Windows\System32\bash.exe`
排在 `PATH` 最前，`shutil.which("bash")` 会选中它。那是个 Linux 环境，认 `/mnt/h/...`
而不认 `H:/...`，于是 `_wrap_command()` 里的 `builtin cd -- ... || exit 126` 每次都失败，
**所有** terminal 工具调用一律返回 exit 126。Git Bash 对 `H:\work` 和 `H:/work` 两种写法
都接受（都解析为 `/h/work`），所以问题不在路径分隔符，只在选错了 bash。
回归测试见 `tests/tools/test_find_bash_windows.py`。

## OpenMontage 并入形态

OpenMontage 源码位于 `src/plugins/openmontage/`，作为 `kind: backend` 插件自动加载。

**命名消歧**：插件内的 `tools/`、`lib/`、`skills/` 是 OpenMontage 的，全限定名
`plugins.openmontage.*`；Hermes 内核的 `src/tools/`、`src/skills/` 是另一回事。
二者曾经同名冲突——`tool_registry.discover()` 的默认包名写死 `"tools"` 时会解析到
Hermes 内核那棵树，发现结果静默变空。现在由 `TOOLS_PACKAGE = __package__` 推导。

**三个根**（定义见 `src/plugins/openmontage/lib/paths.py`）：

| 根 | 位置 | 装什么 |
|---|---|---|
| `CODE_ROOT` | 插件目录 | tools/ lib/ skills/ pipeline_defs/ schemas/ styles/ |
| `REPO_ROOT` | 靠标志物向上探测 | vendor/ .agents/ assets/ remotion-composer/ .venv .env |
| `DATA_ROOT` | 默认等于仓库根 | projects/ .backlot/ output/ music_library/ |

宿主注入 `OPENMONTAGE_DATA_ROOT={HUB_DATA_DIR}/montage` 后整个数据面平移，
且 `montage/` 下的目录名与仓库根逐字一致。不注入时行为与合并前完全相同。

`REPO_ROOT` 刻意不用 `parents[N]`：代码搬家后那种写法会静默指向错误目录而不报错。

**暴露给大脑的是能力面，不是 102 个内部工具**。后者是流水线内的执行单元，由导演
技能按阶段调度，平铺出来只会让大脑面对无法正确排序的选项。插件注册 8 个工具
（`om_preflight` `om_catalog` `om_pipeline` `om_project` `om_director` `om_run`
`om_job` `om_state`）、12 个常驻技能、2 个治理钩子。

**硬规则运行时化**：AGENT_GUIDE 里的 "HARD RULE" 只在被读到且没被长对话冲淡时
才生效。可机械判定的两条（Rule Zero 禁止绕流水线、阶段不许跳）挂在 `pre_tool_call`
上，违规直接拒绝执行。契约测试见
`src/plugins/openmontage/tests/contracts/test_hermes_plugin_contract.py`。

### 一次内容事故

合并过程中发现 `AGENT_GUIDE.md` 的工作区副本被改成中文且比 HEAD 短 22K 字符，
丢失了 `Pipeline Bypass Prohibition`、`Present Both Composition Runtimes`、
`## Orchestrator` 等章节——那几节正是硬规则本身，不是排版。已从 HEAD 恢复
（830 行）并重做模块名前缀；被覆盖的中文版留档在
`.claude/tmp/AGENT_GUIDE.zh.overwritten.md`。若要做中文化，需另起一次并保证章节齐全。

## 测试现状

`plugins/mxai` 被剥离后，`tests/conftest.py` 顶层仍 import 它，**一个模块卡死全套收集** ——
既跑不出绿灯也跑不出有意义的红灯。现已改为在收集阶段按内容识别并跳过依赖该模块的测试。

当前真实状态（`cd agent-hub && pytest -q`，PYTHONPATH 含 `src`）：

| 项 | 数量 |
|---|---|
| 收集到 | 283 |
| 通过 | 276 |
| 失败 | 6 |
| 跳过收集（依赖 plugins.mxai） | 271 个模块 |

### 6 个失败的归因

均与 mxai 剥离无关，是移植前就存在的问题：

| 测试 | 原因 |
|---|---|
| `tests/platform/test_device_auth_login.py`（3 个） | 需要可达的 control-server；缺 `CONTROL_SERVER_BASE_URL` 时返回 503 |
| `tests/test_web_routes_lt029.py::test_public_or_reachable_get[/api/status]` | `HERMES_DASHBOARD_GATED` 默认开启 → 403。设 `=0` 即通过 |
| `tests/cron/test_cron_model_and_delivery.py::test_deliver_clawbot_when_gateway_platform_disabled` | 上游缺陷：测试 monkeypatch `gateway.config.load_gateway_config`，但 `cron.scheduler` 直接持有该符号，补丁不生效 |
| `tests/memory/test_hermes_profile_memory.py::test_retrieve_session_start_blocks` | 测试间顺序污染：单独跑该文件 9 个全过，全量跑才失败 |

### 已修的 mxai 残影

- `src/toolsets.py`：移除 19 个 phantom toolset（1 个聚合 + 18 个单工具），其引用的 18 个 `mxai_*` 工具在 src 中零注册
- `src/tools/ui_titles.py`：移除对 `plugins.mxai.mcp_tools` 的死分支
- `src/hermes_cli/cs_peer_manager.py`：`ensure_profile()` 曾**硬 import** mxai 的 prompt seeder 而直接抛 `ModuleNotFoundError`，改为可降级（缺插件时跳过人设补缺）
- `src/templates/`：移除 11 个社媒渠道 profile 模板（22 个文件），src 中零引用且会被打进 exe；保留渠道中立的 `_default`
- `src/marketing_hub_backend.egg-info`：移除陈旧构建元数据
- `tests/gateway/test_load_gateway_config_profile.py`：被测行为（profile 作用域覆盖 + 聚合 toolset 展开）有价值，把夹具从 `mxai` 换成 `spotify` 而非删除

## 移植遗留问题

`README.md` 引用了若干原 MxAI 仓库的同级路径，这些路径**在本仓库中不存在**：

- `../scripts/README.md`
- `../scripts/build-hub.ps1` — 打包入口，缺失意味着 `agent-hub.exe` 目前无法按文档构建
- `../scripts/start-agent-hub.ps1`
- `../docs/打包规范.md`
- `../docs/marketing-hub-design/`

其中 `build-hub.ps1` 的缺失需要优先补齐或改写，否则 `agent-hub.spec` 只能手工调用 PyInstaller。

**已补齐**：`shared/parent_pid_watch.py`（仓库根）。`src/hermes_cli/parent_pid_watch.py` 是个 shim，
按 `parents[3] / "shared"` 找它；`agent-hub.spec` 第 37 行按 `ROOT.parent / "shared"` 打包它。
两处路径一致指向仓库根的 `shared/`，但文件随移植丢失，导致 Gateway spawn 直接
`ModuleNotFoundError`。现已按调用点契约（`hub_entry.py`、`gateway_lifecycle.py`、`gateway/run.py`）
重新实现：父进程消失时子进程自退，避免 sidecar 被强杀后留下占端口的孤儿进程。

另有 `plugins/mxai` 模块已被移除，但 `src/toolsets.py` 等处仍残留对它的引用，
清理进度见仓库根的集成计划。

## 版本控制边界

`agent-hub/` 的构建产物与依赖不入库，规则分两处：

- 仓库根 `.gitignore` 已覆盖 `node_modules/`、`.venv/`、`__pycache__/`、`dist/`、`build/` 及各类缓存
- `agent-hub/.gitignore` 仅补充本地日志（`/logs/`、`*.log`）

实际跟踪约 2200 个文件 / 48MB，其中排除的大块为：
`src/hermes_cli/web_src/node_modules`（229MB）、`src/ui-tui/node_modules`（152MB）、
`build/`（208MB）、`dist/`（133MB）。

`src/hermes_cli/tui_dist/entry.js` 与 `src/hermes_cli/web_dist/` 是**预构建产物但需要入库** ——
`agent-hub.spec` 在缺少 `tui_dist/entry.js` 时会直接 `SystemExit`。
