#!/usr/bin/env bash
# 远程关闭开发服务器 mjbk（sudo shutdown -h now）—— Linux 入口脚本（破坏性操作）
# 对应 Windows 版双击入口 关机mjbk.bat；终端/桌面 .desktop 均可调用
# 用法: ./关机mjbk.sh            （显示目标并输入 y 二次确认后执行；sudo 密码读 deploy/.env）
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.." || exit 1   # 跳到仓库根目录
exec python3 scripts/tools/wol/shutdown_mjbk.py "$@"
