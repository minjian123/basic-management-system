"""outbox 用例公共夹具：临时 SQLite 库（建发件箱三表）+ 会话 + 引擎注册表。"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bms_core.core.config import get_settings
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.models.base import Base
from bms_core.models.outbox import SysEventConsumed, SysEventDeadLetter, SysOutbox

OUTBOX_TABLES: list[Table] = [
    cast("Table", SysOutbox.__table__),
    cast("Table", SysEventConsumed.__table__),
    cast("Table", SysEventDeadLetter.__table__),
]


async def create_outbox_tables(url: str) -> None:
    """在目标库建发件箱三表。

    Args:
        url: 数据库连接串。
    """
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=OUTBOX_TABLES))
    finally:
        await engine.dispose()


@pytest_asyncio.fixture
async def outbox_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """临时平台库（含发件箱三表）并指向配置。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Returns:
        str: 数据库连接串。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'outbox.db'}"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", url)
    get_settings.cache_clear()
    await create_outbox_tables(url)
    return url


@pytest_asyncio.fixture
async def session(outbox_url: str) -> AsyncGenerator[AsyncSession]:
    """发件箱库会话。

    Args:
        outbox_url: 数据库连接串。

    Yields:
        AsyncSession: 会话。
    """
    engine = create_async_engine(outbox_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db_session:
        yield db_session
    await engine.dispose()


@pytest_asyncio.fixture
async def registry(outbox_url: str) -> AsyncGenerator[EngineRegistry]:
    """引擎注册表（投递器按库键开会话）。

    Args:
        outbox_url: 数据库连接串。

    Yields:
        EngineRegistry: 引擎注册表（退出统一释放）。
    """
    settings = get_settings()
    registry = EngineRegistry(EngineFactory(settings))
    yield registry
    await registry.aclose()


__all__ = ["OUTBOX_TABLES", "PLATFORM_DB_KEY", "create_outbox_tables"]
