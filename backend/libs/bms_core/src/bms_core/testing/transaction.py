"""统一事务回滚内核（13_04）：外层事务 + savepoint + 会话工厂接管。

口径（《测试规范》「测试公共基座」节）：

1. 夹具开启**外层事务**（`connection.begin()`），用例内的 `commit()` 只提交 savepoint；
2. 夹具结束**整体回滚**，用例间互不可见、不落盘；
3. 被测代码自建的会话经 **patch `SessionFactory.create`** 复用同一外层会话——不 patch
   `session_scope` 函数本身（其时被测模块多为 `from … import session_scope`，patch 模块属性无效）；
4. 同步方言（达梦）走 `registry.get_sync` 分支，不经过该工厂，**本夹具不覆盖**。
"""

import contextlib
from collections.abc import AsyncGenerator
from typing import Any
from unittest import mock

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from bms_core.db.session import SessionFactory


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


@contextlib.asynccontextmanager
async def rollback_session(engine: AsyncEngine) -> AsyncGenerator[AsyncSession]:
    """开启回滚会话：用例结束整体回滚。

    Args:
        engine: 目标库引擎。

    Yields:
        AsyncSession: 绑定外层事务（savepoint 模式）的会话。

    Raises:
        Exception: 用例体内的异常原样抛出（回滚在 `finally` 中完成）。
    """
    connection = await engine.connect()
    transaction = await connection.begin()
    if needs_explicit_begin(connection.dialect.name):
        # SQLite（pysqlite / aiosqlite legacy 隔离模式）延迟到首条 DML 才真正 BEGIN；
        # 此时会话的 savepoint 会成为最外层事务并被 commit 提交。显式 BEGIN 保证外层事务真实存在。
        await connection.exec_driver_sql("BEGIN")
    session = AsyncSession(bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        with _patch_session_factory(session):
            yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
