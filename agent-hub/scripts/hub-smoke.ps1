# MxAI plugin REST 烟测（需 hub 已在 8642 监听）
# Usage: .\scripts\hub-smoke.ps1 [-BaseUrl http://127.0.0.1:8642]

param(
    [string]$BaseUrl = 'http://127.0.0.1:8642'
)

$ErrorActionPreference = 'Stop'
$Mxai = "$BaseUrl/api/plugins/mxai"
$failed = 0
$ipcHeaders = @{}

function Test-Endpoint {
    param([string]$Name, [string]$Url, [string]$Method = 'GET', [hashtable]$Headers = @{})
    try {
        $merged = @{}
        foreach ($k in $ipcHeaders.Keys) { $merged[$k] = $ipcHeaders[$k] }
        foreach ($k in $Headers.Keys) { $merged[$k] = $Headers[$k] }
        if ($Method -eq 'GET') {
            $r = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 15 -Headers $merged
        } else {
            $r = Invoke-WebRequest -Uri $Url -Method POST -UseBasicParsing -TimeoutSec 15 -ContentType 'application/json' -Body '{}' -Headers $merged
        }
        if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) {
            Write-Host "  OK $Name" -ForegroundColor Green
            return $true
        }
        Write-Host "  FAIL $Name ($r.StatusCode)" -ForegroundColor Red
        return $false
    } catch {
        Write-Host "  FAIL $Name — $($_.Exception.Message)" -ForegroundColor Red
        return $false
    }
}

Write-Host "==> Hub smoke $BaseUrl" -ForegroundColor Cyan

$loginName = if ($env:HUB_DEV_SEED_AI_WORKER_LOGIN) { $env:HUB_DEV_SEED_AI_WORKER_LOGIN } else { 'aw_1d8c23200075fe43bf0881c5' }
$loginPass = if ($env:HUB_DEV_SEED_PASSWORD) { $env:HUB_DEV_SEED_PASSWORD } else { 'Seed@Pass123' }
$loginJson = "{`"login_name`":`"$loginName`",`"password`":`"$loginPass`"}"
try {
    $login = Invoke-WebRequest -Uri "$BaseUrl/api/auth/login" -Method POST -UseBasicParsing -TimeoutSec 15 -ContentType 'application/json' -Body $loginJson
    if ($login.StatusCode -ge 200 -and $login.StatusCode -lt 300) {
        Write-Host "  OK device login ($loginName)" -ForegroundColor Green
    } else {
        Write-Host "  FAIL device login ($login.StatusCode)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  FAIL device login — $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "  tip: set HUB_DEV_SEED_AI_WORKER_LOGIN / HUB_DEV_SEED_PASSWORD on hub process" -ForegroundColor DarkYellow
    exit 1
}

try {
    $ipc = Invoke-WebRequest -Uri "$BaseUrl/api/auth/dev/local-ipc-token" -UseBasicParsing -TimeoutSec 15
    $ipcBody = $ipc.Content | ConvertFrom-Json
    if ($ipcBody.token) {
        $ipcHeaders['X-Hub-Local-Token'] = $ipcBody.token
        Write-Host "  OK ipc token" -ForegroundColor Green
    } else {
        Write-Host "  FAIL ipc token (empty)" -ForegroundColor Red
        exit 1
    }
} catch {
    Write-Host "  FAIL ipc token — $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$checks = @(
    @{ Name = 'health'; Url = "$BaseUrl/health"; Method = 'GET' },
    @{ Name = 'stats/summary'; Url = "$Mxai/stats/summary"; Method = 'GET' },
    @{ Name = 'queue/summary'; Url = "$Mxai/queue/summary"; Method = 'GET' },
    @{ Name = 'kb/partitions'; Url = "$Mxai/kb/partitions"; Method = 'GET' },
    @{ Name = 'chat/favorites'; Url = "$Mxai/chat/commands/favorites"; Method = 'GET' },
    @{ Name = 'auth/session'; Url = "$Mxai/auth/session"; Method = 'GET' },
    @{ Name = 'auth/login'; Url = "$Mxai/auth/login"; Method = 'POST' },
    @{ Name = 'messaging/platforms'; Url = "$BaseUrl/api/messaging/platforms"; Method = 'GET' },
    @{ Name = 'clawbot/onboarding/start'; Url = "$BaseUrl/api/messaging/clawbot/onboarding/start"; Method = 'POST' }
)

foreach ($c in $checks) {
    if (-not (Test-Endpoint -Name $c.Name -Url $c.Url -Method $c.Method)) {
        $failed += 1
    }
}

if ($failed -gt 0) {
    Write-Host "==> Hub smoke FAILED ($failed checks)" -ForegroundColor Red
    exit 1
}

Write-Host "==> Hub smoke PASSED" -ForegroundColor Green
