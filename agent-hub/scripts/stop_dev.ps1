# Stop backend Hub uvicorn dev (default port 8000)
# Usage: .\scripts\stop_dev.cmd

param(
    [int]$Port = 8000,
    [switch]$ForcePort
)

$ErrorActionPreference = "Continue"

function Get-ListeningPids {
    param([int]$TargetPort)
    $pids = [System.Collections.Generic.HashSet[int]]::new()
    foreach ($line in (netstat -ano | Select-String ":$TargetPort\s")) {
        if ($line -match '\s+LISTENING\s+(\d+)\s*$') {
            [void]$pids.Add([int]$Matches[1])
        }
    }
    return @($pids)
}

function Test-HubUvicornProcess {
    param([string]$CommandLine)
    if ([string]::IsNullOrWhiteSpace($CommandLine)) { return $false }
    return (
        $CommandLine -match 'uvicorn' -and
        (
            $CommandLine -match 'src\.main:app' -or
            $CommandLine -match 'backend[/\\]src' -or
            $CommandLine -match 'marketing-hub'
        )
    )
}

Write-Host "==> Stopping backend dev on port $Port ..." -ForegroundColor Cyan

$pids = Get-ListeningPids -TargetPort $Port
if ($pids.Count -eq 0) {
    Write-Host "Port $Port : no LISTEN process" -ForegroundColor DarkGray
    exit 0
}

foreach ($processId in $pids) {
    $info = Get-CimInstance Win32_Process -Filter "ProcessId=$processId" -ErrorAction SilentlyContinue
    $cmd = if ($info) { $info.CommandLine } else { "" }

    if ($ForcePort -or (Test-HubUvicornProcess $cmd)) {
        $name = (Get-Process -Id $processId -ErrorAction SilentlyContinue).ProcessName
        Write-Host "  kill PID=$processId ($name) - Hub uvicorn" -ForegroundColor Yellow
        & taskkill.exe /PID $processId /T /F 2>$null | Out-Null
    }
    else {
        $short = if ($cmd.Length -gt 120) { $cmd.Substring(0, 120) + "..." } else { $cmd }
        Write-Host "  skip PID=$processId (not Hub uvicorn): $short" -ForegroundColor DarkYellow
        Write-Host "  tip: use -ForcePort to kill anyway" -ForegroundColor DarkYellow
    }
}

Write-Host "==> Backend dev stopped." -ForegroundColor Green
