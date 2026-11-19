"""数据库门上下文（13_08）：**取门只有一条路径** `gate_scope`。

口径（《测试规范》「并行与隔离」节）：

- **一律先加读锁**：读操作持读锁执行；写操作先持读锁进来，再让出读份额升到写锁；
- 读门之间共享、写门与所有读门互斥；写门持有期间新读锁加不上，不会读到写了一半的数据；
- 作用域是**一次数据库操作**（一次会话），不是整条用例；
- 升级顺序固定为「让出读份额 → 取写门 → 放写门 → 取回读份额」，异常路径同序执行；
- 跨库同时需要写门时，固定「平台库在前、租户库在后」的嵌套顺序。
"""

from __future__ import annotations

import time
import traceback
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.gate import db_access_gate
from bms_core.testing import diagnostics
from bms_core.testing.rwlock import DEFAULT_TIMEOUT, DbGate, gate_path

PLATFORM_GATE = "platform"
"""平台库门名（对应 `.cache/test/platform.db`）。"""

TENANT_GATE = "tenant"
"""租户库门名（对应 `.cache/test/tenant.db`）。"""

_GATES: ConcurrentStableDict[str, DbGate] = ConcurrentStableDict()
"""门单例（进程内复用同一句柄；`-n auto` 下由操作系统保证跨进程互斥）。"""


def gate(name: str) -> DbGate:
    """取（或创建）门单例。

    Args:
        name: 门名（`platform` / `tenant`）。

    Returns:
        DbGate: 门实例。
    """
    existing = _GATES.get(name)
    if existing is not None:
        return existing
    created = DbGate(name, gate_path(name))
    _GATES[name] = created
    return created


@asynccontextmanager
async def gate_scope(name: str, *, read_only: bool, wait: float | None = None) -> AsyncGenerator[None]:
    """**取门的唯一入口**：一律先加读锁，写操作再让出读份额升到写锁。

    结构固定为「读锁打底 → （写）让读 → 取写 → 写 → 放写 → 补回读 → 放读」，异常路径同序：

    - 写路径的 `try` 包住「让出读份额 → 取写门 → 执行写」三件事；
    - 它的 `finally` 先放写门、再补回读锁；写门没拿到时 `release_write` 只记日志不抛错；
    - 最外层 `finally` 释放读锁。

    Args:
        name: 门名。
        read_only: 只读 True（持读锁执行），写 False（升到写锁执行）。
        wait: 等待上限（秒）；None 走默认（写门 5s，可用环境变量覆盖）。

    Yields:
        None: 门内区间。
    """
    target = gate(name)
    started = time.monotonic()
    frames = ""
    if diagnostics.hold_enabled():
        frames = " <- ".join(
            line.strip().splitlines()[0]
            for line in traceback.format_stack()[-8:-2]
            if line.strip() and "contextlib.py" not in line and "gates.py" not in line
        )
    token = await target.acquire_read()
    try:
        if read_only:
            yield
            return
        restored: ConcurrentStableList[int] = ConcurrentStableList()
        try:
            # 解锁读锁：让出自己这份份额（同进程其它会话的份额不受影响）。
            await target.release_read(token)
            # 并发的写在这里排队；拿到写门后独占，期间新读锁加不上。
            restored = await target.acquire_write(wait=wait)
            yield
        finally:
            # 无论是否报错都释放写门；没拿到（取写门就失败）时只记日志。
            await target.release_write(restored)
            # 再把读锁加上，恢复进入时的读状态。
            token = await target.acquire_read()
    finally:
        await target.release_read(token)
        elapsed = time.monotonic() - started
        diagnostics.note_hold(name, elapsed, read_only=read_only)
        diagnostics.note_slow_hold(name, elapsed, read_only=read_only, frames=frames)


def write_window(db_key: str) -> AbstractAsyncContextManager[None]:
    """按库键取写门：一段**显式写区间**的跨进程互斥（直连共享引擎的用例用）。

    与 `platform_db_write` / `tenant_db_write` 的分工：那两个是夹具，作用域是**整条用例**（含同用例
    其它夹具的 setup / teardown），只留给「跨多步的全局状态临界区」（如平台默认键的「复位 → 用例 →
    复位」）；单次写事务请用本函数，`async with write_window(...)` 包住的区间就是临界区。

    Args:
        db_key: 数据源键（平台库键取平台门，其余取租户门）。

    Returns:
        AbstractAsyncContextManager[None]: 写门上下文。
    """
    return db_access_gate(db_key, read_only=False, wait=DEFAULT_TIMEOUT)


def close_gates() -> None:
    """关闭所有门句柄（会话或进程退出时调用）。"""
    for target in _GATES.values():
        target.close()
    _GATES.clear()


def reset_gates() -> None:
    """关闭并清空门单例（用例隔离与诊断用，等价于 `close_gates`）。"""
    close_gates()
