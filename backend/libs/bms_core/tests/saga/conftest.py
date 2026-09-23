"""saga 用例公共夹具：临时 SQLite 库（建发件箱与消费幂等表）+ 会话。"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.models.base import Base
from bms_core.models.outbox import SysEventConsumed, SysOutbox

SAGA_TABLES: list[Table] = [
    cast("Table", SysOutbox.__table__),
    cast("Table", SysEventConsumed.__table__),
]


@pytest_asyncio.fixture
async def saga_session(tmp_path: Path) -> AsyncGenerator[AsyncSession]:
    """Saga 用例会话（临时 SQLite，建发件箱与消费幂等表）。

    Args:
        tmp_path: 临时目录。

    Yields:
        AsyncSession: 会话。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'saga.db'}"
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=SAGA_TABLES))
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            yield session
    finally:
        await engine.dispose()
