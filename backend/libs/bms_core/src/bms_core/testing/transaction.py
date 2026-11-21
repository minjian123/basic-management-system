"""统一事务回滚内核（13_04）：外层事务 + savepoint + 会话工厂接管。

口径（《测试规范》「测试公共基座」节）：

1. 夹具开启**外层事务**（`connection.begin()`），用例内的 `commit()` 只提交 savepoint；
2. 夹具结束**整体回滚**，用例间互不可见、不落盘；
3. 被测代码自建的会话经 **patch `SessionFactory.create`** 复用同一外层会话——不 patch
   `session_scope` 函数本身（其时被测模块多为 `from … import session_scope`，patch 模块属性无效）；
4. 同步方言（达梦）走 `registry.get_sync` 分支，不经过该工厂，**本夹具不覆盖**；
5. **门是唯一的互斥**：持门期间不存在第二个写者，事务用默认的延迟事务即可，不再额外前置
   SQLite 写锁（`BEGIN IMMEDIATE` 已删除）。绕过门的直连写由 `busy_timeout` 兜底。
6. **13_08：整段回滚区间在跨进程写门内执行**。回滚会话的写事务跨整条用例持有，与读写门是两套
   互斥——不取门时其它 worker 的写会话会在 SQLite 层盲等 `busy_timeout`（10s，无诊断）；
   取门后与经会话入口的写排同一条队，等门 5s 硬超时（读门 / 整段区 10s）。该夹具仍属**待淘汰**
   （《测试规范》§2.1 第 9 条「回滚式隔离仅限登记用例」），新用例用命名空间隔离。
7. **淘汰路径**：用例与被测代码共用同一会话时改 `write_session`（取门、不改写会话工厂、
   退出不提交），单次写用 `write_window`；只有「被测代码必须自建会话并复用外层事务」的形态
   （作业内部 `session.begin()`、声明装载等）才保留 `rollback_session`。
"""

import contextlib
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager
from pathlib import Path
from typing import Any
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.db.gate import db_access_gate
from bms_core.db.session import SessionFactory
from bms_core.testing.gates import PLATFORM_GATE, TENANT_GATE


class _ReuseScope:
    """会话工厂替身：每次调用都返回「复用同一会话、退出不关闭」的上下文管理器。"""

    def __init__(self, session: AsyncSession) -> None:
        """保存待复用的会话。

        Args:
            session: 外层事务上的会话。
        """
        self._session = session

    def __call__(self) -> contextlib.AbstractAsyncContextManager[AsyncSession]:
        """返回会话上下文管理器（供 `async with factory.create(engine)() as session` 使用）。

        Returns:
            contextlib.AbstractAsyncContextManager[AsyncSession]: 复用会话的上下文管理器。
        """
        return self._scope()

    @contextlib.asynccontextmanager
    async def _scope(self) -> AsyncGenerator[AsyncSession]:
        """产出复用会话（不提交、不关闭，生命周期由外层夹具管理）。

        Yields:
            AsyncSession: 外层会话。
        """
        yield self._session


def _patch_session_factory(session: AsyncSession) -> Any:
    """把 `SessionFactory.create` 替换为复用 `session` 的实现。

    Args:
        session: 外层事务上的会话。

    Returns:
        Any: 已启动的 patch 上下文（调用方负责退出）。
    """
    scope = _ReuseScope(session)

    def _create(self: SessionFactory, options: object = None) -> _ReuseScope:
        """返回复用会话的工厂替身（忽略原始选项）。"""
        return scope

    return mock.patch.object(SessionFactory, "create", _create)


def gate_for_database(database: str | None) -> str | None:
    """按库文件路径推断写门名（只认共享平台的 `platform` / `tenant` 两个逻辑数据源）。

    Args:
        database: 库文件路径（SQLite 连接串的 `database` 段；内存库 / 空串可传）。

    Returns:
        str | None: 门名；临时库 / 内存库 / 非 SQLite 返回 None（不取门）。
    """
    if not database or ":memory:" in database:
        return None
    stem = Path(database).stem
    return stem if stem in (PLATFORM_GATE, TENANT_GATE) else None


def gate_for_engine(engine: AsyncEngine) -> str | None:
    """按引擎库文件推断写门名（只认共享平台的 `platform` / `tenant` 两个逻辑数据源）。

    Args:
        engine: 目标库引擎。

    Returns:
        str | None: 门名；临时库 / 非 SQLite 返回 None（不取门）。
    """
    return gate_for_database(engine.url.database)


class GatedSessionMaker:
    """自带门的会话工厂：`async with maker() as session` 进入即取门、退出即放。

    用途：把测试里 `async_sessionmaker(shared_*_engine, ...)` 原样换成本类，调用点不用动，
    所有直连引擎的读写就都走 `db_access_gate` 这一个入口。
    """

    def __init__(self, engine: AsyncEngine, *, read_only: bool = False) -> None:
        """初始化。

        Args:
            engine: 目标库引擎。
            read_only: 只读 True；写（含需要写的事务）用 False。
        """
        self._engine = engine
        self._read_only = read_only

    def __call__(self) -> AbstractAsyncContextManager[AsyncSession]:
        """返回门内会话的上下文。

        Returns:
            AbstractAsyncContextManager[AsyncSession]: 会话上下文。
        """
        return gated_session(self._engine, read_only=self._read_only)


