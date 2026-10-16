@echo off
chcp 65001 >nul
title 确保模块产物服务（5002）
rem 入口：转调 确保模块产物服务.py（单一实现；幂等，缺则后台拉起）
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%确保模块产物服务.py" %*
exit /b %errorlevel%
