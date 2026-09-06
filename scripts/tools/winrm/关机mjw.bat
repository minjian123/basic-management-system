@echo off
chcp 65001 >nul
title 远程关机开发服务器 mjw
rem 双击入口：调用 shutdown_mjw.py（需要 pywinrm，建议用 venv 的 python 运行）
cd /d "%~dp0..\..\.."
python "scripts\tools\winrm\shutdown_mjw.py"
pause