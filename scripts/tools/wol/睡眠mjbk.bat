@echo off
chcp 65001 >nul
title 远程睡眠开发服务器 mjbk
rem 双击入口：调用 sleep_mjbk.py（仓库根目录执行，脚本在 scripts\wol\ 下向上三级）
cd /d "%~dp0..\..\.."
python "scripts\wol\sleep_mjbk.py"
pause
