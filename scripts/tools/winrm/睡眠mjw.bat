@echo off
chcp 65001 >nul
title 远程让开发服务器 mjw 进入睡眠
rem 双击入口：调用 sleep_mjw.py（需要 pywinrm，建议用 venv 的 python 运行）
cd /d "%~dp0..\..\.."
python "scripts\tools\winrm\sleep_mjw.py"
pause