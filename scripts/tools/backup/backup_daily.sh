#!/usr/bin/env bash
# BMS 开发服务器每日备份总控 —— Linux 入口脚本（转调同名 backup_daily.py 单一实现；逻辑见 backup_daily.py）
# 用法: ./backup_daily.sh；cron 02:30 每日（部署于 mjbk ~/deploy/backup/，须与 backup_daily.py 同目录并存）
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/backup_daily.py" ] || { echo "缺少 backup_daily.py（部署时须与本包装同目录一起拷贝）" >&2; exit 1; }
exec python3 "$HERE/backup_daily.py" "$@"
