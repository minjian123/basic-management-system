"""msg 消费组运行时用例（Kiwi 2532）：拉取 → 键级串行 → 幂等 → 重试 / 死信 → 停机。

锁住四条不能退让的语义：

1. 成功 / 跳过 / 重试成功 / 死信四类结果都按约定 `ack`；死信**落库失败不 ack**；
2. 毒消息（解码失败 / 无处理器 / 版本不支持）不重试，直接死信；
3. 同键在道内严格串行；`ordered` 组道数固定 1；
4. 租户清单不可用保留旧集合；平台租户固定包含。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import cast

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.config import EventConsumerSettings, Settings
from bms_core.core.exceptions import EventConsumeError
from bms_core.db.registry import EngineRegistry
from bms_core.db.tenant import TenantContext, TenantDirectory
from bms_core.events.base import BatchConsumeOutcome, ConsumedTally, EventConsumer, EventEnvelope
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.events.dead_letter import EventDeadLetterEntry
from bms_core.events.msg_consumer import (
    MessageConsumer,
    MsgEventConsumerGroup,
    PlatformOnlyTenantDirectory,
)
from bms_core.events.platform_events import register_platform_event_contracts
from bms_core.events.topic import encode_event, event_attributes, topic_for
from bms_core.metrics.base import BaseMetrics, MetricLabels
from bms_core.msgclient.errors import ErrorCategory
from bms_core.msgclient.messaging.config import MessagingConfig
from bms_core.msgclient.messaging.consumer import (
    Assignment,
    MsgConsumer,
    PollResult,
    ReceivedMessage,
)
from bms_core.msgclient.messaging.errors import ClientAction, MsgClientError

pytestmark = pytest.mark.kiwi_id(2532)


@pytest.fixture(autouse=True)
def _contracts() -> None:
    """平台事件契约（版本兼容判定依赖它）。"""
    register_platform_event_contracts()


class _Directory:
    """租户目录替身（可编排失败与增删）。"""

    def __init__(self, codes: ConcurrentStableList[str]) -> None:
        self.codes = codes
        self.fail = False
        self.calls = 0

    async def active_tenants(self) -> ConcurrentStableList[TenantContext]:
        self.calls += 1
        if self.fail:
            raise RuntimeError("tenant registry down")
        return ConcurrentStableList(TenantContext(code=code, db_key=f"tenant_{code}", name=code) for code in self.codes)


class _Dedup:
    """幂等短窗口替身。"""

    def __init__(self, *, seen: bool = False) -> None:
        self._seen = seen
        self.remembered: ConcurrentStableList[str] = ConcurrentStableList()

    async def seen(self, *, group: str, event_id: str) -> bool:
        del group, event_id
        return self._seen

    async def seen_many(
        self, *, group: str, event_ids: ConcurrentStableList[str]
    ) -> ConcurrentStableFrozenDict[str, bool]:
        del group
        return ConcurrentStableFrozenDict({event_id: self._seen for event_id in event_ids})

    async def remember(self, *, group: str, event_id: str) -> None:
        del group
        self.remembered.add(event_id)

    async def remember_many(self, *, group: str, event_ids: ConcurrentStableList[str]) -> None:
        del group
        for event_id in event_ids:
            self.remembered.add(event_id)


class _Recorder:
    """死信写入器替身。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.entries: ConcurrentStableList[EventDeadLetterEntry] = ConcurrentStableList()
        self.fail = fail

    async def record(self, entry: EventDeadLetterEntry) -> None:
        if self.fail:
            raise RuntimeError("dead letter db down")
        self.entries.add(entry)


