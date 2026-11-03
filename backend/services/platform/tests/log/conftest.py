"""审计日志域用例夹具：进程内 SQLite 库（分片表 / 台账）。"""

from collections.abc import AsyncIterator
from typing import cast

import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.models.base import Base
from bms_core.models.platform.log import SysAuditShard


@pytest_asyncio.fixture
async def log_session() -> AsyncIterator[AsyncSession]:
    """进程内 SQLite 会话（仅建分片台账表；分片表由仓储运行期创建）。

    Yields:
        AsyncSession: 平台库会话（静态连接池，保证内存库跨会话可见）。
    """
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=[cast("Table", SysAuditShard.__table__)])
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()
