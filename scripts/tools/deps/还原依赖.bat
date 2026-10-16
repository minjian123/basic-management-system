@echo off
rem 依赖还原（Windows）：转调 Python 单一实现（同目录 还原依赖.py）。
setlocal
where python >nul 2>nul
if errorlevel 1 (
  echo [还原依赖] 未找到 python，请先安装 Python 3 并加入 PATH。
  exit /b 2
)
chcp 65001 >nul
python "%~dp0还原依赖.py" %*
exit /b %errorlevel%
