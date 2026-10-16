#!/usr/bin/env bash
# mjbk_sleep_rtc.sh — 由 systemd timer(mjbk-sleep-rtc.timer) 每日 00:00 触发
# （转调同目录 mjbk_sleep_rtc.py 单一实现；逻辑与口径见该 .py 头部注释）：
#   1) 把 RTC 闹钟设为当天 08:00；2) 进入系统睡眠（S3）；3) 08:00 由 RTC 自动唤醒。
#
# 部署：本文件与 mjbk_sleep_rtc.py 必须**拷贝到同一目录**——mjbk 上
# /etc/systemd/system/mjbk-sleep-rtc.service 的 ExecStart=/usr/local/bin/mjbk_sleep_rtc.sh。
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/mjbk_sleep_rtc.py"

if [ ! -f "$PY" ]; then
    echo "[mjbk_sleep_rtc] 缺同名实现文件：$PY（部署时须与 mjbk_sleep_rtc.sh 一起拷到同一目录）。" >&2
    exit 2
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "[mjbk_sleep_rtc] 未找到 python3，请先安装 Python 3。" >&2
    exit 2
fi

exec python3 "$PY" "$@"