class _Metrics:
    """指标器替身（记录调用；可编排抛错）。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.counters: ConcurrentStableDict[str, float] = ConcurrentStableDict()
        self.histograms: ConcurrentStableDict[str, float] = ConcurrentStableDict()
        self.fail = fail

    async def counter(self, name: str, *, value: float = 1.0, labels: MetricLabels | None = None) -> None:
        if self.fail:
            raise RuntimeError("metrics down")
        key = f"{name}|{dict(labels or {})}"
        self.counters.set(key, self.counters.get(key, 0.0) + value)

    async def histogram(self, name: str, *, value: float, labels: MetricLabels | None = None) -> None:
        if self.fail:
            raise RuntimeError("metrics down")
        key = f"{name}|{dict(labels or {})}"
        self.histograms.set(key, self.histograms.get(key, 0.0) + 1.0)


class _Handler(EventConsumer):
    """可编排失败的处理器。"""

    def __init__(self, event_type: str, *, fail_times: int = 0) -> None:
        self._event_type = event_type
        self.fail_times = fail_times
        self.calls: ConcurrentStableList[str] = ConcurrentStableList()

    @property
    def event_type(self) -> str:
        return self._event_type

    async def consume(self, event: EventEnvelope) -> None:
        self.calls.add(event.event_id or "")
        if self.fail_times > 0:
            self.fail_times -= 1
            raise RuntimeError("handler boom")


class _FakeConsumer:
    """消费客户端替身。"""

    def __init__(
        self,
        *,
        batches: ConcurrentStableList[ConcurrentStableList[ReceivedMessage]] | None = None,
        partitions: ConcurrentStableList[int] | None = None,
        fail_polls: int = 0,
        error: Exception | None = None,
        paused: bool = False,
        ack_error: bool = False,
        nack_error: bool = False,
    ) -> None:
        self.batches = batches or ConcurrentStableList()
        self.acked: ConcurrentStableList[ReceivedMessage] = ConcurrentStableList()
        self.ack_attempts = 0
        self.nacked: ConcurrentStableList[str] = ConcurrentStableList()
        self.closed = False
        self.joined = False
        self.poll_calls = 0
        self._fail_polls = fail_polls
        self._error = error
        self._paused = paused
        self._ack_error = ack_error
        self._nack_error = nack_error
        self._assignment = Assignment(
            group="g",
            topic="t",
            consumer_id="c",
            partitions=ConcurrentStableFrozenList(partitions if partitions is not None else ConcurrentStableList([0])),
        )

    @property
    def assignment(self) -> Assignment | None:
        return self._assignment

    async def join(self) -> Assignment:
        self.joined = True
        return self._assignment

    async def poll(self, *, max_messages: int = 20, max_wait_ms: int = 30_000) -> PollResult:
        del max_messages, max_wait_ms
        self.poll_calls += 1
        if self._fail_polls > 0:
            self._fail_polls -= 1
            if self._error is not None:
                raise self._error
            raise MsgClientError(
                code=1,
                category=ErrorCategory.TRANSIENT,
                action=ClientAction.RETRY,
                message="poll failed",
            )
        if self._paused:
            return PollResult(paused=True)
        if not self.batches:
            return PollResult()
        return PollResult(messages=ConcurrentStableFrozenList(self.batches.pop(0)))

    async def ack(self, message: ReceivedMessage) -> object:
        self.ack_attempts += 1
        if self._ack_error:
            raise RuntimeError("ack failed")
        self.acked.add(message)
        return None

    async def nack(self, message: ReceivedMessage, *, reason: str = "processing_failed") -> object:
        if self._nack_error:
            raise RuntimeError("nack failed")
        self.nacked.add(reason)
        return None

    async def close(self) -> None:
        self.closed = True


def _settings(**overrides: object) -> Settings:
    consumer = EventConsumerSettings(
        provider="msg",
        enabled=True,
        host="in_service",
        group_prefix="bms",
        concurrency=2,
        batch_size=10,
        poll_interval_seconds=0.01,
        long_poll_ms=1000,
        tenant_refresh_seconds=10,
        max_retries=1,
        retry_backoff_seconds=0,
        dedup_ttl_seconds=60,
    )
    for name, value in overrides.items():
        setattr(consumer, name, value)
    return Settings(event_consumer=consumer)


def _event(
    *,
    event_type: str = "sys.operation.logged",
    event_id: str = "e-1",
    tenant_id: str | None = "1",
    aggregate_key: str | None = "tenant:1",
    event_version: str | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        payload=ConcurrentStableDict({"x": 1}),
        event_id=event_id,
        tenant_id=tenant_id,
        aggregate_key=aggregate_key,
        event_version=event_version,
        occurred_at=datetime(2026, 11, 18, 12, 0, 0, tzinfo=UTC).replace(tzinfo=None),
    )


def _message(event: EventEnvelope | None = None, *, payload: bytes | None = None) -> ReceivedMessage:
    source = event or _event()
    return ReceivedMessage(
        message_id=f"m-{source.event_id}",
        topic=topic_for(source.event_type),
        partition=0,
        offset=1,
        payload=payload if payload is not None else encode_event(source),
        headers=ConcurrentStableFrozenDict(event_attributes(source)),
    )


def _record(event_type: str, *, group: str = "audit-chain", ordered: bool = True) -> EventConsumerRecord:
    return EventConsumerRecord(
        consumer=group,
        event_type=event_type,
        handler_factory=lambda: _Handler(event_type),
        ordered=ordered,
    )


def _group(
    *,
    directory: _Directory | None = None,
    consumers: ConcurrentStableDict[tuple[str, str], _FakeConsumer] | None = None,
    dedup: _Dedup | None = None,
    recorder: _Recorder | None = None,
    metrics: _Metrics | None = None,
    settings: Settings | None = None,
) -> MsgEventConsumerGroup:
    table: ConcurrentStableDict[tuple[str, str], _FakeConsumer] = (
        consumers if consumers is not None else ConcurrentStableDict()
    )

    def _build(config: MessagingConfig, *, group: str, namespace: str, topic: str, consumer_id: str) -> MessageConsumer:
        del group, namespace, consumer_id
        return table.get((config.tenant, topic)) or _FakeConsumer()

    group = MsgEventConsumerGroup(
        settings=settings or _settings(),
        engine_registry=cast("EngineRegistry", object()),
        endpoints=ConcurrentStableList(["http://msg:8000"]),
        tenant_directory=directory,
        platform_tenant="platform",
        service="platform",
        dedup=cast("object", dedup or _Dedup()),  # pyright: ignore[reportArgumentType]
        metrics=cast("BaseMetrics", metrics) if metrics is not None else None,
        consumer_factory=_build,
        dead_letter_recorder=cast("object", recorder or _Recorder()),  # pyright: ignore[reportArgumentType]
    )
    return group


async def _wait(predicate: Callable[[], bool], *, rounds: int = 200) -> None:
    """等待条件成立（每轮 5ms，最多 1 秒）。"""
    import asyncio

    for _ in range(rounds):
        if predicate():
            return
        await asyncio.sleep(0.005)
    raise AssertionError("condition not met in time")


def test_load_builds_groups_topics_and_subscriptions() -> None:
    """声明装载：组 → 处理器 / 主题 → 命名空间；订阅由声明派生。"""
    group = _group()
    group.load(
        ConcurrentStableList(
            [
                _record("sys.operation.logged"),
                _record("sys.login.logged"),
                _record("sys.data.changed"),
            ]
        )
    )
    assert list(group.groups) == ["bms-audit-chain"]
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    assert set(runtime.topics.keys()) == {"bms-sys-operation", "bms-sys-login", "bms-sys-data"}
    assert set(runtime.topics.values()) == {"sys"}
    assert len(group.subscriptions()) == 3
    # 有序组按链键动态建道：未提交前活跃道数为 0。
    assert runtime.lanes_or_create().lanes == 0


def test_load_rejects_topic_with_second_namespace(monkeypatch: pytest.MonkeyPatch) -> None:
    """同一主题派生两个命名空间属实现缺陷（防御分支）。"""
    import bms_core.events.msg_consumer as module

    def _topic(_event_type: str) -> str:
        return "same-topic"

    def _namespace_sys(_event_type: str) -> str:
        return "sys"

    def _namespace_other(_event_type: str) -> str:
        return "other"

    group = _group()
    monkeypatch.setattr(module, "topic_for", _topic)
    monkeypatch.setattr(module, "namespace_for", _namespace_sys)
    group.load(ConcurrentStableList([_record("a.b.c")]))
    monkeypatch.setattr(module, "namespace_for", _namespace_other)
    with pytest.raises(EventConsumeError, match="不同命名空间"):
        group.load(ConcurrentStableList([_record("a.b.d")]))


async def test_start_consumes_and_acks() -> None:
    """启动 → 拉取 → 处理 → ack；指标与关闭都生效。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    event = _event()
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message(event)])]))
    metrics = _Metrics()
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        metrics=metrics,
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()
    assert consumer.closed
    success_key = "bms_event_consume_total|{'group': 'bms-audit-chain', 'result': 'succeeded'}"
    assert metrics.counters.get(success_key) == 1.0
    assert any(key.startswith("bms_event_consume_seconds_total|") for key in metrics.counters)


