"""异步会话工厂与请求级依赖：`SessionFactory` + `get_db` / `get_uow`。

禁止异步会话跨请求共享；每请求独立会话，退出即释放。
工厂链：`SessionFactory → BaseDbFactory → BaseFactory → BasePluggable`（02-54）；实现可替换
（插件键 `session_factory`，配置经 `[session_factory].provider` 选择，缺省 `default`）。
"""

from collections.abc import AsyncIterator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.factory import BaseDbFactory
from app.db.registry import EngineRegistry
from app.db.unit_of_work import DbUnitOfWork


class SessionFactory(BaseDbFactory[AsyncEngine, async_sessionmaker[AsyncSession]]):
    """异步会话工厂：由引擎产出 `async_sessionmaker`。"""

    key: str = "session_factory"

    def create(self, options: AsyncEngine) -> async_sessionmaker[AsyncSession]:
        """构建异步会话工厂。

        Args:
            options: 异步引擎。

        Returns:
            async_sessionmaker[AsyncSession]: 会话工厂。
        """
        return async_sessionmaker(options, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """请求级会话依赖（每请求独立，退出释放）。

    Args:
        request: 当前请求（取 `app.state.engine_registry`）。

    Yields:
        AsyncSession: 请求级异步会话。
    """
    registry: EngineRegistry = request.app.state.engine_registry
    engine = await registry.get()
    factory = cast("SessionFactory | None", getattr(request.app.state, "session_factory", None)) or SessionFactory()
    session_factory = factory.create(engine)
    async with session_factory() as session:
        yield session


async def get_uow(session: Annotated[AsyncSession, Depends(get_db)]) -> DbUnitOfWork:
    """请求级工作单元依赖（基于请求级会话）。

    Args:
        session: 请求级异步会话。

    Returns:
        DbUnitOfWork: 数据库工作单元。
    """
    return DbUnitOfWork(session)
