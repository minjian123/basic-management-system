#!/usr/bin/env python3
"""串行闸门锁的查看与清理（`ci-queue-lock` 容器）。

背景：bms 与 mdm 共用同一台 runner 的宿主 docker daemon，以同名容器作流水线互斥量（`.pre` 取锁 /
`.post` 释放）。**取消流水线时 `.post` 也会被取消**，锁因此遗留；而跨项目 owner 无法由闸门自己判定，
只能等 `CI_QUEUE_STALE_SECONDS`（缺省 7200s）年龄兜底——期间各仓流水线全在 `ci-queue-acquire` 干等。

清理属不可逆动作：**不加 `--yes` 只打印计划**。

用法::

    # 看锁的 owner 与持锁时长
    python3 scripts/tools/ci/ci_queue_lock.py show

    # 确认后强删
    python3 scripts/tools/ci/ci_queue_lock.py clear --yes

连接信息：读仓根 `deploy/.env`（已 gitignore）的 `MJBK_IP` / `MJBK_SSH_USER`（与 `engkit kiwi` 同源，
SSH 走公钥免密；可用同名环境变量覆盖）。锁名取 `CI_QUEUE_LOCK`，缺省 `ci-queue-lock`。
退出码：0 成功；1 SSH / docker 失败；2 用法或凭据缺失 / 未确认。
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time

from ci_common import ENV_FILE, ConcurrentStableList, load_env

LOCK_ENV = "CI_QUEUE_LOCK"
"""锁容器名对应的环境变量（两仓 `.gitlab-ci.yml` 同键）。"""

DEFAULT_LOCK = "ci-queue-lock"
"""缺省锁容器名（与两仓 `CI_QUEUE_LOCK` 缺省值一致）。"""

HOST_ENV = "MJBK_IP"
"""服务器地址键名（与 `engkit kiwi` 同源）。"""

USER_ENV = "MJBK_SSH_USER"
"""SSH 账号键名（与 `engkit kiwi` 同源）。"""

INSPECT_TEMPLATE = '{{index .Config.Labels "ci-queue.owner"}} {{index .Config.Labels "ci-queue.at"}}'
"""同时取 owner 与持锁时间戳的 docker inspect 模板。"""


def ssh_target() -> str:
    """拼接 SSH 目标（`账号@主机`）。

    Returns:
        str: 目标串（凭据缺失为空串）。
    """
    env = load_env(ENV_FILE)
    host = os.environ.get(HOST_ENV, "") or env.get(HOST_ENV, "")
    user = os.environ.get(USER_ENV, "") or env.get(USER_ENV, "")
    return f"{user}@{host}" if host and user else ""


def run_ssh(target: str, command: str) -> tuple[int, str]:
    """远端执行命令。

    Args:
        target: SSH 目标串。
        command: 远端命令。

    Returns:
        tuple[int, str]: 退出码与合并输出。
    """
    result = subprocess.run(["ssh", target, command], text=True, capture_output=True, check=False)
    return result.returncode, (result.stdout + result.stderr).strip()


def lock_owner(target: str, lock: str) -> str:
    """取锁容器的 owner 标签。

    Args:
        target: SSH 目标串。
        lock: 锁容器名。

    Returns:
        str: owner（不存在或读取失败为空串）。
    """
    code, output = run_ssh(target, f"docker inspect -f '{{{{index .Config.Labels \"ci-queue.owner\"}}}}' {lock}")
    return output if code == 0 else ""


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口。

    Args:
        argv: 命令行参数（缺省取 `sys.argv[1:]`）。

    Returns:
        int: 退出码（0 成功 / 1 SSH 或 docker 失败 / 2 用法或凭据缺失）。
    """
    parser = argparse.ArgumentParser(description="串行闸门锁的查看与清理")
    parser.add_argument("action", choices=["show", "clear"], help="show 查看；clear 强删（需 --yes）")
    parser.add_argument("--yes", action="store_true", help="确认执行清锁（不加只打印计划）")
    args = parser.parse_args(argv.to_list() if argv is not None else None)

    target = ssh_target()
    if not target:
        print(f"[lock] 缺少 {HOST_ENV} / {USER_ENV}（读 {ENV_FILE} 或同名环境变量）", file=sys.stderr)
        return 2
    lock = os.environ.get(LOCK_ENV, "") or DEFAULT_LOCK

    code, output = run_ssh(target, f"docker inspect -f '{INSPECT_TEMPLATE}' {lock}")
    if code != 0:
        print(f"[lock] 当前无锁（{lock} 不存在）")
        return 0
    parts = output.split()
    owner = parts[0] if parts else "未知"
    stamp = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
    held = int(time.time()) - stamp if stamp else 0
    stale = os.environ.get("CI_QUEUE_STALE_SECONDS", "7200")
    print(f"[lock] {lock}  owner={owner}  持锁 {held}s（阈值 {stale}s 判定陈旧）")
    if args.action == "show":
        return 0
    if not args.yes:
        print("[lock] 未执行：确认后加 --yes", file=sys.stderr)
        return 2
    code, output = run_ssh(target, f"docker rm -f {lock}")
    print(f"[lock] 删除 {lock}：{output or '已删除'}")
    return 0 if code == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
