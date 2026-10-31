"""events 用例公共夹具：临时 SQLite 平台库（建死信表）+ 引擎注册表。

只建 `sys_event_dead_letter`——本目录用例覆盖的是消费侧死信落库，不涉及发件箱 / 幂等账本表
（那两类的夹具在 `tests/outbox/conftest.py`，互不干扰）。
"""

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import create_async_engine

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.db.engine import EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.models.base import Base
from bms_core.models.outbox import SysEventDeadLetter

DEAD_LETTER_TABLES: ConcurrentStableList[Table] = ConcurrentStableList([cast("Table", SysEventDeadLetter.__table__)])


@pytest_asyncio.fixture
async def dead_letter_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[EngineRegistry]:
    """临时平台库（含死信表）+ 引擎注册表。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        EngineRegistry: 引擎注册表（退出统一释放）。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'events.db'}"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", url)
    get_settings.cache_clear()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(DEAD_LETTER_TABLES)))
    finally:
        await engine.dispose()
    registry = EngineRegistry(EngineFactory(get_settings()))
    try:
        yield registry
    finally:
        await registry.aclose()