def gated_sessionmaker(engine: AsyncEngine, *, read_only: bool = False) -> GatedSessionMaker:
    """构造自带门的会话工厂（替换 `async_sessionmaker(engine)` 用）。

    Args:
        engine: 目标库引擎。
        read_only: 只读 True；写 False。

    Returns:
        GatedSessionMaker: 可直接调用的会话工厂。
    """
    return GatedSessionMaker(engine, read_only=read_only)


@contextlib.asynccontextmanager
async def gated_session(engine: AsyncEngine, *, read_only: bool = True) -> AsyncGenerator[AsyncSession]:
    """直连共享引擎的会话：**按引擎所在库取门**，临界区＝会话生命周期。

    直连引擎（`shared_*_engine`）拿不到请求入口，原先不取门；它的读事务会和别人的写门
    叠在一起（SQLite 上表现为写请求卡到 `busy_timeout` 10s、门被长期占住）。这里统一补上：
    读会话持读门，写会话（`read_only=False`）走 `gate_scope` 的升级路径。

    Args:
        engine: 目标库引擎（共享平台库 / 租户库；临时库不取门）。
        read_only: 只读 True；写 False。

    Yields:
        AsyncSession: 门内会话（退出即关闭、未提交的改动回滚）。
    """
    gate_name = gate_for_engine(engine)
    scope = db_access_gate(gate_name, read_only=read_only) if gate_name is not None else contextlib.nullcontext()
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with scope, factory() as session:
        yield session


@contextlib.asynccontextmanager
async def _write_scope(engine: AsyncEngine, *, savepoint: bool) -> AsyncGenerator[AsyncSession]:
    """测试侧写会话的**唯一实现**：取库写门 → 产出会话（退出即回滚）。

    互斥**只由门提供**（设计决策 2 / 3）：本函数不取任何 SQLite 写锁，也不允许别处绕过门
    单独取库锁——两套锁序混用即锁序反转，24 路并行时表现为大量「等待门 已 10.0s」与整轮停滞。

    `savepoint=True` 把会话绑到外层事务（`join_transaction_mode="create_savepoint"`），并改写
    `SessionFactory.create` 让被测代码自建的会话复用同一事务；`savepoint=False` 用普通会话，
    被测代码自建的会话照常开自己的连接。

    Args:
        engine: 目标库引擎。
        savepoint: 是否使用外层事务 + savepoint 形态。

    Yields:
        AsyncSession: 已取门、未预开事务的会话。

    Raises:
        Exception: 用例体内的异常原样抛出（回滚在 `finally` 完成）。
    """
    gate_name = gate_for_engine(engine)
    scope = db_access_gate(gate_name, read_only=False) if gate_name is not None else contextlib.nullcontext()
    async with scope:
        if not savepoint:
            factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
            async with factory() as session:
                yield session
            return
        connection = await engine.connect()
        transaction = await connection.begin()
        # pysqlite 的延迟事务不发 BEGIN：不显式开事务时 SAVEPOINT 会退化成最外层事务，
        # 用例内的 `commit()` 就直落库了。这里只发**普通** BEGIN（不取写锁）——
        # 互斥由门提供，事务边界只负责 savepoint 语义。
        await connection.exec_driver_sql("BEGIN")
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            with _patch_session_factory(session):
                yield session
        finally:
            await session.close()
            await transaction.rollback()
            await connection.close()


@contextlib.asynccontextmanager
async def write_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """开启「不提交」写会话：进入即取库写门并前置 SQLite 写锁，退出不提交（等价整体回滚）。

    与 `rollback_session` 的唯一区别是**不改写 `SessionFactory.create`**——被测代码自建的
    会话照常开自己的连接，因此只适用于「用例与被测代码共用同一个会话」的形态（服务层直调、
    或经依赖覆盖注入会话的接口用例）。门与锁的取用顺序见 `_write_scope`（全仓唯一实现）。

    用例内的 `commit()` 会真提交（本函数不拦），需要「数据不落库」时用 `flush()`。

    Args:
        engine: 目标库引擎（通常是共享平台 / 租户库夹具）。

    Yields:
        AsyncSession: 已取门、已 `BEGIN IMMEDIATE`、退出即回滚的会话。

    Raises:
        Exception: 用例体内的异常原样抛出（回滚在 `finally` 由会话关闭完成）。
    """
    async with _write_scope(engine, savepoint=False) as session:
        yield session


@contextlib.asynccontextmanager
async def rollback_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """开启回滚会话：用例结束整体回滚（外层事务 + savepoint，门与库锁经唯一实现取用）。

    Args:
        engine: 目标库引擎。

    Yields:
        AsyncSession: 绑定外层事务（savepoint 模式）的会话。

    Raises:
        Exception: 用例体内的异常原样抛出（回滚在 `finally` 中完成）。
    """
    async with _write_scope(engine, savepoint=True) as session:
        yield session
