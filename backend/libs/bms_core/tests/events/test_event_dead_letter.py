"""消费死信写入护栏：落平台库 / 字段截断 / 空租户容错 / 批量写入。

依据《详细设计 · 事件总线》§4.6：消费失败超限转死信并写 `sys_event_dead_letter`（`source=consumer`）——
死信是人工处置入口，看板读平台库，故必须落平台库；业务事务回滚不得带走死信记录（独立事务）。
"""

from datetime import datetime

import pytest
from sqlalchemy import select

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenDict, ConcurrentStableList
from bms_core.db.engine import PLATFORM_DB_KEY
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import session_scope
from bms_core.events.dead_letter import EventDeadLetterEntry, EventDeadLetterRecorder
from bms_core.models.outbox import SysEventDeadLetter
from bms_core.outbox.base import DEAD_LETTER_SOURCE_CONSUMER, ERROR_MSG_MAX_LENGTH


def _entry(**overrides: object) -> EventDeadLetterEntry:
    """构造一条死信（缺省字段取合法值）。

    Args:
        **overrides: 覆盖字段。

    Returns:
        EventDeadLetterEntry: 死信记录。
    """
    base: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "consumer": "bms.audit.chain",
            "event_id": "evt-1",
            "event_type": "sys.user.created",
            "error_msg": "boom",
            "payload": ConcurrentStableFrozenDict({"user_id": "u-1"}),
            "aggregate_key": "1234567890",
            "tenant_id": "1234567890",
            "retry_count": 3,
        }
    )
    base.update(overrides)
    return EventDeadLetterEntry(**base)  # type: ignore[arg-type]


async def _rows(registry: EngineRegistry) -> ConcurrentStableList[SysEventDeadLetter]:
    """读全部死信行。

    Args:
        registry: 引擎注册表。

    Returns:
        ConcurrentStableList[SysEventDeadLetter]: 死信行。
    """
    async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
        return ConcurrentStableList((await session.execute(select(SysEventDeadLetter))).scalars())


async def test_record_writes_consumer_dead_letter(dead_letter_registry: EngineRegistry) -> None:
    """写入一条消费死信：来源 / 组名 / 字段逐一落库。"""
    recorder = EventDeadLetterRecorder(engine_registry=dead_letter_registry)
    await recorder.record(_entry())

    rows = await _rows(dead_letter_registry)
    assert len(rows) == 1
    row = rows[0]
    assert row.source == DEAD_LETTER_SOURCE_CONSUMER
    assert row.consumer == "bms.audit.chain"
    assert row.event_id == "evt-1"
    assert row.event_type == "sys.user.created"
    assert row.aggregate_key == "1234567890"
    assert row.tenant_id == 1234567890
    assert row.retry_count == 3
    assert dict(row.payload) == {"user_id": "u-1"}
    assert row.status == "pending"


async def test_record_truncates_error_message(dead_letter_registry: EngineRegistry) -> None:
    """失败原因按列宽截断（512），不因超长写库失败。"""
    recorder = EventDeadLetterRecorder(engine_registry=dead_letter_registry)
    await recorder.record(_entry(error_msg="x" * 2000))

    rows = await _rows(dead_letter_registry)
    assert len(rows[0].error_msg) == ERROR_MSG_MAX_LENGTH


async def test_record_tolerates_bad_tenant(dead_letter_registry: EngineRegistry) -> None:
    """租户位非十进制（脏数据）不阻断死信落库：按无租户写 NULL。"""
    recorder = EventDeadLetterRecorder(engine_registry=dead_letter_registry)
    await recorder.record(_entry(tenant_id="tenant-demo"))

    rows = await _rows(dead_letter_registry)
    assert rows[0].tenant_id is None


async def test_record_defaults_occurred_at(dead_letter_registry: EngineRegistry) -> None:
    """未给发生时间时按当前时刻落库（死信记录必须有时间，便于排序排障）。"""
    recorder = EventDeadLetterRecorder(engine_registry=dead_letter_registry)
    await recorder.record(_entry(occurred_at=None))

    rows = await _rows(dead_letter_registry)
    assert isinstance(rows[0].occurred_at, datetime)


async def test_record_keeps_given_occurred_at(dead_letter_registry: EngineRegistry) -> None:
    """给了发生时间则保真（不覆盖为当前时刻）。"""
    occurred_at = datetime(2026, 10, 31, 1, 0, 0)
    recorder = EventDeadLetterRecorder(engine_registry=dead_letter_registry)
    await recorder.record(_entry(occurred_at=occurred_at))

    rows = await _rows(dead_letter_registry)
    assert rows[0].occurred_at == occurred_at


async def test_record_many_writes_all(dead_letter_registry: EngineRegistry) -> None:
    """批量写入：同事务落多条。"""
    recorder = EventDeadLetterRecorder(engine_registry=dead_letter_registry)
    await recorder.record_many(
        ConcurrentStableList([_entry(event_id="evt-1"), _entry(event_id="evt-2"), _entry(event_id="evt-3")])
    )

    rows = await _rows(dead_letter_registry)
    assert {row.event_id for row in rows} == {"evt-1", "evt-2", "evt-3"}


async def test_record_many_empty_is_noop(dead_letter_registry: EngineRegistry) -> None:
    """空清单不写库（不产生空事务）。"""
    recorder = EventDeadLetterRecorder(engine_registry=dead_letter_registry)
    await recorder.record_many(ConcurrentStableList())
    assert await _rows(dead_letter_registry) == []


async def test_missing_payload_defaults_to_empty(dead_letter_registry: EngineRegistry) -> None:
    """负载缺省为空对象（无载荷事件也能入死信排障）。"""
    recorder = EventDeadLetterRecorder(engine_registry=dead_letter_registry)
    entry = EventDeadLetterEntry(
        consumer="bms.log.operation",
        event_id="evt-9",
        event_type="sys.user.created",
        error_msg="decode failed",
        payload=ConcurrentStableFrozenDict(),
    )
    await recorder.record(entry)

    rows = await _rows(dead_letter_registry)
    assert dict(rows[0].payload) == {}
    assert rows[0].tenant_id is None


@pytest.mark.parametrize("retry_count", [0, 3])
async def test_retry_count_persisted(dead_letter_registry: EngineRegistry, retry_count: int) -> None:
    """重试次数如实落库（死信看板据此判断恶化程度）。"""
    recorder = EventDeadLetterRecorder(engine_registry=dead_letter_registry)
    await recorder.record(_entry(retry_count=retry_count))
    rows = await _rows(dead_letter_registry)
    assert rows[0].retry_count == retry_count


def test_entry_is_frozen_value_object() -> None:
    """死信入参是不可变值对象（避免落库途中被改）。"""
    entry = _entry()
    with pytest.raises(Exception, match=r"cannot assign|read-only|frozen"):
        entry.event_id = "other"  # type: ignore[misc]
