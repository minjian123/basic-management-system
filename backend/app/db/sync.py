"""达梦同步门面：无异步方言的库（`dm`）以阻塞驱动 + 线程池接入异步应用。

- **方言判定**：`SYNC_ONLY_DIALECTS` 与 `is_sync_only_url` 是「哪些方言只能走同步路径」的
  唯一来源（`app/db/engine.py` 复用该常量，避免两处漂移）。
- **`SyncSession`**：阻塞 `sqlalchemy.orm.Session` 的异步门面——除纯内存调用（`add` /
  `delete` / `get_bind` 不产生 IO）外，全部经 `asyncio.to_thread` 执行，协程语义与
  `AsyncSession` 对齐，使达梦在异步应用内可跑（会话入口 `session_scope` 按方言分流）。
- **`sync_session_scope`**：由同步引擎开会话 → 让出 `SyncSession` → 关闭。
- **退役条件**：达梦官方若提供异步方言驱动，本模块整体退役（改走 `AsyncSession` 路径）。
- 会话类型口径与登记见《后端基类清单》「数据访问与多租户基座」节。
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from sqlalchemy import Engine, Result
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.sql.base import Executable

from app.core.base import BaseObject

SYNC_ONLY_DIALECTS: frozenset[str] = frozenset({"dm"})
"""无异步方言、仅同步驱动的方言（达梦）。"""


def is_sync_only_url(url: str) -> bool:
    """按连接串判定是否仅同步方言。

    Args:
        url: 数据库连接串。

    Returns:
        bool: 仅同步方言 True（`dm`）。
    """
    return make_url(url).get_backend_name() in SYNC_ONLY_DIALECTS


class _SyncTransaction(BaseObject):
    """同步会话的事务边界（`DbUnitOfWork.begin()` 的异步上下文管理器形态）。"""

    def __init__(self, session: Session) -> None:
        """初始化。

        Args:
            session: 阻塞会话。
        """
        self._session = session

    async def __aenter__(self) -> object:
        """开启事务。

        Returns:
            object: 事务边界对象自身。
        """
        await asyncio.to_thread(self._session.begin)
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """提交（正常退出）或回滚（异常退出）并结束事务。"""
        if exc_type is None:
            await asyncio.to_thread(self._session.commit)
        else:
            await asyncio.to_thread(self._session.rollback)


class SyncSession(BaseObject):
    """阻塞会话的异步门面（达梦等无异步方言）：阻塞调用统一在线程池执行。"""

    def __init__(self, engine: Engine) -> None:
        """初始化（建阻塞会话，不建连）。

        Args:
            engine: 同步引擎。
        """
        self._session = Session(engine, expire_on_commit=False)

    @property
    def raw(self) -> Session:
        """底层阻塞会话（门面未覆盖的能力经此逃生；调用方自行保证线程安全）。

        Returns:
            Session: 阻塞会话。
        """
        return self._session

    async def execute(self, statement: Executable, *args: Any, **kwargs: Any) -> Result[Any]:
        """执行语句（线程池）。

        Args:
            statement: SQLAlchemy 语句。
            *args: 位置参数。
            **kwargs: 关键字参数。

        Returns:
            Result[Any]: 执行结果。
        """
        return await asyncio.to_thread(self._session.execute, statement, *args, **kwargs)

    def add(self, instance: object) -> None:
        """加入待写对象（纯内存操作，不产生 IO）。"""
        self._session.add(instance)

    async def delete(self, instance: object) -> None:
        """标记删除（线程池）。"""
        await asyncio.to_thread(self._session.delete, instance)

    async def refresh(self, instance: object, **kwargs: Any) -> None:
        """刷新对象（线程池）。"""
        await asyncio.to_thread(self._session.refresh, instance, **kwargs)

    async def get(self, entity: Any, ident: Any, **kwargs: Any) -> Any:
        """按主键取对象（线程池）。"""
        return await asyncio.to_thread(self._session.get, entity, ident, **kwargs)

    async def flush(self) -> None:
        """刷写待写变更（线程池）。"""
        await asyncio.to_thread(self._session.flush)

    async def commit(self) -> None:
        """提交事务（线程池）。"""
        await asyncio.to_thread(self._session.commit)

    async def rollback(self) -> None:
        """回滚事务（线程池）。"""
        await asyncio.to_thread(self._session.rollback)

    async def close(self) -> None:
        """关闭会话（线程池）。"""
        await asyncio.to_thread(self._session.close)

    def get_bind(self) -> Any:
        """取会话绑定（引擎 / 连接）。"""
        return self._session.get_bind()

    def begin(self) -> AbstractAsyncContextManager[object]:
        """开启事务边界（返回异步上下文管理器，与 `AsyncSession.begin()` 同形）。

        Returns:
            AbstractAsyncContextManager[object]: 事务边界。
        """
        return _SyncTransaction(self._session)

    async def __aenter__(self) -> SyncSession:
        """进入会话上下文。

        Returns:
            SyncSession: 会话门面自身。
        """
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """退出会话上下文（关闭会话）。"""
        await self.close()


type DbSession = AsyncSession | SyncSession
# 会话公共契约：异步会话（各异步方言）或同步门面（达梦等同步方言）；两项须共同覆盖服务 /
# 仓储 / 租户源实际使用的方法集（execute / add / delete / refresh / get / flush / commit /
# rollback / close / get_bind）；新增会话方法须在契约与两处实现同步（登记见《后端基类清单》）。


@asynccontextmanager
async def sync_session_scope(engine: Engine) -> AsyncGenerator[SyncSession]:
    """同步会话作用域：开会话 → 让出门面 → 关闭（异常原样上抛）。

    Args:
        engine: 同步引擎。

    Yields:
        SyncSession: 阻塞会话的异步门面。
    """
    session = SyncSession(engine)
    try:
        yield session
    finally:
        await session.close()