async def test_dedup_hit_skips_and_acks() -> None:
    """L1 命中：跳过处理，仍 ack。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message()])]))
    metrics = _Metrics()
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        dedup=_Dedup(seen=True),
        metrics=metrics,
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()
    assert "bms_event_consume_total|{'group': 'bms-audit-chain', 'result': 'skipped'}" in metrics.counters


async def test_retry_then_success() -> None:
    """首次失败、退避后成功：计 `retried` 并 ack。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message()])]))
    metrics = _Metrics()
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        metrics=metrics,
    )
    record = EventConsumerRecord(
        consumer="audit-chain",
        event_type="sys.operation.logged",
        handler_factory=lambda: _Handler("sys.operation.logged", fail_times=1),
        ordered=True,
    )
    group.load(ConcurrentStableList([record]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()
    assert "bms_event_consume_total|{'group': 'bms-audit-chain', 'result': 'retried'}" in metrics.counters


async def test_retry_exhausted_writes_dead_letter() -> None:
    """重试耗尽：写死信后 ack，死信计数 +1。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message()])]))
    recorder = _Recorder()
    metrics = _Metrics()
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        recorder=recorder,
        metrics=metrics,
    )
    record = EventConsumerRecord(
        consumer="audit-chain",
        event_type="sys.operation.logged",
        handler_factory=lambda: _Handler("sys.operation.logged", fail_times=9),
        ordered=True,
    )
    group.load(ConcurrentStableList([record]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()
    assert len(recorder.entries) == 1
    assert recorder.entries[0].retry_count == 1
    assert "bms_event_dead_letter_total|{'consumer': 'bms-audit-chain'}" in metrics.counters


async def test_dead_letter_write_failure_does_not_ack_and_nacks() -> None:
    """死信落库失败：不 ack，nack 兜底留痕（宁可重复不可丢）。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message()])]))
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        recorder=_Recorder(fail=True),
    )
    record = EventConsumerRecord(
        consumer="audit-chain",
        event_type="sys.operation.logged",
        handler_factory=lambda: _Handler("sys.operation.logged", fail_times=9),
        ordered=True,
    )
    group.load(ConcurrentStableList([record]))
    await group.start()
    await _wait(lambda: bool(consumer.nacked))
    await group.stop()
    assert not consumer.acked
    assert list(consumer.nacked) == ["processing_failed"]


