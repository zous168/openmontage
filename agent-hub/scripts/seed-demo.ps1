# Seed demo data for local REST 联调 / UI 点验
# Usage: .\scripts\seed-demo.ps1  |  .\scripts\seed-demo.ps1 -Force

param(
    [switch]$Force,
    [string]$DataDir = ""
)

$ErrorActionPreference = 'Stop'
$HubRoot = Split-Path $PSScriptRoot -Parent
$RepoRoot = Split-Path $HubRoot -Parent
$EnvFile = Join-Path $RepoRoot ".env.dev"

if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
            $name = $Matches[1].Trim()
            $value = $Matches[2].Trim()
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

if (-not $env:HUB_DATA_DIR) {
    $env:HUB_DATA_DIR = Join-Path $env:PROGRAMDATA 'MarketingHub'
}

$env:PYTHONPATH = Join-Path $HubRoot 'src'

$argsList = @()
if ($Force) { $argsList += '--force' }
if ($DataDir) { $argsList += @('--data-dir', $DataDir) }

Write-Host "==> seed demo data (HUB_DATA_DIR=$env:HUB_DATA_DIR)" -ForegroundColor Cyan
Push-Location $HubRoot
try {
    # --directory 显式把工作目录设为 agent-hub（选中其 .venv + 让 `from src.*` 导入成立），不依赖原生 CWD。
    & uv run --directory $HubRoot python (Join-Path $PSScriptRoot 'seed_demo_data.py') @argsList
} finally {
    Pop-Location
}
