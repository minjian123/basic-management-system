"""真 msg 事件总线集成护栏（Kiwi 2532）：发布 → 消费 → 幂等 / 死信 / 分区不重叠。

未配置 `[service_client].instances.msg` 时自动跳过（本机 CI 无 broker，不计覆盖率分母）。
真栈运行时用例自建独立主题（`bms-sys-itest*`），不污染平台既有主题；组名带随机后缀，
避免与常驻 worker 抢同一组。
"""

import os
from typing import cast
from uuid import uuid4

import httpx
import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.config import Settings, get_settings
from bms_core.db.registry import EngineRegistry
from bms_core.db.tenant import TenantContext, TenantDirectory
from bms_core.events.base import ConsumedTally, EventConsumer, EventEnvelope
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.events.dead_letter import EventDeadLetterEntry, EventDeadLetterRecorder
from bms_core.events.dedup import EventConsumeDedup
from bms_core.events.msg_consumer import MsgEventConsumerGroup
from bms_core.events.topic import namespace_for, topic_for
from bms_core.msgclient.adapter.event_publisher import MsgEventPublisher
from bms_core.msgclient.messaging.config import MessagingConfig, TransportChannel
from bms_core.msgclient.messaging.consumer import MsgConsumer
from bms_core.msgclient.messaging.stats import ClientStats
from bms_core.msgclient.messaging.transport_factory import build_transport

pytestmark = [
    pytest.mark.kiwi_id(2532),
    pytest.mark.skipif(
        not get_settings().service_client.instances.get("msg"),
        reason="未配置真 msg 实例（[service_client].instances.msg）",
    ),
]

_TOPIC_EXISTS = 350008
"""msg 管理端点「主题已存在」业务码（幂等建主题时放行）。"""
_ADMIN_TIMEOUT = 10.0


def _settings() -> Settings:
    """取集成用配置（强制打开消费、短退避）。"""
    settings = get_settings().model_copy(deep=True)
    settings.event_consumer.enabled = True
    settings.event_consumer.host = "worker"
    settings.event_consumer.max_retries = 0
    settings.event_consumer.retry_backoff_seconds = 0.0
    return settings


def _endpoint(settings: Settings) -> str:
    """取 msg 基址（实例池第一个）。"""
    return ConcurrentStableList(settings.service_client.instances["msg"])[0].rstrip("/")


def _tenant() -> str:
    """取集成租户（缺省平台租户；业务租户经环境变量指定）。"""
    return os.environ.get("BMS_MSG_E2E_TENANT") or "platform"


def _event_type(suffix: str) -> str:
    """构造本用例专有事件类型（独立主题，避免与常驻消费组互抢）。"""
    return f"sys.itest{suffix}.roundtrip"


def _ensure_topic(base: str, tenant: str, namespace: str, topic: str, partitions: int = 1) -> None:
    """幂等创建主题（已存在放行）。"""
    response = httpx.post(
        f"{base}/api/v1/msg/admin/topics",
        json={"namespace": namespace, "name": topic, "partition_count": partitions},
        headers={"X-Tenant-ID": tenant},
        timeout=_ADMIN_TIMEOUT,
    )
    body = cast("dict[str, object]", response.json())
    assert body.get("code") in (0, _TOPIC_EXISTS), body


class _Collector(EventConsumer):
    """处理器替身：记录事件；可切「永远失败」验证死信。"""

    def __init__(self, *, fail: bool = False) -> None:
        """初始化。"""
        self.events: ConcurrentStableList[EventEnvelope] = ConcurrentStableList()
        self.fail = fail

    @property
    def event_type(self) -> str:
        """处理器标识（集成用例不按处理器分派，取固定值）。"""
        return "sys.itest.roundtrip"

    async def consume(self, event: EventEnvelope) -> None:
        """记录或抛错。"""
        if self.fail:
            raise RuntimeError("处理器失败（集成用例）")
        self.events.add(event)


class _MemoryDedup:
    """幂等替身：进程内集合（真实实现走 Redis）。"""

    def __init__(self) -> None:
        """初始化。"""
        self._seen = ConcurrentStableList[str]()

    async def seen(self, *, group: str, event_id: str) -> bool:
        """窗口内是否已处理。"""
        del group
        return event_id in self._seen

    async def remember(self, *, group: str, event_id: str) -> None:
        """标记已处理。"""
        del group
        if event_id not in self._seen:
            self._seen.add(event_id)


class _Recorder:
    """死信写入器替身：只收集，不落库。"""

    def __init__(self) -> None:
        """初始化。"""
        self.entries: ConcurrentStableList[EventDeadLetterEntry] = ConcurrentStableList()

    async def record(self, entry: EventDeadLetterEntry) -> None:
        """收集死信。"""
        self.entries.add(entry)


class _PlatformDirectory:
    """租户目录替身：只返回集成租户。"""

    def __init__(self, tenant: str) -> None:
        """初始化。"""
        self._tenant = tenant

    async def active_tenants(self) -> ConcurrentStableList[TenantContext]:
        """返回单个租户上下文。"""
        return ConcurrentStableList(
            (TenantContext(code=self._tenant, db_key=f"tenant_{self._tenant}", name=self._tenant),)
        )


