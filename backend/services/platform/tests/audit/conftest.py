"""审计合规域用例夹具：进程内 SQLite 库（分片台账 / 发件箱 / 被审计表）。"""

from collections.abc import AsyncIterator, Iterator
from typing import cast

import pytest
import pytest_asyncio
from sqlalchemy import Table
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from bms_core.audit.field_capture import (
    install_field_audit,
    reset_capture_state,
    uninstall_field_audit,
)
from bms_core.models.base import Base
from bms_core.models.outbox import SysOutbox
from bms_core.models.platform.log import SysAuditShard
from bms_core.models.platform.role import SysRole


@pytest_asyncio.fixture
async def log_session() -> AsyncIterator[AsyncSession]:
    """进程内 SQLite 会话（台账 / 发件箱 / 角色表；分片表由仓储运行期创建）。

    Yields:
        AsyncSession: 平台库会话（静态连接池，保证内存库跨会话可见）。
    """
    engine = create_async_engine("sqlite+aiosqlite://", poolclass=StaticPool)
    tables = [
        cast("Table", SysAuditShard.__table__),
        cast("Table", SysOutbox.__table__),
        cast("Table", SysRole.__table__),
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def field_audit() -> Iterator[None]:
    """挂载字段级捕获监听（用例结束卸下并清空去重键，避免跨用例串味）。"""
    reset_capture_state()
    install_field_audit()
    yield
    uninstall_field_audit()
    reset_capture_state()
