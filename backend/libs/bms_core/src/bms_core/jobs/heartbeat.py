"""作业 worker 心跳（容器本地文件）：写入 + 健康检查。

- **为什么用文件**：作业 worker 不提供服务端口，镜像内置的 `/healthz` 健康检查必然失败；
  心跳文件只依赖容器本地文件系统，不引入 Redis 等外部依赖，也不受其抖动影响；
- **写入时机**：`JobWorker` 每轮 `tick()` 前刷新（缺省轮询 2s），循环活着就持续刷新——
  调度卡死 / 事件循环卡死时心跳停更，健康检查据此判定 unhealthy；
- **健康检查**：容器健康检查执行 `python -m bms_core.jobs.heartbeat --check`，
  `mtime` 超过 `heartbeat_timeout_seconds`（缺省 30）即退出码 1；
- **参数单源**：路径与超时默认值由本模块常量提供，`[jobs]` 配置与命令行共用，
  环境变量 `BMS_JOBS__HEARTBEAT_PATH` / `BMS_JOBS__HEARTBEAT_TIMEOUT_SECONDS` 可覆盖。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableList

__all__ = [
    "DEFAULT_HEARTBEAT_PATH",
    "DEFAULT_HEARTBEAT_TIMEOUT_SECONDS",
    "build_parser",
    "check_heartbeat",
    "heartbeat_age",
    "main",
    "write_heartbeat",
]

DEFAULT_HEARTBEAT_PATH = "/tmp/bms-jobs-heartbeat"
"""心跳文件缺省路径（容器本地；`[jobs].heartbeat_path` 与健康检查共用）。"""

DEFAULT_HEARTBEAT_TIMEOUT_SECONDS = 30.0
"""心跳超时缺省值（秒；`[jobs].heartbeat_timeout_seconds` 与健康检查共用）。"""

_ENV_PATH = "BMS_JOBS__HEARTBEAT_PATH"
_ENV_TIMEOUT = "BMS_JOBS__HEARTBEAT_TIMEOUT_SECONDS"


def write_heartbeat(path: str | Path = DEFAULT_HEARTBEAT_PATH) -> None:
    """刷新心跳文件（不存在则创建，存在则更新 `mtime`）。

    Args:
        path: 心跳文件路径（父目录缺失时自动创建）。
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.touch(exist_ok=True)


def heartbeat_age(path: str | Path = DEFAULT_HEARTBEAT_PATH, *, now: float | None = None) -> float | None:
    """取心跳文件年龄（秒）。

    Args:
        path: 心跳文件路径。
        now: 当前时间（测试注入；None 取 `time.time()`）。

    Returns:
        float | None: 年龄（秒）；文件不存在返回 None。
    """
    try:
        modified = Path(path).stat().st_mtime
    except FileNotFoundError:
        return None
    return (time.time() if now is None else now) - modified


def check_heartbeat(
    path: str | Path = DEFAULT_HEARTBEAT_PATH,
    *,
    timeout_seconds: float = DEFAULT_HEARTBEAT_TIMEOUT_SECONDS,
    now: float | None = None,
) -> bool:
    """判定心跳是否新鲜（供容器健康检查调用）。

    Args:
        path: 心跳文件路径。
        timeout_seconds: 超时阈值（秒）；年龄超过阈值判定不健康。
        now: 当前时间（测试注入；None 取 `time.time()`）。

    Returns:
        bool: 心跳未超时为 True；文件缺失或超时为 False。
    """
    age = heartbeat_age(path, now=now)
    return age is not None and age <= timeout_seconds


def build_parser() -> argparse.ArgumentParser:
    """构造命令行解析器（缺省即执行健康检查）。

    Returns:
        argparse.ArgumentParser: 解析器。
    """
    parser = argparse.ArgumentParser(prog="python -m bms_core.jobs.heartbeat", description="作业 worker 心跳健康检查")
    parser.add_argument(
        "--check",
        action="store_true",
        help="执行健康检查（缺省动作；保留显式开关便于编排文件自解释）",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get(_ENV_PATH, DEFAULT_HEARTBEAT_PATH),
        help=f"心跳文件路径（缺省读 {_ENV_PATH}，再缺省 {DEFAULT_HEARTBEAT_PATH}）",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=float(os.environ.get(_ENV_TIMEOUT, DEFAULT_HEARTBEAT_TIMEOUT_SECONDS)),
        help=f"超时秒数（缺省读 {_ENV_TIMEOUT}，再缺省 {DEFAULT_HEARTBEAT_TIMEOUT_SECONDS}）",
    )
    return parser


def main(argv: ConcurrentStableList[str] | None = None) -> int:
    """入口：心跳新鲜返回 0，缺失 / 超时返回 1。

    Args:
        argv: 命令行参数（None 取 `sys.argv`）。

    Returns:
        int: 退出码（0 健康 / 1 不健康）。
    """
    args = build_parser().parse_args(None if argv is None else list(argv))
    age = heartbeat_age(args.path)
    if age is None:
        sys.stderr.write(f"[heartbeat] 心跳文件不存在：{args.path}\n")
        return 1
    if age > args.timeout:
        sys.stderr.write(f"[heartbeat] 心跳超时：{age:.1f}s > {args.timeout:.1f}s（{args.path}）\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
