"""数据库门上下文（13_08）：**取门只有一条路径** `gate_scope`。

口径（《测试规范》「并行与隔离」节）：

- **一律先加读锁**：读操作持读锁执行；写操作先持读锁进来，再让出读份额升到写锁；
- 读门之间共享、写门与所有读门互斥；写门持有期间新读锁加不上，不会读到写了一半的数据；
- 作用域是**一次数据库操作**（一次会话），不是整条用例；
- 升级顺序固定为「让出读份额 → 取写门 → 放写门 → 取回读份额」，异常路径同序执行；
- **全库一把门**（13_08 T7，2026-11-20 拍板）：平台库与租户库**共用同一把读写门**。

为什么不再按数据源分把：一个请求常常同时碰两个库（平台库存表单元数据、租户库存布局与
自建字段），而门的粒度是「请求级会话」。两个进程各持一把、互等对方那把，就构成跨库 ABBA
死锁——实测 24 路并行时每轮稳定在同样几个用例卡满 30 秒，把整批拖到 3~5 分钟。合成一把后，
同一时刻最多一个写者，「持 A 库门等 B 库门」在结构上不可能出现，也不必再靠「谁在前谁在后」
的约定维持正确性；代价只是跨库写不再并行（SQLite 单文件写本来就是串行，读仍并行）。
"""

from __future__ import annotations

import time
import traceback
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.gate import db_access_gate
from bms_core.testing import diagnostics
from bms_core.testing.rwlock import DEFAULT_TIMEOUT, GATE_LABEL, DbGate, gate_path

PLATFORM_GATE = "platform"
"""平台库门名（诊断标签；与租户库共用同一把内核门，见模块说明）。"""

TENANT_GATE = "tenant"
"""租户库门名（诊断标签；与平台库共用同一把内核门，见模块说明）。"""

GLOBAL_GATE = "all"
"""全局门的锁文件名（`db-gate-all.lock`）：全库读写共用一把。"""

_GATES: ConcurrentStableDict[str, DbGate] = ConcurrentStableDict()
"""门单例（进程内复用同一句柄；`-n auto` 下由操作系统保证跨进程互斥）。"""


def gate(name: str) -> DbGate:
    """取（或创建）**全局门**单例。

    13_08 T7 起门不再按数据源区分：`name` 只用于诊断标签（日志 / 持有者记录里写
    `platform` / `tenant`），底层锁文件恒为 `db-gate-all.lock`，跨库写因此不可能互相等待。

    Args:
        name: 诊断标签（`platform` / `tenant`），不决定锁文件。

    Returns:
        DbGate: 全局门实例。
    """
    existing = _GATES.get(GLOBAL_GATE)
    if existing is not None:
        return existing
    created = DbGate(GLOBAL_GATE, gate_path(GLOBAL_GATE))
    _GATES[GLOBAL_GATE] = created
    return created


@asynccontextmanager
async def gate_scope(name: str, *, read_only: bool, wait: float | None = None) -> AsyncGenerator[None]:
    """**取门的唯一入口**：一律先加读锁，写操作再让出读份额升到写锁。

    结构固定为「读锁打底 → （写）让读 → 取写 → 写 → 放写 → 补回读 → 放读」，异常路径同序：

    - 写路径的 `try` 包住「让出读份额 → 取写门 → 执行写」三件事；
    - 它的 `finally` 先放写门、再补回读锁；写门没拿到时 `release_write` 只记日志不抛错；
    - 最外层 `finally` 释放读锁。

    **等待时长在异常路径也要记**（13_08 T7）：等读门 / 等写门超时时 `await` 直接抛异常，
    原先的 `wait_read = …` / `wait_write = …` 会被跳过，`held = elapsed - 0 - 0` 就把整段
    等待算成「门内实占」——实测把 180s 等门超时误报成「持门 180s」。现在两段等待都在
    `finally` 里按「进入前时刻」结算，异常行的「结果」列写明阶段，选表时先看这一列。

    Args:
        name: 门名。
        read_only: 只读 True（持读锁执行），写 False（升到写锁执行）。
        wait: 等待上限（秒）；None 走默认（写门 5s，可用环境变量覆盖）。

    Yields:
        None: 门内区间。
    """
    target = gate(name)
    label_token = GATE_LABEL.set(name)
    started = time.monotonic()
    frames = ""
    if diagnostics.hold_enabled():
        frames = " <- ".join(
            line.strip().splitlines()[0]
            for line in traceback.format_stack()[-8:-2]
            if line.strip() and "contextlib.py" not in line and "gates.py" not in line
        )
    wait_read = 0.0
    wait_write = 0.0
    reentered = False
    holders_before = ""
    token: int | None = None
    restored: ConcurrentStableList[int] = ConcurrentStableList()
    stage = "read"
    outcome = "ok"
    try:
        read_started = time.monotonic()
        try:
            token = await target.acquire_read()
        finally:
            wait_read = time.monotonic() - read_started
        if read_only:
            stage = "hold"
            yield
            return
        stage = "write"
        try:
            # 解锁读锁：让出自己这份份额（同进程其它会话的份额不受影响）。
            assert token is not None
            await target.release_read(token)
            # 进入前先抓一份持有者：进程级写门可重入，`wait_write≈0` 既可能是「没人占」，
            # 也可能是「同进程另一协程占着」；读持有者同理——SQLite rollback journal 下
            # 别人开着的读事务会把写者挡住，而等写门那一列看不出来（13_08 调优）。
            reentered = len(target.write_holders()) > 0
            holders_before = " | ".join(target.holder_tasks())
            # 并发的写在这里排队；拿到写门后独占，期间新读锁加不上。
            write_wait_start = time.monotonic()
            try:
                restored = await target.acquire_write(wait=wait)
            finally:
                wait_write = time.monotonic() - write_wait_start
            stage = "hold"
            yield
        finally:
            # 无论是否报错都释放写门；没拿到（取写门就失败）时只记日志。
            # `release_write` 会把升级时让出的读份额**原样补回**，故这里不再另取新份额：
            # 多取一份就永远没人释放（实测每升级一次漏一份读份额，最终读者的内核共享锁
            # 长期不放，写者只能等满硬上限）。
            await target.release_write(restored)
    except BaseException as exc:
        if stage == "hold":
            # 门内业务异常：与门等待区分开，避免把用例自身超时算成「等门超时」。
            outcome = "hold-error"
        else:
            outcome = f"{stage}-{'timeout' if isinstance(exc, TimeoutError) else 'error'}"
        raise
    finally:
        # 读门等待超时时 `token` 从未赋值：此时只落一行记录，不做释放。
        if token is not None:
            # 写路径补回读份额失败时 token 已失效，释放只销账不掩盖原始异常。
            with suppress(RuntimeError):
                await target.release_read(token)
        elapsed = time.monotonic() - started
        # 实占 = 总时长 − 等读 − 等写门；三段落盘才能区分「在门口排队」与「区间内真持有」，
        # 压测调优只认后者是串行成本（前者是争用产物，随排队消失自然下降）。
        held = max(elapsed - wait_read - wait_write, 0.0)
        diagnostics.note_hold(
            name,
            elapsed,
            read_only=read_only,
            wait_read=wait_read,
            wait_write=wait_write,
            held=held,
            reentered=reentered,
            outcome=outcome,
        )
        diagnostics.note_slow_hold(
            name,
            elapsed,
            read_only=read_only,
            wait_read=wait_read,
            wait_write=wait_write,
            held=held,
            frames=frames,
            reentered=reentered,
            holders=holders_before,
            outcome=outcome,
        )
        GATE_LABEL.reset(label_token)


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
