@echo off
chcp 65001 >nul
title 远程唤醒开发服务器 mjw
rem 双击入口：调用 wake_mjw.py（仓库根目录执行）
cd /d "%~dp0..\..\.."
python "scripts\tools\winrm\wake_mjw.py"
pause