async def test_poison_message_dead_letter() -> None:
    """解码失败：不重试，直接死信 + ack。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message(payload=b"not-json")])]))
    recorder = _Recorder()
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        recorder=recorder,
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()
    assert len(recorder.entries) == 1
    assert recorder.entries[0].event_type == "sys.operation.logged"


async def test_no_handler_dead_letter() -> None:
    """事件未在组内声明：死信 + ack。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    event = _event(event_type="sys.login.revoked")
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message(event)])]))
    recorder = _Recorder()
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-login"): consumer}),
        recorder=recorder,
    )
    group.load(ConcurrentStableList([_record("sys.login.logged")]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()
    assert len(recorder.entries) == 1
    assert "无处理器" in recorder.entries[0].error_msg


async def test_incompatible_version_dead_letter() -> None:
    """订阅不支持该主版本：毒消息路径。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    event = _event(event_type="sys.user.created", event_version="1.0.0")
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message(event)])]))
    recorder = _Recorder()
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-user"): consumer}),
        recorder=recorder,
    )
    group.load(ConcurrentStableList([_record("sys.user.created")]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()
    assert len(recorder.entries) == 1
    assert "契约版本" in recorder.entries[0].error_msg


async def test_tenant_refresh_adds_and_removes_units() -> None:
    """租户刷新：新增建单元，移除停单元；平台租户恒在。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumers: ConcurrentStableDict[tuple[str, str], _FakeConsumer] = ConcurrentStableDict(
        {
            ("t1", "bms-sys-operation"): _FakeConsumer(),
            ("t2", "bms-sys-operation"): _FakeConsumer(),
            ("platform", "bms-sys-operation"): _FakeConsumer(),
        }
    )
    group = _group(directory=directory, consumers=consumers)
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    assert set(key[0] for key in runtime.units) == {"t1", "platform"}
    directory.codes = ConcurrentStableList(["t2"])
    await group._refresh_tenants(initial=False)  # pyright: ignore[reportPrivateUsage]
    assert set(key[0] for key in runtime.units) == {"t2", "platform"}
    await group.stop()


async def test_directory_failure_keeps_existing_units() -> None:
    """租户清单不可用：保留旧集合，不停止已有消费。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumers: ConcurrentStableDict[tuple[str, str], _FakeConsumer] = ConcurrentStableDict(
        {("t1", "bms-sys-operation"): _FakeConsumer()}
    )
    group = _group(directory=directory, consumers=consumers)
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    directory.fail = True
    await group._refresh_tenants(initial=False)  # pyright: ignore[reportPrivateUsage]
    assert set(key[0] for key in runtime.units) == {"t1", "platform"}
    await group.stop()


async def test_directory_missing_falls_back_to_platform() -> None:
    """租户源不支持清单：只消费平台租户（告警一次）。"""
    consumer = _FakeConsumer()
    group = _group(
        directory=None,
        consumers=ConcurrentStableDict({("platform", "bms-sys-operation"): consumer}),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    assert set(key[0] for key in runtime.units) == {"platform"}
    await group.stop()


async def test_consume_once_returns_tally() -> None:
    """单轮消费：拉取一条 → 成功计数；单元关闭。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message()])]))
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    tally = await group.consume_once(max_messages=10)
    assert (tally.received, tally.succeeded) == (1, 1)
    assert consumer.closed


async def test_consume_once_empty_assignment_skips_poll() -> None:
    """分配为空（成员数 > 分区数）：不拉取、返回空汇总。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(partitions=ConcurrentStableList())
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    tally = await group.consume_once()
    assert tally.received == 0
    assert consumer.poll_calls == 0


async def test_start_requires_endpoints() -> None:
    """未配置实例地址：启动拒启（不在第一轮拉取才暴露）。"""
    group = MsgEventConsumerGroup(
        settings=_settings(),
        engine_registry=cast("EngineRegistry", object()),
        endpoints=ConcurrentStableList(),
        tenant_directory=None,
        platform_tenant="platform",
        service="platform",
        dead_letter_recorder=cast("object", _Recorder()),  # pyright: ignore[reportArgumentType]
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    with pytest.raises(EventConsumeError, match="实例地址"):
        await group.start()


async def test_poll_errors_and_paused_do_not_kill_unit() -> None:
    """poll 异常 / paused：退避续跑，不终止单元。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(
        fail_polls=1,
        error=MsgClientError(code=1, category=ErrorCategory.TRANSIENT, action=ClientAction.RETRY, message="x"),
        paused=True,
    )
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: consumer.poll_calls >= 3)
    await group.stop()
    assert consumer.closed


async def test_generic_poll_error_continues() -> None:
    """非 MsgClientError 的传输异常：记 error 后续跑。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(fail_polls=1, error=RuntimeError("boom"))
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: consumer.poll_calls >= 2)
    await group.stop()


async def test_ack_and_nack_failures_are_logged_only() -> None:
    """ack / nack 失败不改变消费结果（只记日志）。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    ack_fail = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message()])]), ack_error=True)
    group = _group(directory=directory, consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): ack_fail}))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: ack_fail.ack_attempts >= 1)
    await group.stop()

    nack_fail = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message()])]), nack_error=True)
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): nack_fail}),
        recorder=_Recorder(fail=True),
    )
    record = EventConsumerRecord(
        consumer="audit-chain",
        event_type="sys.operation.logged",
        handler_factory=lambda: _Handler("sys.operation.logged", fail_times=9),
        ordered=True,
    )
    group.load(ConcurrentStableList([record]))
    await group.start()
    await _wait(lambda: nack_fail.poll_calls >= 2)
    await group.stop()


