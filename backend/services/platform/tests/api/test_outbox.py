"""死信看板接口测试（Kiwi 2173）：列表分页 / 筛选 / 详情 / 重投 / 忽略 / 404 / 状态冲突。

单库叠加口径（04-6-2）：库用共享平台库 / 共享租户库（不再建临时库）；事件标识带命名空间前缀，
列表断言一律按本用例事件精确定位（禁止「清单为空」「全表第一行」类断言）。
"""

from datetime import datetime
from typing import cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import get_settings
from bms_core.events.base import EventEnvelope
from bms_core.models.base import Base
from bms_core.models.outbox import SysEventConsumed, SysEventDeadLetter, SysOutbox
from bms_core.outbox.base import DEAD_LETTER_STATUS_PENDING, OUTBOX_STATUS_PENDING
from bms_core.outbox.store import SqlOutboxStore
from bms_core.testing.namespace import Namespace

_TABLES: ConcurrentStableList[Table] = ConcurrentStableList(
    [
        cast("Table", SysOutbox.__table__),
        cast("Table", SysEventConsumed.__table__),
        cast("Table", SysEventDeadLetter.__table__),
    ]
)


def _missing_id(ns: Namespace) -> int:
    """本用例专属的「不存在」主键（避免与库中既有行相撞）。

    Args:
        ns: 用例命名空间。

    Returns:
        int: 不存在的主键。
    """
    return int(ns.prefix[2:], 16) * 1000 + 999


@pytest_asyncio.fixture(autouse=True)
async def outbox_schema(
    platform_db: None,
    shared_platform_engine: AsyncEngine,
    shared_platform_db_url: str,
    shared_tenant_engine: AsyncEngine,
    shared_tenant_db_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """为共享平台库与共享租户库补建发件箱三表，并把两库连接串指向共享库。

    死信看板接口按请求租户库读取（演示租户回落），故测试事件落租户库。

    Args:
        platform_db: 套件平台库夹具（仅用于排序：先完成旧夹具设置再覆盖）。
        shared_platform_engine: 共享平台库引擎。
        shared_platform_db_url: 共享平台库连接串。
        shared_tenant_engine: 共享租户库引擎。
        shared_tenant_db_url: 共享租户库连接串。
        monkeypatch: 环境变量覆盖。
    """
    for engine in (shared_platform_engine, shared_tenant_engine):
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=list(_TABLES)))
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", shared_platform_db_url)
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", shared_tenant_db_url)
    get_settings.cache_clear()


async def _seed_dead_letter(engine: AsyncEngine, *, event_type: str = "order.created") -> str:
    """写一条投递失败转死信的事件（落共享租户库）。

    Args:
        engine: 共享租户库引擎。
        event_type: 事件类型。

    Returns:
        str: 事件 ID。
    """
    maker = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlOutboxStore()
    async with maker() as session:
        async with session.begin():
            event_id = await store.enqueue(session, EventEnvelope(event_type=event_type, tenant_id="1001"))
        async with session.begin():
            await store.mark_failed(session, event_id, "publish boom", max_retries=1, backoff=1)
    return event_id


