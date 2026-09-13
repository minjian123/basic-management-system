"""异步会话工厂与请求级依赖：`async_sessionmaker` + `get_db`。

禁止异步会话跨请求共享；每请求独立会话，退出即释放。
"""

from collections.abc import AsyncIterator

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.db.engine import EngineFactory


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
        request: 当前请求（取 `app.state.engine_factory`）。

    Yields:
        AsyncSession: 请求级异步会话。
    """
    factory: EngineFactory = request.app.state.engine_factory
    session_factory = build_session_factory(factory.create("platform"))
    async with session_factory() as session:
        yield session