async def test_metrics_failure_does_not_break_consumption() -> None:
    """指标器异常：消费照常成功（观测面不反噬业务）。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message()])]))
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        metrics=_Metrics(fail=True),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()


def test_platform_only_directory_returns_platform() -> None:
    """退化目录只返回平台租户。"""
    import asyncio

    contexts = asyncio.run(PlatformOnlyTenantDirectory("platform").active_tenants())
    assert [context.code for context in contexts] == ["platform"]


def test_config_and_consumer_id_shape() -> None:
    """客户端配置与成员标识：超时 = 长轮询 + 5s；id 字符合规且 ≤128。"""
    group = _group(settings=_settings(long_poll_ms=3000))
    config = group._config_for("t1")  # pyright: ignore[reportPrivateUsage]
    assert config.tenant == "t1"
    assert config.request_timeout_ms == 8000
    consumer_id = group._consumer_id("bms-sys-operation")  # pyright: ignore[reportPrivateUsage]
    assert len(consumer_id) <= 128
    assert all(char.isalnum() or char in "._:-" for char in consumer_id)


def test_dead_letter_property_and_tally_kinds() -> None:
    """死信写入器可取；四类结果与未知类别都归一为单条汇总。"""
    import bms_core.events.msg_consumer as module

    recorder = _Recorder()
    assert _group(recorder=recorder).dead_letter_recorder is recorder

    tally = module._tally_of  # pyright: ignore[reportPrivateUsage]
    assert tally("succeeded") == ConsumedTally(received=1, succeeded=1)
    assert tally("skipped") == ConsumedTally(received=1, skipped=1)
    assert tally("retried") == ConsumedTally(received=1, retried=1)
    assert tally("dead") == ConsumedTally(received=1, dead=1)


async def test_consume_once_without_groups_returns_zero() -> None:
    """未装载任何组：单轮消费直接返回空汇总（不建连）。"""
    tally = await _group().consume_once()
    assert tally == ConsumedTally()


async def test_setup_only_starts_when_in_service_and_enabled() -> None:
    """装配钩子只在「启用 + 服务进程宿主」时启动；worker 宿主与关闭开关只装载。"""
    for settings in (_settings(host="worker"), _settings(enabled=False)):
        group = _group(settings=settings)
        group.load(ConcurrentStableList([_record("sys.operation.logged")]))
        await group.setup()
        assert not group._running  # pyright: ignore[reportPrivateUsage]
        await group.stop()


def test_load_duplicate_event_keeps_single_handler() -> None:
    """同组重复声明同一事件：处理器只建一次，订阅按声明逐条保留。"""
    group = _group()
    group.load(ConcurrentStableList([_record("sys.operation.logged"), _record("sys.operation.logged")]))
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    assert list(runtime.handlers.keys()) == ["sys.operation.logged"]
    assert len(group.subscriptions()) == 2


async def test_directory_missing_warns_once() -> None:
    """租户源不支持清单：只告警一次（第二轮不再刷屏），仍返回平台租户。"""
    group = _group(directory=None)
    first = await group._active_tenant_codes()  # pyright: ignore[reportPrivateUsage]
    second = await group._active_tenant_codes()  # pyright: ignore[reportPrivateUsage]
    assert first == second == {"platform"}


async def test_initial_refresh_falls_back_when_directory_fails() -> None:
    """首次装载时清单不可用：退化为仅平台租户，不拒启。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    directory.fail = True
    group = _group(directory=directory)
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    assert set(key[0] for key in runtime.units) == {"platform"}
    await group.stop()


