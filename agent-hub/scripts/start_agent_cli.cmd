@echo off
REM Default Hermes Agent CLI (OpenMontage-enabled).
REM Usage: scripts\start_agent_cli.cmd
REM        scripts\start_agent_cli.cmd -Tui
REM        scripts\start_agent_cli.cmd -Query "列出项目"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_agent_cli.ps1" %*