@pytest.mark.kiwi_id(2173)
async def test_dead_letter_board_flow(client: AsyncClient, shared_tenant_engine: AsyncEngine, ns: Namespace) -> None:
    """列表 / 筛选 / 详情 / 重投（重置发件箱待投递）/ 忽略 / 404 / 状态冲突。"""
    event_id = await _seed_dead_letter(shared_tenant_engine)

    listed = await client.get("/api/v1/outbox/dead-letters", params={"status": DEAD_LETTER_STATUS_PENDING})
    assert listed.status_code == 200
    data = listed.json()["data"]
    assert data["total"] >= 1
    item = next(row for row in data["list"] if row["event_id"] == event_id)
    assert item["source"] == "outbox"
    assert item["status"] == DEAD_LETTER_STATUS_PENDING
    dead_id = item["id"]

    filtered = await client.get("/api/v1/outbox/dead-letters", params={"source": "consumer"})
    assert all(row["event_id"] != event_id for row in filtered.json()["data"]["list"])

    detail = await client.get(f"/api/v1/outbox/dead-letters/{dead_id}")
    assert detail.json()["data"]["event_id"] == event_id

    missing = await client.get(f"/api/v1/outbox/dead-letters/{_missing_id(ns)}")
    assert missing.status_code == 404
    assert missing.json()["code"] == 10002

    replayed = await client.post(f"/api/v1/outbox/dead-letters/{dead_id}/replay")
    assert replayed.json()["code"] == 0
    assert replayed.json()["data"]["status"] == "replayed"

    # 重投后：对应发件箱记录已重置为待投递
    maker = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with maker() as session:
        row = (await session.execute(select(SysOutbox).where(SysOutbox.event_id == event_id))).scalars().first()
    assert row is not None and row.status == OUTBOX_STATUS_PENDING

    conflict = await client.post(f"/api/v1/outbox/dead-letters/{dead_id}/replay")
    assert conflict.json()["code"] == 10003

    other = await _seed_dead_letter(shared_tenant_engine, event_type="sys.user.updated")
    assert other != event_id
    ignored = await client.post(f"/api/v1/outbox/dead-letters/{dead_id}/ignore")
    assert ignored.json()["code"] == 10003  # 已 replayed，不可忽略

    pending = await client.get("/api/v1/outbox/dead-letters", params={"status": DEAD_LETTER_STATUS_PENDING})
    pending_ids = {row["event_id"]: row["id"] for row in pending.json()["data"]["list"]}
    assert other in pending_ids
    ok = await client.post(f"/api/v1/outbox/dead-letters/{pending_ids[other]}/ignore")
    assert ok.json()["data"]["status"] == "ignored"

    missing_action = await client.post(f"/api/v1/outbox/dead-letters/{_missing_id(ns)}/ignore")
    assert missing_action.status_code == 404


async def _seed_consumer_dead_letter(engine: AsyncEngine, ns: Namespace) -> tuple[int, str]:
    """直插一条消费来源死信（`source=consumer`，不经投递器）。

    Args:
        engine: 共享租户库引擎。
        ns: 用例命名空间。

    Returns:
        tuple[int, str]: （死信记录主键, 事件 ID）。
    """
    event_id = ns.code("evt-consumer")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session, session.begin():
        row = SysEventDeadLetter(
            source="consumer",
            event_id=event_id,
            event_type="order.created",
            consumer="billing",
            payload=ConcurrentStableDict(),
            error_msg="consume boom",
            retry_count=3,
            status=DEAD_LETTER_STATUS_PENDING,
            occurred_at=datetime(2026, 10, 1, 0, 0, 0),
        )
        session.add(row)
        await session.flush()
        dead_id = int(row.id)
    return dead_id, event_id


@pytest.mark.kiwi_id(2173)
async def test_replay_missing_and_consumer_source(
    client: AsyncClient, shared_tenant_engine: AsyncEngine, ns: Namespace
) -> None:
    """重投：死信不存在 → 404 / 10002；`source=consumer` 只改处置状态、不动发件箱。"""
    missing = await client.post(f"/api/v1/outbox/dead-letters/{_missing_id(ns)}/replay")
    assert missing.status_code == 404
    assert missing.json()["code"] == 10002

    dead_id, event_id = await _seed_consumer_dead_letter(shared_tenant_engine, ns)
    replayed = await client.post(f"/api/v1/outbox/dead-letters/{dead_id}/replay")
    assert replayed.status_code == 200
    assert replayed.json()["data"]["status"] == "replayed"
    assert replayed.json()["data"]["source"] == "consumer"

    # 消费来源无对应发件箱记录：账本保持原状（本用例事件没有新增发件箱行）
    maker = async_sessionmaker(shared_tenant_engine, expire_on_commit=False)
    async with maker() as session:
        rows = (await session.execute(select(SysOutbox).where(SysOutbox.event_id == event_id))).scalars().all()
    assert rows == []
