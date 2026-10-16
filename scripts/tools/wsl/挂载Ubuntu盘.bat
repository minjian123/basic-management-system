@echo off
rem 挂载双系统 Ubuntu 数据盘进 WSL（只读）：转调同目录 挂载Ubuntu盘.py（Python 单一实现）。
rem 需管理员权限：桌面快捷方式「挂载 Ubuntu 盘」已勾「以管理员身份运行」。
setlocal
chcp 65001 >nul
title 挂载 Ubuntu 数据盘（只读）
where python >nul 2>nul
if errorlevel 1 (
  echo [挂载Ubuntu盘] 未找到 python，请先安装 Python 3 并加入 PATH。
  pause
  exit /b 2
)
python "%~dp0挂载Ubuntu盘.py" %*
set "RC=%errorlevel%"
pause
exit /b %RC%
