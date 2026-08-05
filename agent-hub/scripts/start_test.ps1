# Usage: .\scripts\start_test.cmd   (loads .env.test)

& (Join-Path $PSScriptRoot "_start_hub_backend.ps1") -EnvProfile test
