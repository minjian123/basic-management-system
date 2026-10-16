@echo off
chcp 65001 >nul
title 清理宿主端口
rem 入口：转调 清理宿主端口.py（单一实现；参数：<端口> <本项目宿主目录绝对路径>）
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%清理宿主端口.py" %*
exit /b %errorlevel%
