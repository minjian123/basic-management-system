#!/usr/bin/env bash
# 远程唤醒开发服务器 mjw（WOL，等待 WinRM 5985 就绪）—— Linux 入口脚本
# 对应 Windows 版双击入口 唤醒mjw.bat；终端/桌面 .desktop 均可调用
# 用法: ./唤醒mjw.sh [--timeout <秒>]   （凭据读 deploy/.env 的 MJW_*）
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.." || exit 1   # 跳到仓库根目录
PY="$HOME/tools/winrm-venv/bin/python"                    # wake 只需标准库,venv 缺失时退回系统 python3
[ -x "$PY" ] || PY="$(command -v python3 || true)"
exec "$PY" scripts/tools/winrm/wake_mjw.py "$@"
