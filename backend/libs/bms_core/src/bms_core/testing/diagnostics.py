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
from functools import partial
from pathlib import Path

from bms_core.core.concurrent import ConcurrentStableList

DUMP_ENV = "BMS_TEST_STACK_DUMP"
"""开关环境变量（`1` / `true` / `yes` 视为开启）。"""

HOLD_ENV = "BMS_TEST_GATE_HOLD"
"""持有时长采样开关：设为 1 时每次门区间结束时记一行（用于排最耗时的用例）。"""

HANG_ENV = "BMS_TEST_HANG_SECONDS"
"""定时抓栈间隔（秒）：设置后即使没有等门也会周期抓一份（查「某个 await 永不返回」）。"""

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


def hang_every_seconds() -> float:
    """定时抓栈间隔（未设置或非法返回 0，表示不启用）。

    Returns:
        float: 间隔秒数；0 表示关闭。
    """
    raw = os.environ.get(HANG_ENV, "").strip()
    try:
        value = float(raw)
    except ValueError:
        return 0.0
    return value if value > 0 else 0.0


def ensure_watchdog(path: Path) -> None:
    """按需启动「定时抓栈」看守（进程内一个常驻线程）。

    为什么用线程而不是 `loop.create_task`：pytest-asyncio 每个用例一个新事件循环，任务版看守
    随循环销毁，根本活不到下一次抓取；线程版只持有「当前活动循环」的指针，跨用例继续有效。

    与 `note_gate_wait` 的分工：那个只在等门时抓，管不到「没等门却永远回不来」的 await。

    Args:
        path: 抓取落点（每进程一份）。
    """
    every = hang_every_seconds()
    if every <= 0:
        return
    global _current_loop, _watch_path, _watch_started
    _current_loop = asyncio.get_running_loop()
    _watch_path = path
    with _watch_lock:
        if _watch_started:
            return
        _watch_started = True
    threading.Thread(target=_watch_loop, args=(every,), name="diag-watchdog", daemon=True).start()


def _watch_loop(every: float) -> None:
    """看守线程主体：每 `every` 秒抓一份。

    Args:
        every: 间隔秒数。
    """
    while True:
        _watch_tick(every)


def _watch_tick(every: float) -> None:
    """睡一个间隔后在活动循环上抓一份（异常静默，不影响用例）。

    Args:
        every: 间隔秒数。
    """
    time.sleep(every)
    loop = _current_loop
    path = _watch_path
    if loop is None or path is None or loop.is_closed():
        return
    with contextlib.suppress(RuntimeError):
        loop.call_soon_threadsafe(partial(dump_process_stacks, path, reason="watchdog", detail=f"每 {every:g}s"))
        # call_soon_threadsafe 是线程安全的；dump 在循环线程执行，能枚举 asyncio 任务。


def reset_watchdogs() -> None:
    """重置看守状态（用例隔离与自测用；不终止已启动线程）。"""
    global _current_loop, _watch_path, _watch_started
    with _watch_lock:
        _current_loop = None
        _watch_path = None
        _watch_started = False


_current_loop: asyncio.AbstractEventLoop | None = None
"""最近一次取门时所在的循环（看守线程按它调度抓取）。"""

_watch_path: Path | None = None
"""抓取落点。"""

_watch_started = False
"""看守线程是否已启动。"""

_watch_lock = threading.Lock()
"""启动互斥。"""


def note_hold(
    name: str,
    seconds: float,
    *,
    read_only: bool,
    wait_read: float,
    wait_write: float,
    held: float,
) -> None:
    """记录一次门区间的持有时长（`BMS_TEST_GATE_HOLD=1` 时启用）。

    **三段分开记**：`seconds` 含排队，单看它分不清「在门口等」与「真持有」——压测时
    后者才是串行成本，前者只是争用。故另记等读锁、等写门与区间内实占时长：日志列依次为
    「总时长 / 模式 / 门名 / 用例 / 等读 / 等写 / 实占」。

    Args:
        name: 门名。
        seconds: 门区间总时长（含排队，秒）。
        read_only: 只读区间 True。
        wait_read: 等读锁时长（秒）。
        wait_write: 等写门时长（秒；只读区间为 0）。
        held: 区间内实占时长（秒）。
    """
    if os.environ.get(HOLD_ENV, "").strip() not in {"1", "true", "yes", "on"}:
        return
    test_id = os.environ.get("PYTEST_CURRENT_TEST", "").split(" (")[0]
    path = Path(".cache/test/gate-hold.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    with contextlib.suppress(OSError), path.open("a", encoding="utf-8") as handle:
        mode = "read" if read_only else "write"
        handle.write(f"{seconds:.3f}\t{mode}\t{name}\t{test_id}\t{wait_read:.3f}\t{wait_write:.3f}\t{held:.3f}\n")


def hold_enabled() -> bool:
    """持有时长采样是否开启（`BMS_TEST_GATE_HOLD=1`）。

    Returns:
        bool: 开启返回 True。
    """
    return os.environ.get(HOLD_ENV, "").strip() in {"1", "true", "yes", "on"}


def note_slow_hold(
    name: str,
    seconds: float,
    *,
    read_only: bool,
    wait_read: float,
    wait_write: float,
    held: float,
    frames: str,
) -> None:
    """记录一次「门区间超过 1s」的慢区间，附取门时的调用栈（用来定位长会话从哪来）。

    阈值按**门区间总时长**（含排队）判定：排队本身也是被堵的成本，不能因为「没真持有」
    就漏掉；三段时长同时落盘，读的人可直接分辨这一条是排队还是真持有。

    Args:
        name: 门名。
        seconds: 门区间总时长（含排队，秒）。
        read_only: 只读区间 True。
        wait_read: 等读锁时长（秒）。
        wait_write: 等写门时长（秒；只读区间为 0）。
        held: 区间内实占时长（秒）。
        frames: 取门时的调用栈。
    """
    if not hold_enabled() or seconds < 1.0:
        return
    test_id = os.environ.get("PYTEST_CURRENT_TEST", "").split(" (")[0]
    path = Path(".cache/test/gate-hold-slow.log")
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "read" if read_only else "write"
    prefix = f"{seconds:.3f}\t{mode}\t{name}\t{test_id}\t{wait_read:.3f}\t{wait_write:.3f}\t{held:.3f}"
    with contextlib.suppress(OSError), path.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}\t{frames}" + chr(10))


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
