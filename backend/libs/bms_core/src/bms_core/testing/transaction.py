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
from typing import Any, cast
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from bms_core.db.gate import LazyGatedSession, ReadOperationGatedSession, db_access_gate
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


def _sqlite_autocommit(engine: AsyncEngine) -> AsyncEngine:
    """仅对 SQLite 套 autocommit（正式数据库保持自己的事务语义）。

    这套「操作级读写锁 + 立即提交」只为绕开 SQLite 的库级读写独占；MySQL / PostgreSQL /
    达梦没有这个问题，测试与生产都按各自事务语义运行。

    Args:
        engine: 目标库引擎。

    Returns:
        AsyncEngine: SQLite 返回 autocommit 包装，其余原样。
    """
    if engine.url.get_backend_name() != "sqlite":
        return engine
    return engine.execution_options(isolation_level="AUTOCOMMIT")


@contextlib.asynccontextmanager
async def gated_session(engine: AsyncEngine, *, read_only: bool = True) -> AsyncGenerator[AsyncSession]:
    """直连共享引擎的会话：**按引擎所在库取门**，门的作用域是每次读 / 写操作。

    Args:
        engine: 目标库引擎（共享平台库 / 租户库；临时库不取门）。
        read_only: 只读 True；写 False。

    Yields:
        AsyncSession: 操作级门代理会话（SQLite 下 autocommit，其余库保持原事务语义）。
    """
    gate_name = gate_for_engine(engine)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(_sqlite_autocommit(engine), expire_on_commit=False)
    if gate_name is not None and read_only:
        # 读按操作：每次读新开短会话，读完即关（读锁随会话关闭释放）。
        yield cast(
            "AsyncSession", ReadOperationGatedSession(lambda: db_access_gate(gate_name, read_only=True), factory)
        )
        return
    async with factory() as session:
        if gate_name is None:
            yield session
            return
        # 写按操作：每个数据库方法调用取放一次写门（不整段持有）。
        proxy = LazyGatedSession(lambda: db_access_gate(gate_name, read_only=False), session)
        try:
            yield cast("AsyncSession", proxy)
        finally:
            await proxy.aclose()


@contextlib.asynccontextmanager
async def _write_scope(engine: AsyncEngine, *, savepoint: bool) -> AsyncGenerator[AsyncSession]:
    """测试侧写会话的**唯一实现**：autocommit 会话 + 操作级写门。

    2026-11-21 口径（业主拍板）：**不再用「外层事务 + 退出回滚」**。每次 SQL 立即落库、立即
    释放数据库锁，门只覆盖这一次写操作。用例隔离靠命名空间（`ns`）与按用例清理，不靠「整条
    用例回滚」——那种写法既掩盖了真实写入路径，又把锁（或数据库事务）拉到整条用例，
    24 路并行时必然互相拖死。

    互斥**只由门提供**：本函数不另外取 SQLite 锁，也不允许别处绕过门单独取库锁。

    Args:
        engine: 目标库引擎。
        savepoint: 保留形参以兼容既有调用点；**不再使用事务 / savepoint**。

    Yields:
        AsyncSession: 操作级门代理会话（autocommit）。

    Raises:
        Exception: 用例体内的异常原样抛出。
    """
    del savepoint
    gate_name = gate_for_engine(engine)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(_sqlite_autocommit(engine), expire_on_commit=False)
    async with factory() as session:
        exposed: AsyncSession = (
            cast("AsyncSession", LazyGatedSession(lambda: db_access_gate(gate_name, read_only=False), session))
            if gate_name is not None
            else session
        )
        try:
            with _patch_session_factory(exposed):
                yield exposed
        finally:
            await session.close()


@contextlib.asynccontextmanager
async def write_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """开启写会话：**autocommit + 操作级写门**（每条 SQL 立即落库、立即放锁）。

    与 `rollback_session` 的区别是**不改写 `SessionFactory.create`**——被测代码自建的会话
    照常开自己的连接，因此只适用于「用例与被测代码共用同一个会话」的形态（服务层直调、
    或经依赖覆盖注入会话的接口用例）。

    Args:
        engine: 目标库引擎（通常是共享平台 / 租户库夹具）。

    Yields:
        AsyncSession: 操作级门代理会话（写入即落库，不回滚）。

    Raises:
        Exception: 用例体内的异常原样抛出。
    """
    async with _write_scope(engine, savepoint=False) as session:
        yield session


@contextlib.asynccontextmanager
async def rollback_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """开启写会话（历史名保留）：**autocommit + 操作级写门**，不再整条用例回滚。

    2026-11-21 业主拍板：`rollback_session` 的「退出整体回滚」是旧做法的产物（用事务替用例
    做清理，同时把锁拉到整条用例）。现在写入即落库，用例隔离靠命名空间与按用例清理。

    Args:
        engine: 目标库引擎。

    Yields:
        AsyncSession: 操作级门代理会话。

    Raises:
        Exception: 用例体内的异常原样抛出。
    """
    async with _write_scope(engine, savepoint=True) as session:
        yield session
