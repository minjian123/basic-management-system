@echo off
rem 生成 opencode Web 配对二维码：Python 单一实现（同目录 配对二维码.py）的 Windows 薄包装。
setlocal
where python >nul 2>nul
if errorlevel 1 (
  echo [配对二维码] 未找到 python，请先安装 Python 3 并加入 PATH。
  exit /b 2
)
chcp 65001 >nul
python "%~dp0配对二维码.py" %*
exit /b %errorlevel%
