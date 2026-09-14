#!/usr/bin/env bash
# 一键重打 WorkBuddy「关窗即退出」补丁 —— Linux 入口脚本
# 终端 / 桌面 .desktop 均可调用；需先退出 WorkBuddy，脚本会自动 sudo 提权
# 用法: ./重打关窗即退出.sh [apply|status|restore]   （默认 apply）
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.." || exit 1   # 跳到仓库根目录
exec python3 scripts/tools/workbuddy/patch_close_to_quit.py "$@"
