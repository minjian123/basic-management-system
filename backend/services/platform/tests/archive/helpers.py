"""归档域测试辅助：双库会话、假对象存储与数据构造。"""

# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportIndexIssue=false, reportGeneralTypeIssues=false, reportUnknownLambdaType=false, reportIncompatibleMethodOverride=false, reportDeprecated=false

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from sqlalchemy import Table, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from bms_core.audit.hashchain import BaseHashChain
from bms_core.audit.sha256 import Sha256HashChain
from bms_core.audit.shards import build_shard_table, canonical_record
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.db.gate import LazyGatedSession, db_access_gate
from bms_core.models.job import SysJob
from bms_core.models.outbox import SysOutbox
from bms_core.models.ownership import SysTableOwnership
from bms_core.models.platform.archive import (
    SysArchiveChainTail,
    SysArchiveLog,
    SysArchivePolicy,
    SysArchiveRecord,
)
from bms_core.models.platform.log import SysAuditShard
from bms_core.storage.base import BaseObjectStorage, PresignedUrl, StoredObject
from bms_core.testing.transaction import _sqlite_autocommit, gate_for_engine  # pyright: ignore[reportPrivateUsage]
from tests_support.shared_access import shared_archive_url, shared_engine, shared_platform_url
from tests_support.shared_db import prepare_archive_async

__all__ = [
    "FakeStorage",
    "archive_session",
    "new_pair",
    "new_shared_pair",
    "seed_chain_rows",
    "seed_ownership",
    "utc",
]


def utc(year: int, month: int, day: int = 1) -> datetime:
    """构造 UTC naive 时间。"""
    return datetime(year, month, day, tzinfo=UTC).replace(tzinfo=None)


class FakeStorage(BaseObjectStorage):
    """内存对象存储替身（直接实例化使用；不声明 `plugin_name`，避免登记为插件候选）。"""

    def __init__(self) -> None:
        self.objects: ConcurrentStableDict[str, bytes] = ConcurrentStableDict()

    async def put(self, key: str, data: bytes, *, content_type: str | None = None) -> StoredObject:
        del content_type
        self.objects[key] = data
        return StoredObject(key=key, size=len(data))

    async def get(self, key: str) -> bytes:
        from bms_core.core.exceptions import NotFoundError

        if key not in self.objects:
            raise NotFoundError("对象不存在")
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.objects

    async def presign(self, key: str, *, method: str = "GET", expires_in: int = 3600) -> PresignedUrl:
        return PresignedUrl(url=f"https://fake/{key}", expires_in=expires_in, method=method)


_PLATFORM_TABLES = (
    SysArchivePolicy.__table__,
    SysArchiveLog.__table__,
    SysArchiveChainTail.__table__,
    SysAuditShard.__table__,
    SysTableOwnership.__table__,
    SysOutbox.__table__,
    SysJob.__table__,
)


async def new_pair(tmp_path: Path) -> tuple[AsyncSession, AsyncSession, AsyncEngine, AsyncEngine]:
    """建平台库 / 归档库各一张 SQLite 文件，返回两会话与引擎。"""
    platform_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'platform.db'}")
    archive_engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'archive.db'}")
    async with platform_engine.begin() as connection:
        for table in _PLATFORM_TABLES:
            await connection.run_sync(cast("Table", table).create, checkfirst=True)
    async with archive_engine.begin() as connection:
        await connection.run_sync(SysArchiveRecord.__table__.create, checkfirst=True)
    platform_session = async_sessionmaker(platform_engine, expire_on_commit=False)()
    archive_session = async_sessionmaker(archive_engine, expire_on_commit=False)()
    return platform_session, archive_session, platform_engine, archive_engine


def _gated(engine: AsyncEngine) -> AsyncSession:
    """把引擎包成操作级写门会话（每次写操作取写门、写完即放）。

    Args:
        engine: 目标库引擎。

    Returns:
        AsyncSession: 门代理会话。
    """
    gate_name = gate_for_engine(engine)
    factory: async_sessionmaker[AsyncSession] = async_sessionmaker(_sqlite_autocommit(engine), expire_on_commit=False)
    raw = factory()
    if gate_name is None:  # pragma: no cover - 共享库必然命中门名
        return raw
    return cast("AsyncSession", LazyGatedSession(lambda: db_access_gate(gate_name, read_only=False), raw, bind=engine))


async def new_shared_pair() -> tuple[AsyncSession, AsyncSession, AsyncEngine, AsyncEngine]:
    """共享平台库 / 共享归档库各开一个门代理会话（单库化口径）。

    归档域天然跨两库：`sys_archive_policy` / `sys_archive_log` / `sys_archive_chain_tail` 在平台库，
    `sys_archive_record` 在独立归档库 `bms_archive`（不服务化）。表由共享库准备集建好，用例不再
    各自 `create_all`；引擎由调用方 `dispose`。

    Returns:
        tuple[AsyncSession, AsyncSession, AsyncEngine, AsyncEngine]: (平台库会话, 归档库会话,
        平台库引擎, 归档库引擎)。
    """
    await prepare_archive_async(shared_archive_url())
    platform_engine = shared_engine(shared_platform_url())
    archive_engine = shared_engine(shared_archive_url())
    return _gated(platform_engine), _gated(archive_engine), platform_engine, archive_engine


async def archive_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """打开归档库会话。"""
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session


async def seed_ownership(session: AsyncSession, *, created_at: datetime) -> int:
    """造一条可归档的归属登记行，并回填旧创建时间。"""
    row = SysTableOwnership(
        table_name="sys_table_ownership",
        owner="platform",
        domain="platform_registry",
        datasource="platform",
        status="enabled",
        note="测试归档源表",
    )
    session.add(row)
    await session.commit()
    await session.execute(
        update(SysTableOwnership)
        .where(SysTableOwnership.id == row.id)
        .values(created_at=created_at, updated_at=created_at)
    )
    await session.commit()
    return int(row.id)


async def seed_chain_rows(
    session: AsyncSession,
    *,
    log_type: str,
    month: str,
    tenant_id: int | None,
    count: int,
    starting_prev: str,
    hash_chain: BaseHashChain | None = None,
) -> str:
    """造一个月分片与合法链，返回末条 record_hash。"""
    physical = f"{'sys_operation_log' if log_type == 'operation' else 'sys_login_log'}_{month}"
    table = build_shard_table(log_type, physical)
    async with session.begin():
        await session.run_sync(lambda sync: table.create(sync.connection(), checkfirst=True))
    chain = hash_chain or Sha256HashChain()
    previous = starting_prev
    for index in range(count):
        occurred = utc(int(month[:4]), int(month[4:6]), min(index + 1, 28))
        values: ConcurrentStableDict[str, object] = ConcurrentStableDict(
            {
                "id": int(f"{month}{index + 1:04d}"),
                "event_id": f"{month}-{index + 1}",
                "tenant_id": tenant_id,
                "module": "m",
                "action": "a",
                "method": "GET",
                "path": "/x",
                "status": 200,
                "occurred_at": occurred,
                "created_at": occurred,
                "prev_hash": previous,
            }
        )
        record_hash = chain.compute(previous, canonical_record(log_type, values))
        values["record_hash"] = record_hash
        async with session.begin():
            await session.execute(table.insert().values(**dict(values)))
        previous = record_hash
    return previous
