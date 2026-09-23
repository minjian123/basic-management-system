"""发件箱 CLI 用例（Kiwi 2172）：手动投递 / 事件账本重放 / 失败退码。

测试库：临时 SQLite（建发件箱三表）；发布实现为 null（配置未启用真实 MQ）。
"""

import asyncio
from collections.abc import Coroutine
from pathlib import Path
from typing import Any, cast

import pytest
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.config import get_settings
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.events.base import EventEnvelope
from bms_core.models.base import Base
from bms_core.models.outbox import SysEventConsumed, SysEventDeadLetter, SysOutbox
from bms_core.outbox.base import OUTBOX_STATUS_DELIVERED, OUTBOX_STATUS_PENDING
from bms_core.outbox.store import SqlOutboxStore
from ops.outbox import main

_TABLES: list[Table] = [
    cast("Table", SysOutbox.__table__),
    cast("Table", SysEventConsumed.__table__),
    cast("Table", SysEventDeadLetter.__table__),
]


def _run[T](coro: Coroutine[Any, Any, T]) -> T:
    """在同步测试中执行协程。"""
    return asyncio.run(coro)


async def _create_tables(url: str) -> None:
    """建发件箱三表。"""
    engine = create_async_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=_TABLES))
    await engine.dispose()


async def _seed(url: str, *, delivered: bool) -> str:
    """建表并写一条发件箱事件（可选标记已投递）。

    Returns:
        str: 事件 ID。
    """
    await _create_tables(url)
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlOutboxStore()
    async with maker() as session:
        async with session.begin():
            event_id = await store.enqueue(session, EventEnvelope(event_type="order.created"))
        if delivered:
            async with session.begin():
                await store.mark_delivered(session, event_id)
    await engine.dispose()
    return event_id


async def _status(url: str) -> list[str]:
    """读取发件箱全部状态。"""
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        rows = (await session.execute(select(SysOutbox.status))).scalars().all()
    await engine.dispose()
    return list(rows)


def _point_to(url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """把平台库指向临时库并重置配置缓存。"""
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", url)
    get_settings.cache_clear()


@pytest.mark.kiwi_id(2172)
def test_cli_dispatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """手动投递：待投递事件被转发（null 发布）并标记已投递。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
    _point_to(url, monkeypatch)
    _run(_seed(url, delivered=False))

    assert main(["dispatch", "--db-key", PLATFORM_DB_KEY]) == 0
    assert _run(_status(url)) == [OUTBOX_STATUS_DELIVERED]


@pytest.mark.kiwi_id(2172)
def test_cli_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """重放：已投递事件按类型重置为待投递并打印条数。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}"
    _point_to(url, monkeypatch)
    _run(_seed(url, delivered=True))
    assert _run(_status(url)) == [OUTBOX_STATUS_DELIVERED]

    assert main(["replay", "--event-type", "order.created", "--db-key", PLATFORM_DB_KEY]) == 0
    assert _run(_status(url)) == [OUTBOX_STATUS_PENDING]


@pytest.mark.kiwi_id(2172)
def test_cli_failure_exit_code(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """库不可用：命令返回非 0 退出码（不抛未捕获异常）。"""
    url = f"sqlite+aiosqlite:///{tmp_path / 'missing' / 'deep' / 'cli.db'}"
    _point_to(url, monkeypatch)
    assert main(["replay"]) == 1
