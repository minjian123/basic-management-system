"""事件总线端到端集成用例：真 RocketMQ（gRPC proxy）发布 → 消费 → 幂等 → 死信。

前置（未就绪自动跳过，CI 不受影响）：

```bash
export BMS_ROCKETMQ__ENDPOINTS=192.168.0.107:8081   # broker 的 proxy 端口（不是 9876 / 10911）
uv run pytest libs/bms_core/tests/integration/test_event_bus_rocketmq.py -v
```

覆盖《详细设计 · 事件总线》§4.10 的端到端验证项：

1. 发布的事件能被消费组拉到并成功处理（topic 派生 / 编解码 / ack 全链路）；
2. 同一 `event_id` 重复投递只生效一次（幂等短窗口）；
3. 处理器持续失败时落死信（`sys_event_dead_letter.source = consumer`）。

组名带随机后缀：不共用真实业务组的 offset，跑完即弃。
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis
from sqlalchemy import Table, select
from sqlalchemy.ext.asyncio import create_async_engine

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.db.engine import PLATFORM_DB_KEY, EngineFactory
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import session_scope
from bms_core.events.base import ConsumedTally, EventConsumer, EventEnvelope
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.events.dead_letter import EventDeadLetterEntry, EventDeadLetterRecorder
from bms_core.events.dedup import EventConsumeDedup
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.events.rocketmq_consumer import RocketMqEventConsumerGroup
from bms_core.events.rocketmq_publisher import RocketMqEventPublisher
from bms_core.models.base import Base
from bms_core.models.outbox import SysEventDeadLetter

pytestmark = [pytest.mark.integration, pytest.mark.kiwi_id(2370)]

_ENDPOINTS = os.environ.get("BMS_ROCKETMQ__ENDPOINTS", "")
"""proxy 接入点；未配置则全部用例跳过（CI 无 broker）。"""

_EVENT_TYPE = "sys.user.created"
"""已登记契约的事件类型（topic 为 `bms.sys.user`）。"""

_WAIT_SECONDS = 20.0
"""等待消息可见的上限（broker 路由发现 + 长轮询）。"""


class _Collector(EventConsumer):
    """收集事件的处理器（可编排恒失败）。"""

    def __init__(self, *, fail: bool = False) -> None:
        """初始化。

        Args:
            fail: 是否恒失败（验证死信）。
        """
        self.fail = fail
        self.seen: ConcurrentStableList[str] = ConcurrentStableList()

    @property
    def event_type(self) -> str:
        """事件类型。"""
        return _EVENT_TYPE

    async def consume(self, event: EventEnvelope) -> None:
        """消费事件。

        Args:
            event: 事件信封。

        Raises:
            RuntimeError: 编排的失败。
        """
        if self.fail:
            raise RuntimeError("integration failure")
        self.seen.add(event.event_id or "")


def _settings() -> Settings:
    """构造指向真 broker 的配置（消费启用、重试 0 次、退避 0）。

    Returns:
        Settings: 配置。
    """
    settings = Settings()
    settings.rocketmq.endpoints = _ENDPOINTS
    settings.event_consumer.enabled = True
    settings.event_consumer.max_retries = 0
    settings.event_consumer.retry_backoff_seconds = 0.0
    settings.event_consumer.poll_interval_seconds = 1.0
    settings.event_consumer.visibility_timeout_seconds = 10
    return settings


@pytest.fixture(autouse=True)
def _skip_without_broker() -> None:
    """未配置端点即跳过（CI 与本地无 broker 场景不报红）；顺带登记平台事件契约。"""
    if not _ENDPOINTS:
        pytest.skip("未配置 BMS_ROCKETMQ__ENDPOINTS（需真 broker）")
    register_platform_event_contracts()


@pytest.fixture
async def registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[EngineRegistry]:
    """临时平台库（只建死信表）+ 引擎注册表（死信真实落表断言）。

    Args:
        tmp_path: 临时目录。
        monkeypatch: 环境变量覆盖。

    Yields:
        EngineRegistry: 引擎注册表。
    """
    url = f"sqlite+aiosqlite:///{tmp_path / 'event_bus.db'}"
    monkeypatch.setenv("BMS_DATABASE__PLATFORM__URL", url)
    get_settings.cache_clear()
    engine = create_async_engine(url)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                lambda conn: Base.metadata.create_all(conn, tables=[cast("Table", SysEventDeadLetter.__table__)])
            )
    finally:
        await engine.dispose()
    created = EngineRegistry(EngineFactory(get_settings()))
    try:
        yield created
    finally:
        await created.aclose()


def _event(event_id: str, *, tenant: str = "100000000000000001") -> EventEnvelope:
    """构造事件。

    Args:
        event_id: 事件 ID。
        tenant: 租户主键（十进制）。

    Returns:
        EventEnvelope: 信封。
    """
    return EventEnvelope(
        event_type=_EVENT_TYPE,
        payload=ConcurrentStableDict({"user_id": "u-integration", "event_id": event_id}),
        tenant_id=tenant,
        aggregate_key=tenant,
        event_id=event_id,
        occurred_at=datetime.now(UTC).replace(tzinfo=None),
    )


def _group(registry: EngineRegistry, handler: EventConsumer, *, group: str) -> RocketMqEventConsumerGroup:
    """构造指向真 broker 的消费组。

    Args:
        registry: 引擎注册表（死信落库）。
        handler: 处理器。
        group: 组名（带随机后缀）。

    Returns:
        RocketMqEventConsumerGroup: 运行时。
    """
    consumer = RocketMqEventConsumerGroup(
        settings=_settings(),
        engine_registry=registry,
        dedup=EventConsumeDedup(client=cast("Redis", FakeRedis())),
    )
    consumer.load(
        ConcurrentStableList(
            [
                EventConsumerRecord(
                    consumer=group,
                    event_type=handler.event_type,
                    handler_factory=lambda: handler,
                    ordered=True,
                )
            ]
        )
    )
    return consumer


async def _poll_until(
    group: RocketMqEventConsumerGroup,
    *,
    expected: int,
    timeout: float = _WAIT_SECONDS,
) -> ConsumedTally:
    """反复单轮拉取直到累计达到期望条数或超时。

    Args:
        group: 消费组。
        expected: 期望累计（成功 + 跳过 + 死信）。
        timeout: 超时（秒）。

    Returns:
        ConsumedTally: 累计汇总。
    """
    total = ConsumedTally()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        total = total.merge(await group.consume_once(max_messages=16))
        if total.succeeded + total.skipped + total.dead >= expected:
            return total
        await asyncio.sleep(0.5)
    return total


async def _dead_letters(registry: EngineRegistry) -> ConcurrentStableList[SysEventDeadLetter]:
    """读死信行。

    Args:
        registry: 引擎注册表。

    Returns:
        ConcurrentStableList[SysEventDeadLetter]: 死信行。
    """
    async with session_scope(registry, db_key=PLATFORM_DB_KEY) as session:
        return ConcurrentStableList((await session.execute(select(SysEventDeadLetter))).scalars())


async def test_publish_then_consume_round_trip(registry: EngineRegistry) -> None:
    """发布 → 消费全链路：消息按 topic 落到 broker，消费组拉到并成功处理。"""
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    publisher = RocketMqEventPublisher.from_settings(_settings())
    handler = _Collector()
    group = _group(registry, handler, group=f"bms-it-rt-{uuid.uuid4().hex[:8]}")
    try:
        await publisher.publish(_event(event_id))
        tally = await _poll_until(group, expected=1)
    finally:
        await publisher.aclose()
        await group.aclose()
    # topic 上可能残留历史消息（同一 topic 承载同域同对象的所有事件），断言只针对本次事件 ID
    assert event_id in handler.seen, f"未消费到事件 {event_id}：{tally}"


async def test_same_event_id_consumed_once(registry: EngineRegistry) -> None:
    """同一 `event_id` 投递两次：第二次被幂等短窗口拦下，处理器只执行一次。"""
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    publisher = RocketMqEventPublisher.from_settings(_settings())
    handler = _Collector()
    group = _group(registry, handler, group=f"bms-it-idem-{uuid.uuid4().hex[:8]}")
    try:
        await publisher.publish(_event(event_id))
        await publisher.publish(_event(event_id))
        tally = await _poll_until(group, expected=2)
    finally:
        await publisher.aclose()
        await group.aclose()
    assert list(handler.seen).count(event_id) == 1, f"重复消费：{list(handler.seen)}"
    assert tally.skipped >= 1, f"未命中幂等短窗口：{tally}"


async def test_retry_exhausted_writes_dead_letter(registry: EngineRegistry) -> None:
    """处理器持续失败（重试 0 次）→ 落死信（`source = consumer`），不再无限重投。"""
    event_id = f"evt-{uuid.uuid4().hex[:12]}"
    publisher = RocketMqEventPublisher.from_settings(_settings())
    handler = _Collector(fail=True)
    group = _group(registry, handler, group=f"bms-it-dead-{uuid.uuid4().hex[:8]}")
    try:
        await publisher.publish(_event(event_id))
        tally = await _poll_until(group, expected=1)
    finally:
        await publisher.aclose()
        await group.aclose()
    assert tally.dead >= 1, f"未转死信：{tally}"
    rows = [row for row in await _dead_letters(registry) if row.event_id == event_id]
    assert len(rows) == 1
    assert rows[0].source == "consumer"
    assert "integration failure" in rows[0].error_msg


async def test_dead_letter_recorder_writes_to_platform_db(registry: EngineRegistry) -> None:
    """死信写入器对真库可用（与消费链路同源，独立验证落库）。"""
    recorder = EventDeadLetterRecorder(engine_registry=registry)
    await recorder.record(
        EventDeadLetterEntry(
            consumer="bms-it-probe",
            event_id=f"evt-{uuid.uuid4().hex[:12]}",
            event_type=_EVENT_TYPE,
            error_msg="probe",
        )
    )
    assert len(await _dead_letters(registry)) == 1
