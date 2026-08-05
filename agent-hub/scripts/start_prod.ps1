# Usage: .\scripts\start_prod.cmd   (loads .env.prod)

& (Join-Path $PSScriptRoot "_start_hub_backend.ps1") -EnvProfile prod