def _group(
    settings: Settings,
    tenant: str,
    event_type: str,
    handler: EventConsumer,
    recorder: _Recorder,
) -> MsgEventConsumerGroup:
    """构造消费组运行时（真实 msg 客户端，替身只用于幂等 / 死信 / 租户目录）。"""
    group = MsgEventConsumerGroup(
        settings=settings,
        engine_registry=cast("EngineRegistry", object()),
        endpoints=ConcurrentStableList((_endpoint(settings),)),
        tenant_directory=cast("TenantDirectory", _PlatformDirectory(tenant)),
        platform_tenant=tenant,
        service=f"itest-{uuid4().hex[:8]}",
        dedup=cast("EventConsumeDedup", _MemoryDedup()),
        dead_letter_recorder=cast("EventDeadLetterRecorder", recorder),
    )
    group.load(
        ConcurrentStableList(
            (
                EventConsumerRecord(
                    consumer=f"itest-consumer-{uuid4().hex[:8]}",
                    event_type=event_type,
                    handler_factory=lambda: handler,
                    ordered=True,
                    description="真 msg 集成用例",
                ),
            )
        )
    )
    return group


async def _publish(base: str, tenant: str, event: EventEnvelope) -> None:
    """经真实发布器投递一条事件。"""
    publisher = MsgEventPublisher(base_url=base, namespace="", tenant=tenant)
    try:
        await publisher.publish(event)
    finally:
        await publisher.aclose()


async def test_publish_consume_and_dedup() -> None:
    """发布 → 消费 → 落处理器；同一 `event_id` 重复投递只生效一次。"""
    settings = _settings()
    base = _endpoint(settings)
    tenant = _tenant()
    event_type = _event_type(uuid4().hex[:8])
    _ensure_topic(base, tenant, namespace_for(event_type), topic_for(event_type))

    event = EventEnvelope(
        event_type=event_type,
        payload=ConcurrentStableDict({"seq": 1}),
        event_id=f"itest-{uuid4()}",
        aggregate_key="itest-key",
        event_version="1.0.0",
    )
    handler = _Collector()
    group = _group(settings, tenant, event_type, handler, _Recorder())
    try:
        await _publish(base, tenant, event)
        first = await group.consume_once(max_messages=8)
        assert first.received >= 1
        assert first.succeeded >= 1
        assert [item.event_id for item in handler.events] == [event.event_id]

        await _publish(base, tenant, event)
        second = await group.consume_once(max_messages=8)
        assert second.skipped >= 1
        assert len(handler.events) == 1
    finally:
        await group.aclose()


async def test_retry_exhausted_goes_dead_letter() -> None:
    """处理器持续失败（重试 0 次）→ 写死信并 ack（不再无限重投）。"""
    settings = _settings()
    base = _endpoint(settings)
    tenant = _tenant()
    event_type = _event_type(uuid4().hex[:8])
    _ensure_topic(base, tenant, namespace_for(event_type), topic_for(event_type))

    handler = _Collector(fail=True)
    recorder = _Recorder()
    group = _group(settings, tenant, event_type, handler, recorder)
    try:
        await _publish(
            base,
            tenant,
            EventEnvelope(event_type=event_type, payload=ConcurrentStableDict({"seq": 1}), event_id=f"itest-{uuid4()}"),
        )
        tally: ConsumedTally = await group.consume_once(max_messages=8)
        assert tally.dead >= 1
        assert [entry.event_type for entry in recorder.entries] == [event_type]
    finally:
        await group.aclose()


async def test_two_consumers_partitions_do_not_overlap() -> None:
    """同组两个成员加入后分区不重叠（多实例不重复消费的硬前提）。"""
    settings = _settings()
    base = _endpoint(settings)
    tenant = _tenant()
    event_type = _event_type(uuid4().hex[:8])
    namespace = namespace_for(event_type)
    topic = topic_for(event_type)
    _ensure_topic(base, tenant, namespace, topic, partitions=4)

    config = MessagingConfig(
        endpoints=ConcurrentStableFrozenList((base,)),
        tenant=tenant,
        channel=TransportChannel.JSON,
    )
    first = MsgConsumer(
        config,
        build_transport(config),
        ClientStats(),
        group=f"itest-group-{uuid4().hex[:8]}",
        namespace=namespace,
        topic=topic,
        consumer_id=f"itest-a-{uuid4().hex[:8]}",
    )
    second = MsgConsumer(
        config,
        build_transport(config),
        ClientStats(),
        group=first.group,
        namespace=namespace,
        topic=topic,
        consumer_id=f"itest-b-{uuid4().hex[:8]}",
    )
    try:
        await first.join()
        await second.join()
        # 后加入触发再平衡：以两侧心跳取回的最新分配为准，断言不重叠且都拿到分区。
        first_partitions = set((await first.heartbeat()).partitions)
        second_partitions = set((await second.heartbeat()).partitions)
        assert first_partitions
        assert second_partitions
        assert first_partitions.isdisjoint(second_partitions)
    finally:
        await first.close()
        await second.close()
