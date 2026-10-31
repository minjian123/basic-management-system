"""jobs 用例公共夹具：临时 SQLite（作业两表 + 发件箱 + 任务两表）+ 会话 + 引擎注册表 + fakeredis。"""

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
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.models.base import Base
from bms_core.models.job import SysJob, SysJobError
from bms_core.models.outbox import SysEventConsumed, SysEventDeadLetter, SysOutbox
from bms_core.models.platform.task import SysTask, SysTaskLog

JOB_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    [
        cast("Table", SysJob.__table__),
        cast("Table", SysJobError.__table__),
        cast("Table", SysTask.__table__),
        cast("Table", SysTaskLog.__table__),
        cast("Table", SysOutbox.__table__),
        cast("Table", SysEventConsumed.__table__),
        cast("Table", SysEventDeadLetter.__table__),
    ]
)


async def create_job_tables(url: str) -> None:
    """在目标库建作业相关表。

    Args:
        url: 数据库连接串。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(JOB_TABLES)))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def job_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """临时库（含作业相关表）并把平台库指向它。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Returns:
        str: 数据库连接串。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'job.db'}"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", url)
    get_settings.cache_clear()
    await create_job_tables(url)
    return url


@pytest_asyncio.fixture
async def session(job_url: str) -> AsyncGenerator[AsyncSession]:
    """作业库会话。

    Args:
        job_url: 数据库连接串。

    Yields:
        AsyncSession: 会话。
    """
    engine = create_async_engine(job_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


@pytest_asyncio.fixture
async def registry(job_url: str) -> AsyncGenerator[EngineRegistry]:
    """引擎注册表（worker 按库键开会话）。

    Args:
        job_url: 数据库连接串。

    Yields:
        EngineRegistry: 引擎注册表（退出统一释放）。
    """
    _ = job_url
    registry = EngineRegistry(EngineFactory(get_settings()))
    yield registry
    await registry.aclose()


@pytest.fixture
def fake_redis() -> Redis:
    """假 Redis（信号 / 队列用例）。

    Returns:
        Redis: fakeredis 实例。
    """
    return cast("Redis", FakeRedis(decode_responses=False))


def platform_session_url(job_url: str) -> str:
    """取会话工厂使用的库键连接串（测试断言辅助）。

    Args:
        job_url: 数据库连接串。

    Returns:
        str: 连接串。
    """
    return job_url


__all__ = ["JOB_TABLES", "create_job_tables", "platform_session_url"]
