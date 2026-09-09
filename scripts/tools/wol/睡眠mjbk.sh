#!/usr/bin/env bash
# 远程让开发服务器 mjbk 进入系统睡眠（S3）—— Linux 入口脚本
# 对应 Windows 版双击入口 睡眠mjbk.bat；终端/桌面 .desktop 均可调用
# 用法: ./睡眠mjbk.sh            （显示目标并输入 y 二次确认后执行；sudo 密码读 deploy/.env）
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/../../.." || exit 1   # 跳到仓库根目录
exec python3 scripts/tools/wol/sleep_mjbk.py "$@"
