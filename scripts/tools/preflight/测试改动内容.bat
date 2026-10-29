@echo off
rem Dev loop entry (Windows): run only git-changed related tests
rem backend direct-dependency tests + affected frontend packages + changed-file ruff
rem coverage and full static checks stay in the push entry: scripts\tools\preflight\推送.bat
setlocal
set "SCRIPT_DIR=%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo python not found in PATH. Install Python 3 first.
  exit /b 2
)

cd /d "%SCRIPT_DIR%..\..\.."
python "scripts\tools\preflight\测试改动内容.py" %*
exit /b %errorlevel%
