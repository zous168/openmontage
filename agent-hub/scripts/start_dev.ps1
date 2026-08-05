# Usage: .\scripts\start_dev.cmd   (loads .env.dev)

& (Join-Path $PSScriptRoot "_start_hub_backend.ps1") -EnvProfile dev
