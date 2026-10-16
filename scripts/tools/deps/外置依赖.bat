@echo off
rem 依赖外置（Windows）：转调 Python 单一实现（同目录 外置依赖.py）。
setlocal
where python >nul 2>nul
if errorlevel 1 (
  echo [外置依赖] 未找到 python，请先安装 Python 3 并加入 PATH。
  exit /b 2
)
chcp 65001 >nul
python "%~dp0外置依赖.py" %*
exit /b %errorlevel%
