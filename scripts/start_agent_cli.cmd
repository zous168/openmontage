@echo off
REM Repo-root shortcut → agent-hub Hermes Agent CLI (OpenMontage).
set "TARGET=%~dp0..\agent-hub\scripts\start_agent_cli.cmd"
if not exist "%TARGET%" (
  echo ERROR: missing "%TARGET%"
  exit /b 1
)
call "%TARGET%" %*
