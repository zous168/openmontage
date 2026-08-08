# Start the default Hermes Agent CLI (interactive chat) with OpenMontage env.
# Usage:
#   .\scripts\start_agent_cli.cmd
#   .\scripts\start_agent_cli.cmd -Tui
#   .\scripts\start_agent_cli.cmd -Query "列出 OpenMontage 项目"
#   .\scripts\start_agent_cli.ps1 -EnvProfile dev -- --yolo

param(
    [ValidateSet('dev', 'test', 'prod')]
    [string]$EnvProfile = 'dev',

    # Ink TUI instead of classic chat REPL
    [switch]$Tui,

    # One-shot prompt (non-interactive). Implies chat -q.
    [string]$Query = '',

    # Extra args forwarded to hermes after the subcommand (e.g. --yolo)
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$HermesArgs = @()
)

$ErrorActionPreference = 'Stop'
$HubRoot = Split-Path $PSScriptRoot -Parent
$RepoRoot = Split-Path $HubRoot -Parent
$EnvFile = Join-Path $RepoRoot ".env.$EnvProfile"
$DataDir = Join-Path $RepoRoot '.data'
$SrcDir = Join-Path $HubRoot 'src'

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

# OpenMontage local data plane (projects, config.yaml, plugins).
$env:HUB_DATA_DIR = $DataDir
$env:HERMES_HOME = $DataDir
# HubRoot first (src.*), then SrcDir (cli / hermes_cli top-level imports).
$env:PYTHONPATH = "$HubRoot;$SrcDir"
# Chinese Windows defaults subprocess text mode to GBK; git/tool output is often
# UTF-8 → UnicodeDecodeError in Thread-_readerthread. Force UTF-8 mode.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
# CLI should not fight the hub's gateway supervisor when hub is already up.
if (-not $env:HERMES_GATEWAY_AUTOSTART) {
    $env:HERMES_GATEWAY_AUTOSTART = '0'
}

$pythonCandidates = @(
    (Join-Path $RepoRoot '.venv\Scripts\python.exe'),
    (Join-Path $HubRoot '.venv\Scripts\python.exe')
)
$Python = $pythonCandidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $Python) {
    Write-Host "==> ERROR: no venv python found. Expected one of:" -ForegroundColor Red
    $pythonCandidates | ForEach-Object { Write-Host "    $_" }
    exit 1
}

$argv = @('hermes')
if ($Tui) {
    $argv += '--tui'
} elseif ($Query) {
    $argv += @('chat', '-q', $Query)
} else {
    $argv += 'chat'
}
if ($HermesArgs -and $HermesArgs.Count -gt 0) {
    $argv += $HermesArgs
}

Write-Host "==> Hermes Agent CLI  (data=$DataDir profile=$EnvProfile)" -ForegroundColor Green
Write-Host "==> $($argv -join ' ')" -ForegroundColor DarkGray
Write-Host "==> OpenMontage tools: om_preflight / om_catalog / om_pipeline / om_project / om_director / om_run / om_job / om_state" -ForegroundColor DarkGray
Write-Host "==> Backlot board (if hub is up): http://127.0.0.1:8643/plugins/openmontage/" -ForegroundColor DarkGray
Write-Host ""

# hermes_cli has no __main__; write a temp launcher (avoid PS 5.1 breaking python -c quotes).
$argvJson = ($argv | ConvertTo-Json -Compress)
if ($argv.Count -eq 1) {
    # ConvertTo-Json on a single string yields a bare string, not an array.
    $argvJson = "[$argvJson]"
}

$launchPy = @"
import json, sys, subprocess

sys.path.insert(0, r'$SrcDir')
sys.path.insert(0, r'$HubRoot')

# Harden text-mode subprocess I/O on Windows (GBK locale vs UTF-8 tool output).
def _force_utf8_text_kwargs(kwargs):
    if kwargs.get('text') or kwargs.get('universal_newlines'):
        kwargs.setdefault('encoding', 'utf-8')
        kwargs.setdefault('errors', 'replace')
    return kwargs

_orig_run = subprocess.run
_orig_popen = subprocess.Popen

def _run(*args, **kwargs):
    return _orig_run(*args, **_force_utf8_text_kwargs(kwargs))

class _Popen(_orig_popen):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **_force_utf8_text_kwargs(kwargs))

subprocess.run = _run
subprocess.Popen = _Popen

from hermes_cli.main import main
sys.argv = json.loads(r'''$argvJson''')
raise SystemExit(main())
"@
$launchFile = Join-Path ([System.IO.Path]::GetTempPath()) 'openmontage_agent_cli_launch.py'
Set-Content -LiteralPath $launchFile -Value $launchPy -Encoding UTF8

Push-Location $HubRoot
try {
    & $Python $launchFile
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
