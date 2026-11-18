"""数据库门上下文（13_08）：按库名取门、读门 / 写门 / 升级写门。

口径（《测试规范》「并行与隔离」节）：

- 读门与写门的作用域都是**一次数据库操作**（一次会话），不是整条用例；
- 写门与所有读门互斥；写者等待期间新读者排在写者之后（写者优先，不被饿死）；
- 升级顺序固定为「让出读份额 → 取写门 → 放写门 → 取回读份额」，异常路径同序执行；
- 跨库同时需要写门时，固定「平台库在前、租户库在后」的嵌套顺序。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager

from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.registry import PLATFORM_DB_KEY
from bms_core.testing.rwlock import READ, DbGate, gate_path

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
async def read_gate(name: str) -> AsyncGenerator[None]:
    """读门上下文（共享，可与其它读者并发）。

    Args:
        name: 门名。

    Yields:
        None: 持读门区间。
    """
    target = gate(name)
    await target.acquire(write=False)
    try:
        yield
    finally:
        await target.release(write=False)


@asynccontextmanager
async def write_gate(name: str) -> AsyncGenerator[None]:
    """写门上下文（独占，持有期间新读者被挡住）。

    Args:
        name: 门名。

    Yields:
        None: 持写门区间。
    """
    target = gate(name)
    await target.acquire(write=True)
    try:
        yield
    finally:
        await target.release(write=True)


@asynccontextmanager
async def upgrade_to_write(name: str) -> AsyncGenerator[None]:
    """在已持读门的上下文内升级为写门。

    流程：释放全部读份额 → 取写门 → 用例块 → 放写门 → 重新取回读份额。
    **禁止持读门原地升级**：多个写者同时原地升级会互相等对方让出读份额而死锁。

    Args:
        name: 门名。

    Yields:
        None: 持写门区间（退出后恢复原读门深度）。
    """
    target = gate(name)
    depth = target.depth if target.mode == READ else 0
    for _ in range(depth):
        await target.release(write=False)
    try:
        await target.acquire(write=True)
    except BaseException:
        for _ in range(depth):
            await target.acquire(write=False)
        raise
    try:
        yield
    finally:
        await target.release(write=True)
        for _ in range(depth):
            await target.acquire(write=False)


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
    return write_gate(PLATFORM_GATE if db_key == PLATFORM_DB_KEY else TENANT_GATE)


def close_gates() -> None:
    """关闭所有门句柄（会话或进程退出时调用）。"""
    for target in _GATES.values():
        target.close()
    _GATES.clear()


def reset_gates() -> None:
    """关闭并清空门单例（用例隔离与诊断用，等价于 `close_gates`）。"""
    close_gates()