async def test_tenant_loop_refreshes_and_survives_failure() -> None:
    """租户刷新循环：正常轮次建单元，清单失败只告警不退出。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    group = _group(directory=directory, settings=_settings(tenant_refresh_seconds=0.05))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    group._running = True  # pyright: ignore[reportPrivateUsage]
    task = asyncio.create_task(group._tenant_loop())  # pyright: ignore[reportPrivateUsage]
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    await _wait(lambda: ("t1", "bms-sys-operation") in runtime.units)  # pyright: ignore[reportPrivateUsage]
    directory.fail = True
    # 等下一轮刷新真正走到失败分支（循环把异常吞掉并告警），再停机。
    await _wait(lambda: directory.calls >= 2)
    group._running = False  # pyright: ignore[reportPrivateUsage]
    await task


async def test_tenant_loop_returns_immediately_when_stopped() -> None:
    """循环入口已停机：直接返回（不再睡眠 / 刷新）。"""
    group = _group()
    await group._tenant_loop()  # pyright: ignore[reportPrivateUsage]


class _SlowDirectory:
    """租户清单慢响应（用于在刷新途中取消循环）。"""

    async def active_tenants(self) -> ConcurrentStableList[TenantContext]:
        await asyncio.sleep(10)
        return ConcurrentStableList()


async def test_tenant_loop_swallows_refresh_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """单轮刷新抛出未预期异常：记告警后继续下一轮，循环不退出。"""
    group = _group(settings=_settings(tenant_refresh_seconds=0.05))
    group._running = True  # pyright: ignore[reportPrivateUsage]
    calls: ConcurrentStableList[bool] = ConcurrentStableList()

    async def _boom(*, initial: bool) -> None:
        calls.add(initial)
        raise RuntimeError("refresh boom")

    monkeypatch.setattr(group, "_refresh_tenants", _boom)
    task = asyncio.create_task(group._tenant_loop())  # pyright: ignore[reportPrivateUsage]
    await _wait(lambda: len(calls) >= 1)
    group._running = False  # pyright: ignore[reportPrivateUsage]
    await task
    assert list(calls) == [False]


async def test_tenant_loop_cancel_propagates() -> None:
    """刷新途中取消：`CancelledError` 原样传播（不吞掉关闭信号）。"""
    group = _group(settings=_settings(tenant_refresh_seconds=0.05))
    group._tenant_directory = cast("TenantDirectory", _SlowDirectory())  # pyright: ignore[reportPrivateUsage]
    group._running = True  # pyright: ignore[reportPrivateUsage]
    task = asyncio.create_task(group._tenant_loop())  # pyright: ignore[reportPrivateUsage]
    await asyncio.sleep(0.06)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


class _JoinFailConsumer(_FakeConsumer):
    """加入组失败（主题不存在 / 网络抖动）。"""

    async def join(self) -> Assignment:
        raise RuntimeError("join failed")


class _CloseFailConsumer(_FakeConsumer):
    """关闭失败（不影响其它单元）。"""

    async def close(self) -> None:
        raise RuntimeError("close failed")


class _NoAssignmentConsumer(_FakeConsumer):
    """尚未拿到分配。"""

    @property
    def assignment(self) -> Assignment | None:
        return None


async def test_join_failure_leaves_unit_absent() -> None:
    """建单元 join 失败：告警并关闭客户端，不登记单元（下轮重试）。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _JoinFailConsumer()
    group = _group(directory=directory, consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    assert ("t1", "bms-sys-operation") not in runtime.units
    assert consumer.closed
    await group.stop()


async def test_stop_unit_missing_key_and_close_failure() -> None:
    """停单元：键不存在安全跳过；关闭异常只告警。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _CloseFailConsumer()
    group = _group(directory=directory, consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    await group._stop_unit(runtime, ("ghost", "bms-sys-operation"))  # pyright: ignore[reportPrivateUsage]
    assert ("t1", "bms-sys-operation") in runtime.units
    await group.stop()


async def test_run_unit_without_assignment_sleeps() -> None:
    """无分配单元：不 poll，按轮询间隔让出（等待再平衡）。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _NoAssignmentConsumer()
    group = _group(directory=directory, consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await asyncio.sleep(0.02)
    await group.stop()
    assert consumer.poll_calls == 0


async def test_run_unit_breaks_when_stop_requested_mid_batch() -> None:
    """停机请求发生在批量处理中：消息循环立即中断（不再处理后续消息）。"""
    import bms_core.events.msg_consumer as module

    group = _group()
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]

    class _Stopper(_FakeConsumer):
        async def poll(self, *, max_messages: int = 20, max_wait_ms: int = 30_000) -> PollResult:
            del max_messages, max_wait_ms
            group._running = False  # pyright: ignore[reportPrivateUsage]
            return PollResult(messages=ConcurrentStableFrozenList([_message()]))

    consumer = _Stopper()
    unit = module._ConsumerUnit(  # pyright: ignore[reportPrivateUsage]
        tenant="t1",
        group="bms-audit-chain",
        namespace="sys",
        topic="bms-sys-operation",
        consumer=consumer,
    )
    group._running = True  # pyright: ignore[reportPrivateUsage]
    await group._run_unit(runtime, unit)  # pyright: ignore[reportPrivateUsage]
    assert len(consumer.acked) == 0


async def test_run_unit_emits_batch_timing_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """`timing_enabled=True`：每批输出一条分段计时日志（拉取 / 处理 / ack / 条数）。"""
    import bms_core.events.msg_consumer as module

    captured: ConcurrentStableList[ConcurrentStableDict[str, object]] = ConcurrentStableList()

    class _Capturing:
        def info(self, event: str, **fields: object) -> None:
            if event == "event_consumer_batch_timing":
                captured.add(ConcurrentStableDict(fields))

        def warning(self, event: str, **fields: object) -> None:
            del event, fields

        def error(self, event: str, **fields: object) -> None:
            del event, fields

        def debug(self, event: str, **fields: object) -> None:
            del event, fields

    monkeypatch.setattr(module, "_LOGGER", _Capturing())
    group = _group(settings=_settings(timing_enabled=True))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    done = asyncio.Event()

    class _Timed(_FakeConsumer):
        async def poll(self, *, max_messages: int = 20, max_wait_ms: int = 30_000) -> PollResult:
            if self.batches:
                return await super().poll(max_messages=max_messages, max_wait_ms=max_wait_ms)
            group._running = False  # pyright: ignore[reportPrivateUsage]
            done.set()
            return PollResult()

    consumer = _Timed(batches=ConcurrentStableList([ConcurrentStableList([_message()])]))
    unit = module._ConsumerUnit(  # pyright: ignore[reportPrivateUsage]
        tenant="t1",
        group="bms-audit-chain",
        namespace="sys",
        topic="bms-sys-operation",
        consumer=consumer,
    )
    group._running = True  # pyright: ignore[reportPrivateUsage]
    task = asyncio.create_task(group._run_unit(runtime, unit))  # pyright: ignore[reportPrivateUsage]
    await done.wait()
    await task
    assert captured
    assert captured[0]["records"] == 1
    assert set(captured[0]) >= {"poll_ms", "process_ms", "ack_ms", "total_ms"}
    assert len(consumer.acked) == 1


async def test_settle_message_process_error_is_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    """处理链路抛未预期异常：只记日志，不向拉取循环冒泡。"""
    import bms_core.events.msg_consumer as module

    group = _group()
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    consumer = _FakeConsumer()

    async def _boom(*_: object, **__: object) -> object:
        raise RuntimeError("unexpected")

    monkeypatch.setattr(group, "_process_message", _boom)
    unit = module._ConsumerUnit(  # pyright: ignore[reportPrivateUsage]
        tenant="t1",
        group="bms-audit-chain",
        namespace="sys",
        topic="bms-sys-operation",
        consumer=consumer,
    )
    await group._settle_message(runtime, unit, _message())  # pyright: ignore[reportPrivateUsage]
    assert len(consumer.acked) == 0


async def test_poll_once_join_failure_and_empty_batch() -> None:
    """单轮消费：join 失败返回空汇总；空批量不进消息循环。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    join_fail = _JoinFailConsumer()
    group = _group(directory=directory, consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): join_fail}))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    assert (await group.consume_once()).received == 0
    assert join_fail.closed

    empty = _FakeConsumer()
    group = _group(directory=directory, consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): empty}))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    assert (await group.consume_once()).received == 0
    assert empty.poll_calls == 1


async def test_poll_once_without_assignment_skips_poll() -> None:
    """单轮消费：无分配不 poll / 不报错。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _NoAssignmentConsumer()
    group = _group(directory=directory, consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    assert (await group.consume_once()).received == 0
    assert consumer.poll_calls == 0


async def test_poll_once_batch_continues_after_unacked_message() -> None:
    """单轮消费：同批「不 ack」消息不中断后续消息（死信落库失败 → nack，下一条照常 ack）。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(
        batches=ConcurrentStableList(
            [
                ConcurrentStableList(
                    [
                        _message(payload=b"not-json"),
                        _message(_event(event_id="e-2")),
                    ]
                )
            ]
        )
    )
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        recorder=_Recorder(fail=True),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    tally = await group.consume_once()
    assert tally.received == 2
    assert list(consumer.nacked) == ["schema_invalid"]
    assert [message.message_id for message in consumer.acked] == ["m-e-2"]


def test_default_consumer_and_config_factory_paths() -> None:
    """缺省客户端构造走真实 `MsgConsumer`；注入配置工厂时直接取工厂产物。"""
    expected = MessagingConfig(endpoints=ConcurrentStableFrozenList(["http://msg:8000"]), tenant="t9")
    group = MsgEventConsumerGroup(
        settings=_settings(),
        engine_registry=cast("EngineRegistry", object()),
        endpoints=ConcurrentStableList(["http://msg:8000"]),
        tenant_directory=None,
        platform_tenant="platform",
        service="platform",
        config_factory=lambda tenant: expected,
        dead_letter_recorder=cast("object", _Recorder()),  # pyright: ignore[reportArgumentType]
    )
    assert group._config_for("t9") is expected  # pyright: ignore[reportPrivateUsage]

    real = MsgEventConsumerGroup(
        settings=_settings(),
        engine_registry=cast("EngineRegistry", object()),
        endpoints=ConcurrentStableList(["http://msg:8000"]),
        tenant_directory=None,
        platform_tenant="platform",
        service="platform",
        dead_letter_recorder=cast("object", _Recorder()),  # pyright: ignore[reportArgumentType]
    )
    consumer = real._make_consumer(tenant="t1", group="g", namespace="sys", topic="bms-sys-operation")  # pyright: ignore[reportPrivateUsage]
    assert isinstance(consumer, MsgConsumer)


async def test_setup_starts_when_in_service_and_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """装配钩子：启用且宿主为服务进程时调用 `start()`（worker 宿主只装载）。"""
    group = _group(settings=_settings(host="in_service", enabled=True))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    started: ConcurrentStableList[bool] = ConcurrentStableList()

    async def _start() -> None:
        started.add(True)

    monkeypatch.setattr(group, "start", _start)
    await group.setup()
    assert list(started) == [True]


async def test_start_without_declarations_returns_early() -> None:
    """无任何组声明：`start()` 直接返回，不建后台任务。"""
    group = _group()
    await group.start()
    assert not group._running  # pyright: ignore[reportPrivateUsage]


async def test_stop_unit_without_task_closes_consumer() -> None:
    """停单元：单元任务为空（已停或未起）仍释放客户端，不抛错。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer()
    group = _group(directory=directory, consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    unit = runtime.units[("t1", "bms-sys-operation")]
    unit.task = None
    await group._stop_unit(runtime, ("t1", "bms-sys-operation"))  # pyright: ignore[reportPrivateUsage]
    assert consumer.closed is True
    await group.stop()


async def test_run_unit_handles_empty_batch() -> None:
    """空批次：`poll` 返回空消息列表时本轮不处理任何消息，继续下一轮。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList()]))
    group = _group(directory=directory, consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}))
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: consumer.poll_calls >= 1)
    await group.stop()
    assert list(consumer.acked) == []


async def test_batch_continues_after_unacked_message() -> None:
    """同批「不 ack」消息不中断本批：前一条死信落库失败（nack 兜底），后一条照常处理并 ack。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(
        batches=ConcurrentStableList(
            [
                ConcurrentStableList(
                    [
                        _message(payload=b"not-json"),
                        _message(_event(event_id="e-2")),
                    ]
                )
            ]
        )
    )
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        recorder=_Recorder(fail=True),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()
    assert list(consumer.nacked) == ["schema_invalid"]
    assert [message.message_id for message in consumer.acked] == ["m-e-2"]


class _BatchHandler(_Handler):
    """批量处理器替身：按编排返回非可重试失败 / 数量不符 / 直接抛错。"""

    def __init__(
        self,
        event_type: str,
        *,
        kind: str = "failed",
        retryable: bool = False,
        delta: int = 0,
        raises: bool = False,
    ) -> None:
        super().__init__(event_type)
        self._kind = kind
        self._retryable = retryable
        self._delta = delta
        self._raises = raises

    async def consume_batch(
        self, events: ConcurrentStableList[EventEnvelope]
    ) -> ConcurrentStableList[BatchConsumeOutcome]:
        if self._raises:
            raise RuntimeError("batch boom")
        outcomes: ConcurrentStableList[BatchConsumeOutcome] = ConcurrentStableList()
        for event in events[: max(0, len(events) - self._delta)]:
            outcomes.add(
                BatchConsumeOutcome(
                    event_id=event.event_id or "",
                    kind=self._kind,
                    retryable=self._retryable,
                    error="batch failed",
                )
            )
        return outcomes


async def _run_single_with(handler: EventConsumer) -> tuple[_FakeConsumer, _Recorder, _Metrics]:
    """用给定处理器跑一条消息并返回观测点。

    Args:
        handler: 处理器实例。

    Returns:
        tuple[_FakeConsumer, _Recorder, _Metrics]: 消费替身 / 死信替身 / 指标替身。
    """
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(batches=ConcurrentStableList([ConcurrentStableList([_message()])]))
    recorder = _Recorder()
    metrics = _Metrics()
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        recorder=recorder,
        metrics=metrics,
    )
    record = EventConsumerRecord(
        consumer="audit-chain",
        event_type="sys.operation.logged",
        handler_factory=lambda: handler,
        ordered=True,
    )
    group.load(ConcurrentStableList([record]))
    await group.start()
    await _wait(lambda: bool(consumer.acked))
    await group.stop()
    return consumer, recorder, metrics


async def test_batch_non_retryable_failure_goes_dead_letter() -> None:
    """批结果标记不可重试：直接写死信并 ack（不进入退避重试）。"""
    consumer, recorder, _ = await _run_single_with(_BatchHandler("sys.operation.logged", retryable=False))
    assert consumer.acked
    assert len(recorder.entries) == 1
    assert recorder.entries[0].retry_count == 0


async def test_batch_result_length_mismatch_is_retried() -> None:
    """批结果数量不符：按可重试失败回退单条重试（此处单条成功 → 计 retried）。"""
    consumer, _, metrics = await _run_single_with(_BatchHandler("sys.operation.logged", delta=1))
    assert consumer.acked
    assert "bms_event_consume_total|{'group': 'bms-audit-chain', 'result': 'retried'}" in metrics.counters


async def test_batch_handler_exception_is_retried() -> None:
    """批处理器整体抛错：按可重试失败逐条重试，单条成功即 ack。"""
    consumer, _, metrics = await _run_single_with(_BatchHandler("sys.operation.logged", raises=True))
    assert consumer.acked
    assert "bms_event_consume_total|{'group': 'bms-audit-chain', 'result': 'retried'}" in metrics.counters


async def test_commit_batch_size_chunks_messages() -> None:
    """提交批量小于拉取条数：按 `commit_batch_size` 分块，两条都处理并 ack。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(
        batches=ConcurrentStableList(
            [ConcurrentStableList([_message(_event(event_id="e-1")), _message(_event(event_id="e-2"))])]
        )
    )
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        settings=_settings(commit_batch_size=1),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: len(consumer.acked) == 2)
    await group.stop()
    assert [message.message_id for message in consumer.acked] == ["m-e-1", "m-e-2"]


def test_chain_key_uses_declared_derivation() -> None:
    """链键：声明了派生函数就用它；未声明回落分区键。"""
    group = _group()
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    event = _event()
    assert group._chain_key_of(runtime, event) == "tenant:1"  # pyright: ignore[reportPrivateUsage]

    runtime.chain_keys.set("sys.operation.logged", lambda item: f"chain:{item.tenant_id}")
    assert group._chain_key_of(runtime, event) == "chain:1"  # pyright: ignore[reportPrivateUsage]


def test_load_registers_declared_chain_key() -> None:
    """装载声明时链键派生进入运行时（批量分道据此取键）。"""
    group = _group()
    record = EventConsumerRecord(
        consumer="audit-chain",
        event_type="sys.operation.logged",
        handler_factory=lambda: _Handler("sys.operation.logged"),
        ordered=True,
        chain_key=lambda event: "custom",
    )
    group.load(ConcurrentStableList([record]))
    runtime = group._groups["bms-audit-chain"]  # pyright: ignore[reportPrivateUsage]
    assert runtime.chain_keys.get("sys.operation.logged") is not None


def test_non_ordered_group_uses_fixed_lanes() -> None:
    """非有序组仍用固定道数（组级 concurrency 覆盖）。"""
    import bms_core.events.msg_consumer as module

    runtime = module._GroupRuntime(  # pyright: ignore[reportPrivateUsage]
        name="bms-job-monitor", ordered=False, concurrency=3
    )
    assert runtime.lanes_or_create().lanes == 3


async def test_dead_letter_ack_failure_on_poison_message_is_logged() -> None:
    """毒消息写死信成功后 ack 失败：只记日志，不阻断后续消息。"""
    directory = _Directory(ConcurrentStableList(["t1"]))
    consumer = _FakeConsumer(
        batches=ConcurrentStableList([ConcurrentStableList([_message(payload=b"not-json")])]), ack_error=True
    )
    group = _group(
        directory=directory,
        consumers=ConcurrentStableDict({("t1", "bms-sys-operation"): consumer}),
        recorder=_Recorder(),
    )
    group.load(ConcurrentStableList([_record("sys.operation.logged")]))
    await group.start()
    await _wait(lambda: consumer.ack_attempts > 0)
    await group.stop()
    assert consumer.ack_attempts == 1
    assert consumer.acked == []
