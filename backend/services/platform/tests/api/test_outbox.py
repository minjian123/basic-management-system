"""死信看板接口测试（Kiwi 2173）：列表分页 / 筛选 / 详情 / 重投 / 忽略 / 404 / 状态冲突。"""

from typing import cast

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bms_core.core.config import get_settings
from bms_core.events.base import EventEnvelope
from bms_core.models.base import Base
from bms_core.models.outbox import SysEventConsumed, SysEventDeadLetter, SysOutbox
from bms_core.outbox.base import DEAD_LETTER_STATUS_PENDING, OUTBOX_STATUS_PENDING
from bms_core.outbox.store import SqlOutboxStore

_TABLES: list[Table] = [
    cast("Table", SysOutbox.__table__),
    cast("Table", SysEventConsumed.__table__),
    cast("Table", SysEventDeadLetter.__table__),
]


@pytest_asyncio.fixture(autouse=True)
async def outbox_schema(
    platform_db_url: str, tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """为平台库与临时租户库补建发件箱三表，并把租户库指向临时文件。

    死信看板接口按请求租户库读取（演示租户回落），故测试事件落租户库。

    Args:
        platform_db_url: 会话级平台库连接串。
        tmp_path_factory: 临时目录工厂。
        monkeypatch: 环境变量覆盖。
    """
    tenant_url = f"sqlite+aiosqlite:///{tmp_path_factory.mktemp('tenant') / 'tenant.db'}"
    monkeypatch.setenv("BMS_DATABASE__TENANTS__URL", tenant_url)
    get_settings.cache_clear()
    for url in (platform_db_url, tenant_url):
        engine = create_async_engine(url)
        async with engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(conn, tables=_TABLES))
        await engine.dispose()


async def _seed_dead_letter(*, event_type: str = "order.created") -> str:
    """写一条投递失败转死信的事件（落请求租户库）。

    Returns:
        str: 事件 ID。
    """
    url = get_settings().database.tenants.resolved_url()
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    store = SqlOutboxStore()
    async with maker() as session:
        async with session.begin():
            event_id = await store.enqueue(session, EventEnvelope(event_type=event_type, tenant_id="t1"))
        async with session.begin():
            await store.mark_failed(session, event_id, "publish boom", max_retries=1, backoff=1)
    await engine.dispose()
    return event_id


@pytest.mark.kiwi_id(2173)
async def test_dead_letter_board_flow(client: AsyncClient) -> None:
    """列表 / 筛选 / 详情 / 重投（重置发件箱待投递）/ 忽略 / 404 / 状态冲突。"""
    event_id = await _seed_dead_letter()

    listed = await client.get("/api/v1/outbox/dead-letters", params={"status": DEAD_LETTER_STATUS_PENDING})
    assert listed.status_code == 200
    data = listed.json()["data"]
    assert data["total"] >= 1
    item = next(row for row in data["list"] if row["event_id"] == event_id)
    assert item["source"] == "outbox"
    assert item["status"] == DEAD_LETTER_STATUS_PENDING
    dead_id = item["id"]

    filtered = await client.get("/api/v1/outbox/dead-letters", params={"source": "consumer"})
    assert filtered.json()["data"]["total"] == 0

    detail = await client.get(f"/api/v1/outbox/dead-letters/{dead_id}")
    assert detail.json()["data"]["event_id"] == event_id

    missing = await client.get("/api/v1/outbox/dead-letters/999999999")
    assert missing.status_code == 404
    assert missing.json()["code"] == 10002

    replayed = await client.post(f"/api/v1/outbox/dead-letters/{dead_id}/replay")
    assert replayed.json()["code"] == 0
    assert replayed.json()["data"]["status"] == "replayed"

    # 重投后：对应发件箱记录已重置为待投递
    backend_url = get_settings().database.tenants.resolved_url()
    engine = create_async_engine(backend_url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        row = (await session.execute(select(SysOutbox))).scalars().first()
        assert row is not None and row.status == OUTBOX_STATUS_PENDING
    await engine.dispose()

    conflict = await client.post(f"/api/v1/outbox/dead-letters/{dead_id}/replay")
    assert conflict.json()["code"] == 10003

    other = await _seed_dead_letter(event_type="user.updated")
    assert other != event_id
    ignored = await client.post(f"/api/v1/outbox/dead-letters/{dead_id}/ignore")
    assert ignored.json()["code"] == 10003  # 已 replayed，不可忽略

    pending = await client.get("/api/v1/outbox/dead-letters", params={"status": DEAD_LETTER_STATUS_PENDING})
    newest = pending.json()["data"]["list"][0]
    ok = await client.post(f"/api/v1/outbox/dead-letters/{newest['id']}/ignore")
    assert ok.json()["data"]["status"] == "ignored"

    missing_action = await client.post("/api/v1/outbox/dead-letters/999999999/ignore")
    assert missing_action.status_code == 404
