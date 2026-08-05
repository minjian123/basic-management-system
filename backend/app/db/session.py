"""AsyncSession 工厂与请求级会话依赖。

- 每次请求经 get_db() 依赖创建独立会话，请求结束自动关闭；异步会话禁止跨请求共享
- 会话绑定引擎由数据源路由（db/router.py）按租户上下文决定
- 事务边界：依赖粒度事务，请求内显式 commit/rollback，大事务显式声明边界
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from .router import resolve_engine

_session_factory = async_sessionmaker(expire_on_commit=False)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """获取全局会话工厂（bind 由每次创建会话时指定，支持多数据源）。"""
    return _session_factory


async def get_db() -> AsyncIterator[AsyncSession]:
    """请求级会话依赖：按当前租户上下文路由到对应库，请求结束自动关闭。"""
    engine = await resolve_engine()
    async with AsyncSession(engine, expire_on_commit=False) as session:
        yield session
