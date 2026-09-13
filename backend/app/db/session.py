"""异步会话工厂与请求级依赖：`async_sessionmaker` + `get_db`。

禁止异步会话跨请求共享；每请求独立会话，退出即释放。
"""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.registry import EngineRegistry
from app.db.unit_of_work import DbUnitOfWork


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """构建异步会话工厂。

    Args:
        engine: 异步引擎。

    Returns:
        async_sessionmaker[AsyncSession]: 会话工厂。
    """
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    """请求级会话依赖（每请求独立，退出释放）。

    Args:
        request: 当前请求（取 `app.state.engine_registry`）。

    Yields:
        AsyncSession: 请求级异步会话。
    """
    registry: EngineRegistry = request.app.state.engine_registry
    engine = await registry.get()
    session_factory = build_session_factory(engine)
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
