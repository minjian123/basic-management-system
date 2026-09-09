#!/usr/bin/env bash
# 远程唤醒开发服务器 mjbk（WOL）—— Linux 入口脚本
# 对应 Windows 版双击入口 唤醒mjbk.bat；终端/桌面 .desktop 均可调用
# 用法: ./唤醒mjbk.sh [--timeout <秒>]   （默认等待 SSH 就绪 120 秒，凭据读 deploy/.env）
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.." || exit 1   # 跳到仓库根目录
exec python3 scripts/tools/wol/wake_mjbk.py "$@"
