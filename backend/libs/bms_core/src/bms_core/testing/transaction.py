"""统一事务回滚内核（13_04）：外层事务 + savepoint + 会话工厂接管。

口径（《测试规范》「测试公共基座」节）：

1. 夹具开启**外层事务**（`connection.begin()`），用例内的 `commit()` 只提交 savepoint；
2. 夹具结束**整体回滚**，用例间互不可见、不落盘；
3. 被测代码自建的会话经 **patch `SessionFactory.create`** 复用同一外层会话——不 patch
   `session_scope` 函数本身（其时被测模块多为 `from … import session_scope`，patch 模块属性无效）；
4. 同步方言（达梦）走 `registry.get_sync` 分支，不经过该工厂，**本夹具不覆盖**；
5. SQLite 事务一律 `BEGIN IMMEDIATE`（`begin_write`）：「先读后写」的延迟事务在升级写锁时若他人
   持写锁会**立即** `database is locked`，`busy_timeout` 对升级死锁不等待；开头就拿写锁，冲突
   退化为 `busy_timeout` 下的短等待（共享引擎 30s）。
6. **13_08：整段回滚区间在跨进程写门内执行**。回滚会话的写事务跨整条用例持有，与读写门是两套
   互斥——不取门时其它 worker 的写会话会在 SQLite 层盲等 `busy_timeout`（30s，无诊断）；
   取门后与经会话入口的写排同一条队，等门有 10s 告警 / 180s 超时。该夹具仍属**待淘汰**
   （《测试规范》§2.1 第 9 条「回滚式隔离仅限登记用例」），新用例用命名空间隔离。
7. **淘汰路径**：用例与被测代码共用同一会话时改 `write_session`（不取门、不改写会话工厂、
   退出不提交），单次写用 `write_window`；只有「被测代码必须自建会话并复用外层事务」的形态
   （作业内部 `session.begin()`、声明装载等）才保留 `rollback_session`。
"""

import contextlib
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.db.session import SessionFactory
from bms_core.testing.gates import PLATFORM_GATE, TENANT_GATE, write_gate


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


def needs_explicit_begin(dialect_name: str) -> bool:
    """是否需要显式 `BEGIN`（SQLite 的 pysqlite / aiosqlite legacy 模式延迟到首条 DML 才真正开事务）。

    Args:
        dialect_name: 数据库方言名（`sqlite` / `postgresql` / `mysql` / `dm`）。

    Returns:
        bool: SQLite 返回 `True`。
    """
    return dialect_name == "sqlite"


async def begin_write(connection: AsyncConnection) -> None:
    """SQLite 上把当前事务开成 `BEGIN IMMEDIATE`（写锁前置），其它方言不做任何事。

    为什么需要：SQLite 的延迟事务是「先 SELECT 再 INSERT/UPDATE」形态，读锁升级写锁时若另一连接
    正持写锁会**立即** `database is locked`——`busy_timeout` 对升级死锁不生效（等待也推进不了）。
    开头就拿写锁，冲突退化为 `busy_timeout` 下的短等待。**只用于确定要写的事务**（回滚夹具、
    作业批写）：读路径若也前置写锁，会把纯读并发压成串行，长事务持有写锁还会把别人卡到超时。

    Args:
        connection: 已 `begin()` 但尚未发出 DML 的连接（SQLite 此时 DBAPI 层还没有事务）。
    """
    if needs_explicit_begin(connection.dialect.name):
        await connection.exec_driver_sql("BEGIN IMMEDIATE")


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


def gate_for_engine(engine: AsyncEngine) -> str | None:
    """按引擎库文件推断写门名（只认共享平台的 `platform` / `tenant` 两个逻辑数据源）。

    Args:
        engine: 目标库引擎。

    Returns:
        str | None: 门名；临时库 / 非 SQLite 返回 None（不取门）。
    """
    database = engine.url.database or ""
    if not database or ":memory:" in database:
        return None
    stem = Path(database).stem
    return stem if stem in (PLATFORM_GATE, TENANT_GATE) else None


@contextlib.asynccontextmanager
async def write_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """开启「不提交」写会话：事务开头取 SQLite 写锁，退出时不提交（等价整体回滚）。

    与 `rollback_session` 的区别只有两点，都是 13_08 的收口方向：

    1. **不取跨进程写门**：写冲突交给 SQLite 的 `busy_timeout` 短等待，而不是应用层文件锁；
    2. **不改写 `SessionFactory.create`**：被测代码自建的会话照常开自己的连接，因此只适用于
       「用例与被测代码共用同一个会话」的形态（服务层直调、或经依赖覆盖注入会话的接口用例）。

    用例内的 `commit()` 会真提交（本函数不拦），需要「数据不落库」时用 `flush()`。

    Args:
        engine: 目标库引擎（通常是共享平台 / 租户库夹具）。

    Yields:
        AsyncSession: 已 `BEGIN IMMEDIATE`、退出即回滚的会话。

    Raises:
        Exception: 用例体内的异常原样抛出（回滚在 `finally` 由会话关闭完成）。
    """
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        # SQLite 延迟到首条 DML 才真正 BEGIN；显式前置写锁，避免「先读后写」升级时立即
        # `database is locked`（`busy_timeout` 对升级死锁不生效，见 `begin_write`）。
        await begin_write(await session.connection())
        yield session


@contextlib.asynccontextmanager
async def rollback_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """开启回滚会话：用例结束整体回滚（整段区间在库写门内执行）。

    Args:
        engine: 目标库引擎。

    Yields:
        AsyncSession: 绑定外层事务（savepoint 模式）的会话。

    Raises:
        Exception: 用例体内的异常原样抛出（回滚在 `finally` 中完成）。
    """
    gate_name = gate_for_engine(engine)
    scope = write_gate(gate_name) if gate_name is not None else contextlib.nullcontext()
    async with scope:
        connection = await engine.connect()
        transaction = await connection.begin()
        # SQLite 延迟到首条 DML 才真正 BEGIN；显式开事务保证 savepoint 不成为最外层事务（`begin_write` 内
        # 同时做「写锁前置」，口径见模块文档第 5 条）。
        await begin_write(connection)
        session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
        try:
            with _patch_session_factory(session):
                yield session
        finally:
            await session.close()
            await transaction.rollback()
            await connection.close()
