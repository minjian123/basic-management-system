"""卡住现场诊断工具（13_08）：把当前进程的 asyncio 任务栈与线程栈落盘。

用途：并发用例卡住时，光看「等待门 10s」的告警无法判断持有者——持有者记录会被后续取锁
覆盖。本工具在告警 / 超时现场抓一份全进程栈，直接看到「谁持着门、卡在哪个 await 上」。

开关（默认关闭，零开销）::

    BMS_TEST_STACK_DUMP=1 pytest ...          # 等门告警 / 超时时自动落盘
    BMS_TEST_STACK_DUMP=1 BMS_TEST_STACK_DUMP_EVERY=5 pytest ...   # 告警后每 5s 再抓一份

落点：`<工程根>/.cache/test/gate-stacks-<pid>.log`（每进程一份，多 worker 不互相覆盖）。

也可以直接调用::

    from bms_core.testing.diagnostics import dump_process_stacks
    dump_process_stacks(path, reason="手动抓取")

口径：只在诊断期开启，默认关闭；开启后每个进程首次告警即抓一份，之后按
`BMS_TEST_STACK_DUMP_EVERY`（默认 10s）节流，避免刷盘拖慢本来就卡住的用例。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
import threading
import time
import traceback
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableList

DUMP_ENV = "BMS_TEST_STACK_DUMP"
"""开关环境变量（`1` / `true` / `yes` 视为开启）。"""

DUMP_EVERY_ENV = "BMS_TEST_STACK_DUMP_EVERY"
"""同一进程两次抓取的间隔（秒，默认 10）。"""

DEFAULT_EVERY_SECONDS = 10.0
"""默认节流间隔（秒）。"""

_last_dump = 0.0
"""上次抓取时刻（`time.monotonic()`；进程级）。"""

_lock = threading.Lock()
"""节流判断的互斥（等门发生在不同协程，避免并发重复写盘）。"""


def enabled() -> bool:
    """诊断是否开启（读环境变量）。

    Returns:
        bool: 开启返回 True。
    """
    return os.environ.get(DUMP_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def dump_every_seconds() -> float:
    """抓取节流间隔（读环境变量，非法值回落默认）。

    Returns:
        float: 间隔秒数。
    """
    raw = os.environ.get(DUMP_EVERY_ENV, "").strip()
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_EVERY_SECONDS
    return value if value > 0 else DEFAULT_EVERY_SECONDS


def dump_process_stacks(path: Path, *, reason: str, detail: str = "") -> Path:
    """把当前进程的所有 asyncio 任务栈与线程栈追加到文件。

    Args:
        path: 目标文件路径（父目录自动创建）。
        reason: 触发原因（`warn` / `timeout` / 自定义）。
        detail: 附加信息（门名、等待时长、持有者描述等）。

    Returns:
        Path: 写入的文件路径。
    """
    lines: ConcurrentStableList[str] = ConcurrentStableList()
    lines.add(f"\n===== {time.strftime('%H:%M:%S')} {reason} {detail} =====\n")
    _collect_tasks(lines)
    _collect_threads(lines)
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError), path.open("a", encoding="utf-8") as handle:
        handle.writelines(lines)
    return path


def note_gate_wait(
    path: Path,
    *,
    gate_name: str,
    waited: float,
    reason: str,
    holder: str = "",
) -> Path | None:
    """等门告警 / 超时时的抓取入口（受开关与节流约束）。

    Args:
        path: 目标文件路径。
        gate_name: 门名。
        waited: 已等待秒数。
        reason: 触发原因（`warn` / `timeout`）。
        holder: 持有者描述（另存一行，便于与任务栈对照）。

    Returns:
        Path | None: 实际写盘返回路径；未开启或被节流返回 None。
    """
    global _last_dump
    if not enabled():
        return None
    now = time.monotonic()
    with _lock:
        if now - _last_dump < dump_every_seconds():
            return None
        _last_dump = now
    detail = f"门={gate_name} 等待={waited:.1f}s"
    if holder:
        detail = f"{detail} 持有者={holder[:300]}"
    return dump_process_stacks(path, reason=reason, detail=detail)


def reset_throttle() -> None:
    """清空节流状态（用例隔离与自测用）。"""
    global _last_dump
    with _lock:
        _last_dump = 0.0


def _collect_tasks(lines: ConcurrentStableList[str]) -> None:
    """收集当前事件循环里的任务栈（无运行中的循环时跳过）。

    Args:
        lines: 输出行缓冲。
    """
    try:
        tasks = asyncio.all_tasks()
    except RuntimeError:
        lines.add("--- 无运行中的事件循环\n")
        return
    for task in tasks:
        lines.add(f"--- task {task.get_name()} {task!r}\n")
        for frame in task.get_stack(limit=10):
            lines.add("".join(traceback.format_stack(frame, limit=1)))


def _collect_threads(lines: ConcurrentStableList[str]) -> None:
    """收集当前进程所有线程栈。

    Args:
        lines: 输出行缓冲。
    """
    current = threading.get_ident()
    frames = sys._current_frames()  # pyright: ignore[reportPrivateUsage]
    for thread_id, frame in frames.items():
        marker = " (当前线程)" if thread_id == current else ""
        lines.add(f"--- thread {thread_id}{marker}\n")
        lines.add("".join(traceback.format_stack(frame, limit=12)))
