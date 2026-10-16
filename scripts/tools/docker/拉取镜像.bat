@echo off
chcp 65001 >nul
title 批量拉取镜像
rem 双击入口：调用 拉取镜像.py（.py 自身按 __file__ 定位，无 cwd 要求）
rem 选项与口径见 拉取镜像.py 头部注释（-h 查看帮助）；对应 Linux 入口 拉取镜像.sh
set "SCRIPT_DIR=%~dp0"
python "%SCRIPT_DIR%拉取镜像.py" %*
set "RC=%ERRORLEVEL%"
pause
exit /b %RC%
