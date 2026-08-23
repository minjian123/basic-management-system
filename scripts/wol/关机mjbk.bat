@echo off
chcp 65001 >nul
title 远程关机开发服务器 mjbk
rem 双击入口：调用 shutdown_mjbk.py（仓库根目录执行，脚本在 scripts\wol\ 下向上三级）
cd /d "%~dp0..\..\.."
python "scripts\wol\shutdown_mjbk.py"
pause