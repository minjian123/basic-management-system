#!/usr/bin/env bash
# mjbk_sleep_rtc.sh — 由 systemd timer(mjbk-sleep-rtc.timer) 每日 00:00 触发：
#   1) 把 RTC 闹钟设为当天 08:00；
#   2) 让机器进入系统睡眠（S3）；
#   3) 08:00 由 RTC 硬件时钟自动唤醒（无需外部 WOL）。
# 说明：白天机器保持开机；到 00:00 才睡；08:00 醒来后继续开机到下一个 00:00。
set -euo pipefail

RTC=/sys/class/rtc/rtc0/wakealarm

# timer 在 00:00 触发，当天 08:00 在未来。
wake_dt="$(date -d '08:00' +%s)"

# 写入 RTC 闹钟：先清零，再写目标 epoch 秒。
echo 0 > "$RTC"
echo "$wake_dt" > "$RTC"

actual="$(cat "$RTC")"
if [ "$actual" != "$wake_dt" ]; then
    logger -t mjbk_sleep_rtc "RTC 闹钟写入失败: got=${actual} want=${wake_dt}"
    exit 1
fi

logger -t mjbk_sleep_rtc "RTC 闹钟已设 $(date -d @${wake_dt} '+%F %T')，系统进入睡眠"

# 进入系统睡眠（此调用会阻塞到唤醒后返回）。
systemctl suspend
