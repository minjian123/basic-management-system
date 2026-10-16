@echo off
chcp 65001 >nul
title 本机全套后端（本地裸跑）
rem 入口：转调 本地全套.py（单一实现；完整用法加 --help）
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%本地全套.py" %*
exit /b %errorlevel%
