"""数据库门上下文（13_08）：**取门只有一条路径** `gate_scope`。

口径（《测试规范》「并行与隔离」节）：

- **一律先加读锁**：读操作持读锁执行；写操作先持读锁进来，再让出读份额升到写锁；
- 读门之间共享、写门与所有读门互斥；写门持有期间新读锁加不上，不会读到写了一半的数据；
- 作用域是**一次数据库操作**（一次会话），不是整条用例；
- 升级顺序固定为「让出读份额 → 取写门 → 放写门 → 取回读份额」，异常路径同序执行；
- 跨库同时需要写门时，固定「平台库在前、租户库在后」的嵌套顺序。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.gate import db_access_gate
from bms_core.testing.rwlock import DbGate, gate_path

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
async def gate_scope(name: str, *, read_only: bool) -> AsyncGenerator[None]:
    """**取门的唯一入口**：一律先加读锁，写操作再让出读份额升到写锁。

    顺序固定为「读锁打底 → （写）让读 → 取写 → 放写 → 取回读 → 放读」，异常路径同序。
    这样全仓只有一种锁序：读操作持读锁执行；写操作先持读锁进来，再独占写门完成写入，
    写期间新读锁加不上，因此不存在「读到写了一半的数据」。

    Args:
        name: 门名。
        read_only: 只读 True（持读锁执行），写 False（升到写锁执行）。

    Yields:
        None: 门内区间。
    """
    target = gate(name)
    token = await target.acquire_read()
    try:
        if read_only:
            yield
            return
        # 让出**自己这份**读份额（不影响同进程其它会话的份额），再排队取写门。
        try:
            restored = await target.acquire_write()
        except BaseException:
            # 取写门可能已让出本任务的读份额（等锁超时）：此时补回一份，保证退出路径一致；
            # 若因「其它任务持读」而报错，自己的份额还在，不能重复取。
            if not target.owns(token):
                token = await target.acquire_read()
            raise
        try:
            yield
        finally:
            await target.release_write(restored)
        # 让出的份额已由 `release_write` 恢复，`token` 仍然有效；这里**不得**再取一次读锁
        # （那会在写门刚释放时去抢共享锁，被等待中的写者挡住，最长 180s）。
    finally:
        await target.release_read(token)


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
    return db_access_gate(db_key, read_only=False)


def close_gates() -> None:
    """关闭所有门句柄（会话或进程退出时调用）。"""
    for target in _GATES.values():
        target.close()
    _GATES.clear()


def reset_gates() -> None:
    """关闭并清空门单例（用例隔离与诊断用，等价于 `close_gates`）。"""
    close_gates()
