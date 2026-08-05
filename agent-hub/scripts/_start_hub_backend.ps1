# Start agent-hub uvicorn (Hermes + MxAI plugin) for local REST 联调.
# Usage: .\scripts\start_dev.ps1  |  .\scripts\start_test.ps1

param(
    [ValidateSet('dev', 'test', 'prod')]
    [string]$EnvProfile = 'dev',
    [int]$Port = 8642,
    [string]$ListenHost = '127.0.0.1'
)

$ErrorActionPreference = 'Stop'
$HubRoot = Split-Path $PSScriptRoot -Parent
$RepoRoot = Split-Path $HubRoot -Parent
$EnvFile = Join-Path $RepoRoot ".env.$EnvProfile"

if (Test-Path $EnvFile) {
    Write-Host "==> Loading $EnvFile" -ForegroundColor Cyan
    Get-Content $EnvFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        if ($line -notmatch '^([^=]+)=(.*)$') { return }
        $name = $Matches[1].Trim()
        $value = $Matches[2].Trim()
        if ($value -eq '') { return }
        [Environment]::SetEnvironmentVariable($name, $value, 'Process')
    }
}

# HUB_DEV_SEED_* 已移除：开发 stub 登录已删，登录统一走真实控制服务器验证。

$env:PYTHONPATH = Join-Path $HubRoot 'src'

# API_SERVER_KEY: shared by Hermes delegate; see .env.dev / .env.test
if (-not $env:API_SERVER_KEY) {
    Write-Host '==> WARN: API_SERVER_KEY not set (Hermes delegate unavailable when MXAI_MOCK=0)' -ForegroundColor Yellow
}

# uvicorn 的真实监听地址是唯一真源：强制 HUB_API_HOST/HUB_API_PORT 与之对齐。
# main.py 的 configure_integrated_dashboard 用这两个变量设 app.state.bound_host/bound_port，
# 默认 profile 的 TUI attach URL(_build_gateway_ws_url) 又据此拼接。若二者漂移（例如旧 shell
# 里残留 0.0.0.0:8000），attach URL 会连到没人监听的端口 → 子进程 WS 1006 → "gateway exited"。
# 这里显式覆盖，清除任何残留进程级环境变量的影响。
$env:HUB_API_HOST = $ListenHost
$env:HUB_API_PORT = "$Port"

# Integrated hub: uvicorn owns $Port; gateway api_server must bind a different loopback port.
$apiPort = ($env:API_SERVER_PORT -as [int])
if (-not $apiPort -or $apiPort -eq $Port) {
    $env:API_SERVER_PORT = '18789'
    Write-Host "==> API_SERVER_PORT=$($env:API_SERVER_PORT) (dashboard/listen port is $Port)" -ForegroundColor DarkGray
}

$devDataDir = Join-Path $RepoRoot '.data'
$mockLabel = if ($null -ne $env:MXAI_MOCK -and $env:MXAI_MOCK -ne '') { $env:MXAI_MOCK } else { 'unset(production)' }
Write-Host "==> agent-hub uvicorn ${ListenHost}:${Port} (data=$devDataDir MXAI_MOCK=$mockLabel)" -ForegroundColor Green

function Test-HubListenPortFree {
    param([string]$HostName, [int]$ListenPort)
    $listeners = @(Get-NetTCPConnection -LocalAddress $HostName -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue)
    if (-not $listeners) { return $true }
    $owner = ($listeners | Select-Object -First 1).OwningProcess
    $procName = (Get-Process -Id $owner -ErrorAction SilentlyContinue).ProcessName
    if (-not $procName) { $procName = 'unknown' }
    Write-Host ""
    Write-Host "==> ERROR: ${HostName}:${ListenPort} already in use (PID $owner, $procName)." -ForegroundColor Red
    if ($procName -eq 'agent-hub') {
        Write-Host "    MxAI sidecar or another agent-hub instance is running. Quit MxAI or run .\scripts\stop-all.cmd first." -ForegroundColor Yellow
    } else {
        Write-Host "    Free the port or set HUB_API_PORT to another value before starting dev hub." -ForegroundColor Yellow
    }
    Write-Host ""
    return $false
}

if (-not (Test-HubListenPortFree -HostName $ListenHost -ListenPort $Port)) {
    exit 1
}

# Push/Pop（含 finally）：保证 Ctrl+C 退出后 shell 回到调用时的目录，不停在 agent-hub。
Push-Location $HubRoot
try {
    # 源码热重载仅 HUB_DEV_RELOAD=1 时开启（Windows 下默认关，避免 spawn 报错）。
    # 业务配置热生效不依赖此项，走 ConfigManager.replace / WS。
    $reloadPy = 'False'
    if ($env:HUB_DEV_RELOAD -eq '1') {
        Write-Host '==> HUB_DEV_RELOAD=1: uvicorn reload enabled' -ForegroundColor Yellow
        $reloadPy = 'True'
    } else {
        Write-Host '==> uvicorn without reload (config still hot via ConfigManager)' -ForegroundColor DarkGray
    }
    # 用「临时启动脚本 + 程序化 uvicorn.run」启动，原因：
    # ① `python -m uvicorn` 在本机某些 console/stdin 条件下加载 app 前就静默退出（exit 0、无日志）；
    #    程序化 uvicorn.run 实测不受影响。
    # ② 直接 `python -c "<代码>"` 在 PowerShell 5.1 下把含空格/引号的变量当参数传会被破坏
    #    （uv: "Argument expected for the -c option"）；写成临时 .py 文件可彻底绕开引号问题。
    # 启动脚本里显式把 agent-hub 与 agent-hub/src 加入 sys.path：前者让 main.py 的 `from src.*`
    # 成立、后者让 uvicorn 能 import `main:app`，从而不依赖进程 CWD。
    $srcDir = Join-Path $HubRoot 'src'
    $launchPy = @"
import sys
sys.path.insert(0, r'$srcDir')
sys.path.insert(0, r'$HubRoot')

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='$ListenHost', port=$Port, reload=$reloadPy)
"@
    $launchFile = Join-Path ([System.IO.Path]::GetTempPath()) 'agent_hub_launch.py'
    Set-Content -LiteralPath $launchFile -Value $launchPy -Encoding UTF8
    # 使用仓库根 uv workspace / .venv（兼容：若尚未建 workspace 则回退 agent-hub）
    # --no-sync：.venv 由 scripts/install_deps.py 用 pip 装，含 CUDA 版 torch 与
    # 一批未在 pyproject 声明的 ML/媒体包。让 uv 同步会卸掉 40 个包（实测），
    # 本地转写与视频兜底随之失效。启动只需用现成环境，不该改写它。
    $uvProject = if (Test-Path (Join-Path $RepoRoot 'pyproject.toml')) { $RepoRoot } else { $HubRoot }
    & uv run --no-sync --directory $uvProject python $launchFile
    if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "==> ERROR: agent-hub exited with code $LASTEXITCODE (check bind / logs above)." -ForegroundColor Red
        exit $LASTEXITCODE
    }
} finally {
    Pop-Location
}
