#!/usr/bin/env python3
"""mjbk_sleep_rtc.py — 由 systemd timer(mjbk-sleep-rtc.timer) 每日 00:00 触发：
  1) 把 RTC 闹钟设为当天 08:00；
  2) 让机器进入系统睡眠（S3）；
  3) 08:00 由 RTC 硬件时钟自动唤醒（无需外部 WOL）。
说明：白天机器保持开机；到 00:00 才睡；08:00 醒来后继续开机到下一个 00:00。

部署口径：本文件与同名 .sh 瘦包装（mjbk_sleep_rtc.sh）必须落在同一目录——
mjbk 上 `/etc/systemd/system/mjbk-sleep-rtc.service` 的
`ExecStart=/usr/local/bin/mjbk_sleep_rtc.sh` 先起包装，包装再转调同目录的本 .py
（缺 .py 时包装会提示「缺同名实现文件」并退出 2）。

行为口径（与原 shell 版逐项一致）：
  - 目标时刻：等价 `date -d '08:00' +%s`，即本地时区「当天 08:00」的 epoch 秒
    （timer 00:00 触发时该时刻在未来）；
  - 写 RTC：先向 /sys/class/rtc/rtc0/wakealarm 写 0 清零，再写目标 epoch 秒
    （与 `echo` 同为带尾换行；写权限不足或接口缺失时向 stderr 报错并退出 1）；
  - 写后校验：回读值 ≠ 目标值 → `logger -t mjbk_sleep_rtc "RTC 闹钟写入失败: got=… want=…"`
    并退出 1（日志文案与旧版一致）；
  - 成功：`logger -t mjbk_sleep_rtc "RTC 闹钟已设 <YYYY-MM-DD HH:MM:SS>，系统进入睡眠"`；
  - 最后 `systemctl suspend`：阻塞到唤醒后返回，其退出码即脚本退出码（同旧 `set -e`）。

历史：本脚本原为 shell 实现（mjbk_sleep_rtc.sh），2026-10-16 起改为
Python 单一实现 + 同名 .sh 薄包装。
"""

import contextlib
import datetime
import subprocess
import sys

# RTC 闹钟接口：写 0 清零，写 epoch 秒即设下次唤醒时刻。
WAKEALARM = "/sys/class/rtc/rtc0/wakealarm"
# 每日唤醒时刻（本地时区整天定点）。
WAKE_HOUR = 8
LOG_TAG = "mjbk_sleep_rtc"


def configure_stdio():
    """输出统一 UTF-8（异常信息会进 systemd journal）。"""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(Exception):
            stream.reconfigure(encoding="utf-8")


def log(message):
    """写 syslog（等价 `logger -t mjbk_sleep_rtc 消息`）。"""
    subprocess.run(["logger", "-t", LOG_TAG, message], check=True)


def write_wakealarm(value):
    """向 wakealarm 写一个值（等价 `echo value > /sys/class/rtc/rtc0/wakealarm`）。"""
    with open(WAKEALARM, "w", encoding="ascii") as handle:
        handle.write(f"{value}\n")


def read_wakealarm():
    """读回 wakealarm（去尾换行，等价 shell 命令替换）。"""
    with open(WAKEALARM, encoding="ascii") as handle:
        return handle.read().strip()


def next_wake_epoch(now=None):
    """当天 WAKE_HOUR 点的 epoch 秒（本地时区，等价 `date -d '08:00' +%s`）。"""
    moment = now or datetime.datetime.now()
    return int(moment.replace(hour=WAKE_HOUR, minute=0, second=0, microsecond=0).timestamp())


def main():
    # timer 在 00:00 触发，当天 08:00 在未来。
    wake_epoch = next_wake_epoch()

    # 写入 RTC 闹钟：先清零，再写目标 epoch 秒。
    try:
        write_wakealarm(0)
        write_wakealarm(wake_epoch)
        actual = read_wakealarm()
    except OSError as exc:
        sys.stderr.write(f"[{LOG_TAG}] RTC 闹钟写入失败（{WAKEALARM}）：{exc}\n")
        return 1

    if actual != str(wake_epoch):
        log(f"RTC 闹钟写入失败: got={actual} want={wake_epoch}")
        return 1

    wake_text = datetime.datetime.fromtimestamp(wake_epoch).strftime("%Y-%m-%d %H:%M:%S")
    log(f"RTC 闹钟已设 {wake_text}，系统进入睡眠")

    # 进入系统睡眠（此调用会阻塞到唤醒后返回）。
    subprocess.run(["systemctl", "suspend"], check=True)
    return 0


if __name__ == "__main__":
    configure_stdio()
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as exc:
        # 与旧 `set -e` 同口径：外部命令失败即中止，退出码沿用其状态码
        # （被信号终止的负值折算为 shell 的 128+N）。
        code = 128 - exc.returncode if exc.returncode < 0 else exc.returncode
        sys.stderr.write(f"[{LOG_TAG}] 外部命令失败（退出码 {code}）：{' '.join(exc.cmd)}\n")
        sys.exit(code)
