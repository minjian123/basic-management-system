"""tasks 用例公共夹具：临时 SQLite（建 `sys_task` / `sys_task_log`）+ 会话 + 引擎注册表 + fakeredis。"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.models.base import Base
from bms_core.models.outbox import SysEventConsumed, SysEventDeadLetter, SysOutbox
from bms_core.models.platform.task import SysTask, SysTaskLog

TASK_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    [
        cast("Table", SysTask.__table__),
        cast("Table", SysTaskLog.__table__),
        cast("Table", SysOutbox.__table__),
        cast("Table", SysEventConsumed.__table__),
        cast("Table", SysEventDeadLetter.__table__),
    ]
)


async def create_task_tables(url: str) -> None:
    """在目标库建任务两表。

    Args:
        url: 数据库连接串。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(TASK_TABLES)))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def task_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """临时库（含任务两表）并把平台库指向它。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Returns:
        str: 数据库连接串。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'task.db'}"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", url)
    get_settings.cache_clear()
    await create_task_tables(url)
    return url


@pytest_asyncio.fixture
async def session(task_url: str) -> AsyncGenerator[AsyncSession]:
    """任务库会话。

    Args:
        task_url: 数据库连接串。

    Yields:
        AsyncSession: 会话。
    """
    engine = create_async_engine(task_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


@pytest_asyncio.fixture
async def registry(task_url: str) -> AsyncGenerator[EngineRegistry]:
    """引擎注册表（调度器按库键开会话）。

    Args:
        task_url: 数据库连接串。

    Yields:
        EngineRegistry: 引擎注册表（退出统一释放）。
    """
    _ = task_url
    registry = EngineRegistry(EngineFactory(get_settings()))
    yield registry
    await registry.aclose()


@pytest.fixture
def fake_redis() -> Redis:
    """假 Redis（队列 / 信号用例）。

    Returns:
        Redis: fakeredis 实例。
    """
    return cast("Redis", FakeRedis(decode_responses=False))


__all__ = ["PLATFORM_DB_KEY", "TASK_TABLES", "create_task_tables"]
