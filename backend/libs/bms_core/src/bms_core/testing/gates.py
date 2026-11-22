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

import contextlib
import time
import traceback
from collections.abc import AsyncGenerator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager, suppress
from typing import Any

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.db.gate import db_access_gate
from bms_core.testing import diagnostics, lock_probe
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
            lock_probe.note("gate+", f"{name} ro")
            try:
                yield
            finally:
                lock_probe.note("gate-", f"{name} ro")
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
            lock_probe.note("gate+", f"{name} rw")
            try:
                yield
            finally:
                lock_probe.note("gate-", f"{name} rw")
        finally:
            # 无论是否报错都释放写门；没拿到（取写门就失败）时只记日志。
            # **同步释放**：用例 / 夹具被取消时 finally 里的 await 会立刻再抛 CancelledError，
            # 异步释放就走不完，写门深度永久多一层。这里先同步清账目与内核锁，再尽力恢复读份额。
            pending = target.release_write_now(restored)
            if pending:
                with suppress(BaseException):
                    await target.restore_reads(pending)
    except BaseException as exc:
        if stage == "hold":
            # 门内业务异常：与门等待区分开，避免把用例自身超时算成「等门超时」。
            outcome = "hold-error"
        else:
            outcome = f"{stage}-{'timeout' if isinstance(exc, TimeoutError) else 'error'}"
        lock_probe.note("error", f"{name} stage={stage} {type(exc).__name__} {str(exc)[:160]}")
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


class _GatedConnection:
    """连接代理：每次执行按操作取放门（读 / 写由包装方决定）。"""

    def __init__(self, connection: Any, scope: Callable[[], AbstractAsyncContextManager[None]]) -> None:
        """初始化。

        Args:
            connection: 底层异步连接。
            scope: 门上下文工厂（每次执行新建一个）。
        """
        object.__setattr__(self, "_connection", connection)
        object.__setattr__(self, "_scope", scope)

    async def execute(self, *args: object, **kwargs: object) -> Any:
        """执行 SQL（门内）；执行前本无事务时，执行后立即结束自动事务（释放数据库锁）。"""
        return await self._run("execute", *args, **kwargs)

    async def exec_driver_sql(self, *args: object, **kwargs: object) -> Any:
        """执行驱动级 SQL（门内）；自动事务随执行结束。"""
        return await self._run("exec_driver_sql", *args, **kwargs)

    async def scalar(self, *args: object, **kwargs: object) -> Any:
        """取首行首列（门内）；自动事务随执行结束。"""
        return await self._run("scalar", *args, **kwargs)

    async def scalars(self, *args: object, **kwargs: object) -> Any:
        """取标量集合（门内）；自动事务随执行结束。"""
        return await self._run("scalars", *args, **kwargs)

    async def _run(self, method: str, *args: object, **kwargs: object) -> Any:
        """门内执行一次连接方法，并在自动事务后立即回滚结束它。

        Args:
            method: 底层连接方法名。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            Any: 底层返回值。
        """
        connection = object.__getattribute__(self, "_connection")
        scope = object.__getattribute__(self, "_scope")
        auto = not connection.in_transaction()
        async with scope():
            value = await getattr(connection, method)(*args, **kwargs)
            if auto:
                with contextlib.suppress(Exception):
                    await connection.rollback()
        return value

    def __getattr__(self, name: str) -> Any:
        """其余属性 / 方法原样透传（commit / rollback / close 等）。"""
        return getattr(object.__getattribute__(self, "_connection"), name)


class GatedEngine:
    """共享测试库引擎代理：`connect()` 走读门、`begin()` 走写门，**每次执行取放一次**。

    为什么要有它：用例里大量直连 `shared_platform_engine` / `shared_tenant_engine` 开连接、开事务，
    不经过任何会话入口；这些读事务会长期持有 SQLite 读锁，24 路并行时写者在写门里等库锁满 10 秒。
    代理引擎把「所有直连读写」也纳入操作级门，用例无需改动。

    Attributes:
        url: 底层引擎连接串（透传）。
    """

    def __init__(self, engine: Any, gate_name: str) -> None:
        """初始化。

        Args:
            engine: 底层异步引擎。
            gate_name: 门名（诊断标签）。
        """
        object.__setattr__(self, "_engine", engine)
        object.__setattr__(self, "_gate_name", gate_name)

    @asynccontextmanager
    async def connect(self) -> AsyncGenerator[Any]:
        """打开连接（执行走读门）。"""
        gate_name = object.__getattribute__(self, "_gate_name")
        async with object.__getattribute__(self, "_engine").connect() as connection:
            yield _GatedConnection(connection, lambda: db_access_gate(gate_name, read_only=True, wait=DEFAULT_TIMEOUT))

    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[Any]:
        """打开写连接（执行走写门）；**不再开事务**，每条 SQL 自动提交。"""
        gate_name = object.__getattribute__(self, "_gate_name")
        async with object.__getattribute__(self, "_engine").connect() as connection:
            yield _GatedConnection(connection, lambda: db_access_gate(gate_name, read_only=False, wait=DEFAULT_TIMEOUT))

    async def dispose(self) -> None:
        """销毁底层引擎。"""
        await object.__getattribute__(self, "_engine").dispose()

    def __getattr__(self, name: str) -> Any:
        """其余属性 / 方法原样透传（`sync_engine` / `url` 等）。"""
        return getattr(object.__getattribute__(self, "_engine"), name)
