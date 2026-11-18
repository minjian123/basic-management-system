"""msg 消费组运行时（`event_consumer` 端口的真实实现，插件名 `msg`）。

**运行模型**：

- 声明来自各服务 `event_consumer_records()`，基座装配期 `load()` 一次；
- 一个 bms 组 → 按主题拆多个「租户 × 组 × 主题」消费单元，每单元一个 `MsgConsumer`；
- 同一组的所有单元共用**一个**键级串行执行器：`ordered=True` 道数固定 1（审计链跨主题串行），
  其余组按 `[event_consumer].concurrency`；
- 租户覆盖 = 平台租户（`[platform_tenant].code`）固定 + 业务租户经 `TenantDirectory` 动态枚举；
- 幂等 L1（Redis 只读预判 + 成功后标记）→ 处理器 → L2（处理器自身唯一约束）；
- 失败应用内退避重试，超限写 `sys_event_dead_letter` 后 `ack`；死信落库失败不 `ack`，
  以 `nack` 兜底；毒消息不重试。

**为什么按主题拆单元**：msg 的消费组身份是 `(租户, 主题, 组名)`，一个 `MsgConsumer` 只绑一个主题；
同组多主题（审计三事件）因此有多个单元，但执行器是组级共享的，顺序语义由执行器而不是 broker 承担。

**为什么不做运行期组互斥**：同一组被两个宿主同时消费属于部署错误，需要分布式租约才能拦；
本实现以 `[event_consumer].host` + 启动日志 + 运维检查把关，不在消费热路径引入租约开销。
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
import socket
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Protocol

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.config import Settings
from bms_core.core.exceptions import EventConsumeError
from bms_core.core.logging import get_logger
from bms_core.core.objects import BaseDataContract, BaseValueObject
from bms_core.db.registry import EngineRegistry
from bms_core.db.session import SessionFactory
from bms_core.db.tenant import TenantContext, TenantDirectory
from bms_core.events.base import (
    DEFAULT_CONSUME_BATCH,
    BaseEventConsumerGroup,
    ConsumedTally,
    EventConsumer,
    EventEnvelope,
)
from bms_core.events.consumer_records import EventConsumerRecord, qualify_consumer
from bms_core.events.contracts import EventSubscription, event_version_compatible, resolve_event_contract
from bms_core.events.dead_letter import EventDeadLetterEntry, EventDeadLetterRecorder
from bms_core.events.dedup import EventConsumeDedup
from bms_core.events.lane import KeyedLaneExecutor
from bms_core.events.topic import (
    ATTR_EVENT_ID,
    ATTR_EVENT_TYPE,
    decode_event,
    namespace_for,
    topic_for,
)
from bms_core.metrics.base import BaseMetrics
from bms_core.msgclient.messaging.config import MessagingConfig
from bms_core.msgclient.messaging.consumer import Assignment, MsgConsumer, PollResult, ReceivedMessage
from bms_core.msgclient.messaging.errors import MsgClientError
from bms_core.msgclient.messaging.stats import ClientStats
from bms_core.msgclient.messaging.transport_factory import build_transport

__all__ = ["MessageConsumer", "MsgEventConsumerGroup", "PlatformOnlyTenantDirectory"]

_LOGGER = get_logger("bms")

_METRIC_CONSUME = "bms_event_consume_total"
_METRIC_DEAD = "bms_event_dead_letter_total"
_METRIC_DURATION = "bms_event_consume_duration_seconds"

_CONSUMER_ID_PATTERN = re.compile(r"[^a-zA-Z0-9._:-]")
"""消费成员标识非法字符（msg 侧 `CONSUMER_ID_PATTERN` 只接受字母数字与 `._:-`）。"""

_LONG_POLL_TIMEOUT_SLACK_MS = 5_000
"""请求超时相对长轮询的余量（毫秒）：必须显著大于长轮询，否则客户端先超时。"""


@dataclass(frozen=True)
class _Outcome(BaseValueObject):
    """单条消息处理结果。

    Attributes:
        kind: 结果类别（`succeeded` / `skipped` / `retried` / `dead`）。
        ack: 是否应确认消息（死信落库失败时为 False，交给 broker 重投）。
    """

    kind: str
    ack: bool


class MessageConsumer(Protocol):
    """消费客户端契约（`MsgConsumer` 的结构化替身；用例注入假实现）。"""

    @property
    def assignment(self) -> Assignment | None:
        """当前分配（未加入为 None）。"""
        ...

    async def join(self) -> Assignment:
        """加入消费组。"""
        ...

    async def poll(self, *, max_messages: int = 20, max_wait_ms: int = 30_000) -> PollResult:
        """拉取一批消息。"""
        ...

    async def ack(self, message: ReceivedMessage) -> object:
        """确认一条消息。"""
        ...

    async def nack(self, message: ReceivedMessage, *, reason: str = "processing_failed") -> object:
        """拒绝一条消息（服务端转死信 + 位点前移）。"""
        ...

    async def close(self) -> None:
        """停心跳、离开组、关闭传输。"""
        ...


class PlatformOnlyTenantDirectory:
    """退化租户目录：只返回平台租户（租户源不支持清单时的显式降级）。

    只在「服务没有可枚举的租户源、但确实声明了消费组」时使用，并在启动日志告警；
    不静默假装业务租户也存在。
    """

    def __init__(self, platform_tenant: str) -> None:
        """初始化。

        Args:
            platform_tenant: 平台租户编码。
        """
        self._code = platform_tenant or "platform"

    async def active_tenants(self) -> ConcurrentStableList[TenantContext]:
        """只返回平台租户。

        Returns:
            ConcurrentStableList[TenantContext]: 仅含平台租户。
        """
        return ConcurrentStableList((TenantContext(code=self._code, db_key=f"tenant_{self._code}", name=self._code),))


@dataclass
class _ConsumerUnit(BaseDataContract):
    """消费单元：租户 × 组 × 主题（一个 `MsgConsumer` + 一个拉取协程）。"""

    tenant: str
    group: str
    namespace: str
    topic: str
    consumer: MessageConsumer
    task: asyncio.Task[None] | None = None


@dataclass
class _GroupRuntime(BaseDataContract):
    """单组运行时：处理器表 + 主题 → 命名空间 + 消费单元 + 组级执行器。"""

    name: str
    ordered: bool
    concurrency: int | None
    handlers: ConcurrentStableDict[str, EventConsumer] = field(
        default_factory=lambda: ConcurrentStableDict[str, EventConsumer]()
    )
    topics: ConcurrentStableDict[str, str] = field(default_factory=lambda: ConcurrentStableDict[str, str]())
    units: ConcurrentStableDict[tuple[str, str], _ConsumerUnit] = field(
        default_factory=lambda: ConcurrentStableDict[tuple[str, str], _ConsumerUnit]()
    )
    lanes: KeyedLaneExecutor | None = None

    def lanes_or_create(self) -> KeyedLaneExecutor:
        """取（或创建）组级执行器。

        Returns:
            KeyedLaneExecutor: 执行器（有序组 1 道）。
        """
        if self.lanes is None:
            self.lanes = KeyedLaneExecutor(1 if self.ordered else (self.concurrency or 1))
        return self.lanes


class MsgEventConsumerGroup(BaseEventConsumerGroup):
    """msg 消费组运行时（多组并行，组内键级串行，按租户装载）。"""

    plugin_name = "msg"

    def __init__(
        self,
        *,
        settings: Settings,
        engine_registry: EngineRegistry,
        endpoints: ConcurrentStableList[str],
        tenant_directory: TenantDirectory | None,
        platform_tenant: str,
        service: str,
        session_factory: SessionFactory | None = None,
        dedup: EventConsumeDedup | None = None,
        metrics: BaseMetrics | None = None,
        consumer_factory: Callable[..., MessageConsumer] | None = None,
        config_factory: Callable[[str], MessagingConfig] | None = None,
        dead_letter_recorder: EventDeadLetterRecorder | None = None,
    ) -> None:
        """初始化（不建连；`start()` 时才按租户建消费者）。

        Args:
            settings: 应用配置（`[event_consumer]`）。
            engine_registry: 引擎注册表（死信落平台库）。
            endpoints: msg 实例地址池（与发布器同源）。
            tenant_directory: 租户目录（None = 只消费平台租户并告警）。
            platform_tenant: 平台租户编码（无租户事件落点）。
            service: 服务标识（消费成员 id 前缀）。
            session_factory: 会话工厂（死信落库）。
            dedup: 幂等短窗口（缺省按配置构造）。
            metrics: 指标器（可选）。
            consumer_factory: 消费客户端工厂（单测注入替身）。
            config_factory: 租户 → 客户端配置工厂（单测注入；缺省按端点构造）。
            dead_letter_recorder: 死信写入器（单测注入替身；缺省按引擎注册表构造）。
        """
        self._settings = settings
        self._engine_registry = engine_registry
        self._endpoints = endpoints
        self._tenant_directory = tenant_directory
        self._platform_tenant = platform_tenant or "platform"
        self._service = service
        self._session_factory = session_factory
        self._dedup = dedup or EventConsumeDedup(ttl=settings.event_consumer.dedup_ttl_seconds)
        self._metrics = metrics
        self._consumer_factory = consumer_factory
        self._config_factory = config_factory
        self._dead_letters = dead_letter_recorder or EventDeadLetterRecorder(
            engine_registry=engine_registry, session_factory=session_factory
        )
        self._groups: ConcurrentStableDict[str, _GroupRuntime] = ConcurrentStableDict()
        self._records: ConcurrentStableList[EventConsumerRecord] = ConcurrentStableList()
        self._running = False
        self._refresh_task: asyncio.Task[None] | None = None
        self._directory_warned = False

    @property
    def enabled(self) -> bool:
        """消费是否启用（`[event_consumer].enabled`）。"""
        return bool(self._settings.event_consumer.enabled)

    @property
    def host(self) -> str:
        """宿主形态（`in_service` / `worker`）。"""
        return self._settings.event_consumer.host

    @property
    def groups(self) -> ConcurrentStableList[str]:
        """已装载的组名（诊断用）。"""
        return ConcurrentStableList(self._groups.keys())

    @property
    def dead_letter_recorder(self) -> EventDeadLetterRecorder:
        """死信写入器（诊断 / 测试注入故障用）。

        Returns:
            EventDeadLetterRecorder: 写入器。
        """
        return self._dead_letters

    def load(self, records: ConcurrentStableList[EventConsumerRecord]) -> None:
        """装载声明（按组建处理器表与主题表，不启动）。

        Args:
            records: 合并后的组声明。

        Raises:
            EventConsumeError: 同一主题被派生出两个命名空间（事件域不一致，属实现缺陷）。
        """
        for record in records:
            qualified = replace(
                record,
                consumer=qualify_consumer(record.consumer, group_prefix=self._settings.event_consumer.group_prefix),
            )
            runtime = self._groups.get(qualified.consumer)
            if runtime is None:
                runtime = _GroupRuntime(
                    name=qualified.consumer, ordered=qualified.ordered, concurrency=qualified.concurrency
                )
                self._groups.set(qualified.consumer, runtime)
            if runtime.handlers.get(qualified.event_type) is None:
                runtime.handlers.set(qualified.event_type, qualified.handler_factory())
            topic = topic_for(qualified.event_type)
            namespace = namespace_for(qualified.event_type)
            existing = runtime.topics.get(topic)
            if existing is not None and existing != namespace:
                raise EventConsumeError(f"同一主题派生出了不同命名空间：{topic}（{existing} / {namespace}）")
            runtime.topics.set(topic, namespace)
            self._records.add(qualified)

    def subscriptions(self) -> ConcurrentStableList[EventSubscription]:
        """由声明派生订阅清单（供契约覆盖校验与启动日志）。

        Returns:
            ConcurrentStableList[EventSubscription]: 订阅声明。
        """
        return ConcurrentStableList(
            EventSubscription(
                consumer=record.consumer,
                event_type=record.event_type,
                description=record.description,
            )
            for record in self._records
        )

    async def setup(self) -> None:
        """装配期钩子：仅当「启用且宿主为服务进程」时启动后台消费。"""
        if self.enabled and self.host == "in_service":
            await self.start()

    async def start(self) -> None:
        """启动各组的租户刷新与消费单元（幂等）。

        Raises:
            EventConsumeError: 未配置 msg 实例地址。
        """
        if self._running or not self._groups:
            return
        if not self._endpoints:
            raise EventConsumeError("msg 消费组启动失败：未配置消息平台实例地址")
        self._running = True
        for runtime in self._groups.values():
            runtime.lanes_or_create()
        await self._refresh_tenants(initial=True)
        self._refresh_task = asyncio.create_task(self._tenant_loop())
        _LOGGER.info(
            "event_consumer_started",
            groups=list(self._groups.keys()),
            host=self.host,
            platform_tenant=self._platform_tenant,
        )

    async def stop(self) -> None:
        """停止后台消费并等待在途完成（幂等）。"""
        self._running = False
        refresh = self._refresh_task
        self._refresh_task = None
        if refresh is not None:
            refresh.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await refresh
        for runtime in self._groups.values():
            for unit in ConcurrentStableList(runtime.units.values()):
                await self._stop_unit(runtime, (unit.tenant, unit.topic))
            lanes = runtime.lanes
            runtime.lanes = None
            if lanes is not None:
                await lanes.aclose()

    async def aclose(self) -> None:
        """释放资源（幂等；随 `ResourceManager` 逆序回收）。"""
        await self.stop()

    async def consume_once(self, *, max_messages: int = DEFAULT_CONSUME_BATCH) -> ConsumedTally:
        """对各组执行一轮拉取消费（诊断 / 联调用，不启动后台循环）。

        Args:
            max_messages: 单单元单轮拉取上限。

        Returns:
            ConsumedTally: 汇总结果。
        """
        total = ConsumedTally()
        if not self._groups:
            return total
        codes = await self._active_tenant_codes()
        tenants = codes if codes is not None else ConcurrentStableSet({self._platform_tenant})
        for runtime in self._groups.values():
            lanes = runtime.lanes_or_create()
            try:
                for tenant in tenants:
                    for topic, namespace in ConcurrentStableList(runtime.topics.items()):
                        tally = await self._poll_once(runtime, tenant, namespace, topic, max_messages=max_messages)
                        total = total.merge(tally)
            finally:
                await lanes.aclose()
                runtime.lanes = None
        return total

    async def _tenant_loop(self) -> None:
        """租户清单刷新循环（取消即退出）。"""
        interval = self._settings.event_consumer.tenant_refresh_seconds
        while self._running:
            await asyncio.sleep(interval)
            if not self._running:  # pragma: no cover - 取消与标志的竞态
                return
            try:
                await self._refresh_tenants(initial=False)
            except asyncio.CancelledError:  # pragma: no cover - 关闭期取消传播
                raise
            except Exception as exc:  # 单轮刷新异常不终止消费
                _LOGGER.warning("event_consumer_tenant_refresh_failed", error=repr(exc))

    async def _refresh_tenants(self, *, initial: bool) -> None:
        """按最新租户集合增删消费单元。

        Args:
            initial: 是否首次装载（清单不可用时退化为「仅平台租户」）。
        """
        codes = await self._active_tenant_codes()
        if codes is None:
            if not initial:
                return
            codes = ConcurrentStableSet({self._platform_tenant})
        for runtime in self._groups.values():
            for unit in ConcurrentStableList(runtime.units.values()):
                if unit.tenant not in codes:
                    await self._stop_unit(runtime, (unit.tenant, unit.topic))
            for tenant in codes:
                for topic, namespace in ConcurrentStableList(runtime.topics.items()):
                    if (tenant, topic) in runtime.units:
                        continue
                    await self._start_unit(runtime, tenant, namespace, topic)

    async def _active_tenant_codes(self) -> ConcurrentStableSet[str] | None:
        """取当前应消费的租户编码集合（平台租户固定并集）。

        Returns:
            ConcurrentStableSet[str] | None: 租户编码；清单不可用返回 None（调用方保留旧集合）。
        """
        if self._tenant_directory is None:
            if not self._directory_warned:
                self._directory_warned = True
                _LOGGER.warning(
                    "event_consumer_tenant_directory_missing",
                    detail="租户源不支持清单，只消费平台租户",
                    platform_tenant=self._platform_tenant,
                )
            return ConcurrentStableSet({self._platform_tenant})
        try:
            contexts = await self._tenant_directory.active_tenants()
        except Exception as exc:  # 清单不可用：保留旧集合，下轮重试
            _LOGGER.warning("event_consumer_tenant_directory_unavailable", error=repr(exc))
            return None
        codes: ConcurrentStableSet[str] = ConcurrentStableSet(context.code for context in contexts)
        codes.add(self._platform_tenant)
        return codes

    async def _start_unit(self, runtime: _GroupRuntime, tenant: str, namespace: str, topic: str) -> None:
        """建立并启动一个消费单元。

        Args:
            runtime: 组运行时。
            tenant: 租户编码。
            namespace: 事件域命名空间。
            topic: 主题名。
        """
        consumer = self._make_consumer(tenant=tenant, group=runtime.name, namespace=namespace, topic=topic)
        try:
            assignment = await consumer.join()
        except Exception as exc:  # 主题不存在 / 租户未开通 / 网络抖动：下轮刷新重试
            _LOGGER.warning(
                "event_consumer_join_failed",
                group=runtime.name,
                tenant=tenant,
                topic=topic,
                error=repr(exc),
            )
            with contextlib.suppress(Exception):
                await consumer.close()
            return
        unit = _ConsumerUnit(tenant=tenant, group=runtime.name, namespace=namespace, topic=topic, consumer=consumer)
        runtime.units.set((tenant, topic), unit)
        unit.task = asyncio.create_task(self._run_unit(runtime, unit))
        _LOGGER.info(
            "event_consumer_unit_started",
            group=runtime.name,
            tenant=tenant,
            namespace=namespace,
            topic=topic,
            partitions=list(assignment.partitions),
        )

    async def _stop_unit(self, runtime: _GroupRuntime, key: tuple[str, str]) -> None:
        """停止并释放一个消费单元。

        Args:
            runtime: 组运行时。
            key: `(租户, 主题)`。
        """
        unit = runtime.units.pop(key, None)
        if unit is None:
            return
        task = unit.task
        unit.task = None
        if task is not None:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        try:
            await unit.consumer.close()
        except Exception as exc:  # 关闭失败不阻断其它单元
            _LOGGER.warning(
                "event_consumer_unit_close_failed",
                group=unit.group,
                tenant=unit.tenant,
                topic=unit.topic,
                error=repr(exc),
            )

    async def _run_unit(self, runtime: _GroupRuntime, unit: _ConsumerUnit) -> None:
        """单消费单元拉取循环（取消即退出）。

        Args:
            runtime: 组运行时。
            unit: 消费单元。
        """
        interval = self._settings.event_consumer.poll_interval_seconds
        while self._running:
            assignment = unit.consumer.assignment
            if assignment is None or not assignment.partitions:
                await asyncio.sleep(interval)
                continue
            try:
                result = await unit.consumer.poll(
                    max_messages=self._settings.event_consumer.batch_size,
                    max_wait_ms=self._settings.event_consumer.long_poll_ms,
                )
            except asyncio.CancelledError:  # pragma: no cover - 关闭期取消传播
                raise
            except MsgClientError as exc:
                _LOGGER.warning(
                    "event_consumer_poll_failed",
                    group=unit.group,
                    tenant=unit.tenant,
                    topic=unit.topic,
                    error=repr(exc),
                )
                await asyncio.sleep(interval)
                continue
            except Exception as exc:  # 传输 / 解析异常：退避后续跑
                _LOGGER.error(
                    "event_consumer_poll_error",
                    group=unit.group,
                    tenant=unit.tenant,
                    topic=unit.topic,
                    error=repr(exc),
                )
                await asyncio.sleep(interval)
                continue
            if result.paused:
                await asyncio.sleep(interval)
                continue
            if not result.messages:
                # 长轮询正常会挂起；替身 / 异常实现返回空时也给事件循环让出机会，避免空转
                await asyncio.sleep(interval)
                continue
            for message in result.messages:
                if not self._running:
                    break
                await self._settle_message(runtime, unit, message)

    async def _settle_message(self, runtime: _GroupRuntime, unit: _ConsumerUnit, message: ReceivedMessage) -> None:
        """处理并确认一条消息（处理异常不终止该单元）。

        Args:
            runtime: 组运行时。
            unit: 消费单元。
            message: 拉取到的消息。
        """
        try:
            outcome = await self._process_message(runtime, unit, message)
        except asyncio.CancelledError:  # pragma: no cover - 关闭期取消传播
            raise
        except Exception as exc:  # 兜底：绝不让单条消息把拉取循环打挂
            _LOGGER.error("event_consumer_process_error", group=unit.group, error=repr(exc))
            return
        await self._count(runtime.name, outcome.kind)
        if not outcome.ack:
            return
        try:
            await unit.consumer.ack(message)
        except Exception as exc:  # ack 失败：msg 停等 + 可见性超时负责重投
            _LOGGER.warning(
                "event_consumer_ack_failed",
                group=unit.group,
                tenant=unit.tenant,
                topic=unit.topic,
                error=repr(exc),
            )

    async def _process_message(self, runtime: _GroupRuntime, unit: _ConsumerUnit, message: ReceivedMessage) -> _Outcome:
        """解码 → 版本校验 → 进串行道（预判 + 处理 + 标记）。

        Args:
            runtime: 组运行时。
            unit: 消费单元。
            message: 拉取到的消息。

        Returns:
            _Outcome: 处理结果。
        """
        try:
            event = decode_event(message.payload, ConcurrentStableDict(message.headers))
        except EventConsumeError as exc:
            return await self._to_dead_letter(
                runtime,
                unit,
                message,
                None,
                str(exc),
                event_type=_header(message, ATTR_EVENT_TYPE) or "unknown",
                schema_invalid=True,
            )
        handler = runtime.handlers.get(event.event_type)
        if handler is None:
            return await self._to_dead_letter(
                runtime,
                unit,
                message,
                event,
                f"无处理器（组未声明该事件）：{event.event_type}",
            )
        contract = resolve_event_contract(event.event_type)
        if contract is not None and not event_version_compatible(contract, event.event_version):
            return await self._to_dead_letter(
                runtime,
                unit,
                message,
                event,
                f"订阅不支持该契约版本：{event.event_version}",
            )
        lanes = runtime.lanes_or_create()
        return await lanes.submit(
            _partition_key(event),
            lambda: self._consume_once_deduped(runtime, unit, message, event, handler),
        )

    async def _consume_once_deduped(
        self,
        runtime: _GroupRuntime,
        unit: _ConsumerUnit,
        message: ReceivedMessage,
        event: EventEnvelope,
        handler: EventConsumer,
    ) -> _Outcome:
        """串行道内执行「预判 → 处理 → 标记」。

        Args:
            runtime: 组运行时。
            unit: 消费单元（死信 / nack 用）。
            message: 原始消息。
            event: 事件信封。
            handler: 处理器。

        Returns:
            _Outcome: 处理结果。
        """
        event_id = event.event_id or ""
        if await self._dedup.seen(group=runtime.name, event_id=event_id):
            return _Outcome("skipped", True)
        try:
            await self._invoke(runtime.name, handler, event)
        except Exception as exc:
            return await self._retry_or_dead(runtime, unit, message, event, handler, exc)
        await self._dedup.remember(group=runtime.name, event_id=event_id)
        return _Outcome("succeeded", True)

    async def _invoke(self, group: str, handler: EventConsumer, event: EventEnvelope) -> None:
        """调用处理器并记录耗时（失败原样上抛）。

        Args:
            group: 组名（指标标签）。
            handler: 处理器。
            event: 事件信封。
        """
        started = time.perf_counter()
        try:
            await handler.consume(event)
        except Exception:
            await self._observe(group, "failure", time.perf_counter() - started)
            raise
        await self._observe(group, "success", time.perf_counter() - started)

    async def _retry_or_dead(
        self,
        runtime: _GroupRuntime,
        unit: _ConsumerUnit,
        message: ReceivedMessage,
        event: EventEnvelope,
        handler: EventConsumer,
        error: Exception,
    ) -> _Outcome:
        """应用内退避重试，耗尽后转死信。

        Args:
            runtime: 组运行时。
            unit: 消费单元。
            message: 原始消息。
            event: 事件信封。
            handler: 处理器。
            error: 首次失败原因。

        Returns:
            _Outcome: 处理结果。
        """
        settings = self._settings.event_consumer
        last_error = error
        for attempt in range(1, settings.max_retries + 1):
            await asyncio.sleep(settings.retry_backoff_seconds * (2 ** (attempt - 1)))
            try:
                await self._invoke(runtime.name, handler, event)
            except Exception as exc:  # 记录最近一次原因，继续退避
                last_error = exc
                continue
            await self._dedup.remember(group=runtime.name, event_id=event.event_id or "")
            return _Outcome("retried", True)
        return await self._to_dead_letter(
            runtime,
            unit,
            message,
            event,
            f"重试 {settings.max_retries} 次仍失败：{last_error!r}",
            retry_count=settings.max_retries,
        )

    async def _to_dead_letter(
        self,
        runtime: _GroupRuntime,
        unit: _ConsumerUnit,
        message: ReceivedMessage,
        event: EventEnvelope | None,
        error: str,
        *,
        event_type: str | None = None,
        schema_invalid: bool = False,
        retry_count: int = 0,
    ) -> _Outcome:
        """写消费死信（落库失败不 ack，并尝试 nack 兜底）。

        Args:
            runtime: 组运行时。
            unit: 消费单元。
            message: 原始消息。
            event: 已解码事件（毒消息为 None）。
            error: 失败原因。
            event_type: 事件类型（毒消息取属性值）。
            schema_invalid: 是否毒消息（nack 原因取 `schema_invalid`）。
            retry_count: 已重试次数。

        Returns:
            _Outcome: 处理结果。
        """
        entry = EventDeadLetterEntry(
            consumer=runtime.name,
            event_id=(event.event_id if event else None) or _header(message, ATTR_EVENT_ID) or message.message_id,
            event_type=(event.event_type if event else None) or event_type or "unknown",
            error_msg=error,
            payload=ConcurrentStableFrozenDict(event.payload) if event else ConcurrentStableFrozenDict[str, object](),
            aggregate_key=event.aggregate_key if event else None,
            tenant_id=event.tenant_id if event else None,
            retry_count=retry_count,
            occurred_at=event.occurred_at if event else None,
        )
        try:
            await self._dead_letters.record(entry)
        except Exception as exc:  # 死信落库失败：不 ack；nack 兜底留痕
            _LOGGER.error(
                "event_dead_letter_failed",
                group=runtime.name,
                event_id=entry.event_id,
                error=repr(exc),
            )
            await self._nack(unit, message, schema_invalid=schema_invalid)
            return _Outcome("dead", False)
        await self._dead_count(runtime.name)
        return _Outcome("dead", True)

    async def _nack(self, unit: _ConsumerUnit, message: ReceivedMessage, *, schema_invalid: bool) -> None:
        """尝试 nack（失败只记日志，不改变「不 ack」的结论）。

        Args:
            unit: 消费单元。
            message: 原始消息。
            schema_invalid: 是否毒消息。
        """
        reason = "schema_invalid" if schema_invalid else "processing_failed"
        try:
            await unit.consumer.nack(message, reason=reason)
        except Exception as exc:  # nack 也失败：留给可见性超时重投
            _LOGGER.warning("event_consumer_nack_failed", group=unit.group, error=repr(exc))

    async def _poll_once(
        self, runtime: _GroupRuntime, tenant: str, namespace: str, topic: str, *, max_messages: int
    ) -> ConsumedTally:
        """单租户单主题拉取一轮并处理（诊断用；不启动后台任务）。

        Args:
            runtime: 组运行时。
            tenant: 租户编码。
            namespace: 事件域命名空间。
            topic: 主题名。
            max_messages: 拉取上限。

        Returns:
            ConsumedTally: 本轮汇总。
        """
        consumer = self._make_consumer(tenant=tenant, group=runtime.name, namespace=namespace, topic=topic)
        try:
            await consumer.join()
        except Exception as exc:
            _LOGGER.warning(
                "event_consumer_join_failed",
                group=runtime.name,
                tenant=tenant,
                topic=topic,
                error=repr(exc),
            )
            with contextlib.suppress(Exception):
                await consumer.close()
            return ConsumedTally()
        unit = _ConsumerUnit(tenant=tenant, group=runtime.name, namespace=namespace, topic=topic, consumer=consumer)
        tally = ConsumedTally()
        try:
            assignment = consumer.assignment
            if assignment is None or not assignment.partitions:
                return tally
            result = await consumer.poll(
                max_messages=max_messages, max_wait_ms=self._settings.event_consumer.long_poll_ms
            )
            for message in result.messages:
                outcome = await self._process_message(runtime, unit, message)
                tally = tally.merge(_tally_of(outcome.kind))
                await self._count(runtime.name, outcome.kind)
                if outcome.ack:
                    with contextlib.suppress(Exception):
                        await consumer.ack(message)
        finally:
            with contextlib.suppress(Exception):
                await consumer.close()
        return tally

    def _make_consumer(self, *, tenant: str, group: str, namespace: str, topic: str) -> MessageConsumer:
        """构造一个消费客户端（用例可注入工厂）。

        Args:
            tenant: 租户编码。
            group: 组名。
            namespace: 事件域命名空间。
            topic: 主题名。

        Returns:
            MessageConsumer: 消费客户端。
        """
        consumer_id = self._consumer_id(topic)
        if self._consumer_factory is not None:
            return self._consumer_factory(
                self._config_for(tenant), group=group, namespace=namespace, topic=topic, consumer_id=consumer_id
            )
        config = self._config_for(tenant)
        return MsgConsumer(
            config,
            build_transport(config),
            ClientStats(),
            group=group,
            namespace=namespace,
            topic=topic,
            consumer_id=consumer_id,
        )

    def _config_for(self, tenant: str) -> MessagingConfig:
        """按租户构造客户端配置（缺省实现；用例可注入工厂）。

        Args:
            tenant: 租户编码。

        Returns:
            MessagingConfig: 客户端配置。
        """
        if self._config_factory is not None:
            return self._config_factory(tenant)
        return MessagingConfig(
            endpoints=ConcurrentStableFrozenList(self._endpoints),
            tenant=tenant,
            request_timeout_ms=self._settings.event_consumer.long_poll_ms + _LONG_POLL_TIMEOUT_SLACK_MS,
        )

    def _consumer_id(self, topic: str) -> str:
        """构造消费成员标识（组内唯一；含主机 / 进程 / 主题 / 随机后缀）。

        Args:
            topic: 主题名。

        Returns:
            str: 成员标识（≤128，字符集符合 msg 约束）。
        """
        host = _CONSUMER_ID_PATTERN.sub("-", socket.gethostname() or "host")
        topic_part = _CONSUMER_ID_PATTERN.sub("-", topic)[-24:]
        raw = f"{self._service}-{host}-{os.getpid()}-{topic_part}-{uuid.uuid4().hex[:8]}"
        return raw[:128]

    async def _count(self, group: str, kind: str) -> None:
        """上报消费结果计数。

        Args:
            group: 组名。
            kind: 结果类别。
        """
        if self._metrics is None:
            return
        with contextlib.suppress(Exception):
            await self._metrics.counter(_METRIC_CONSUME, labels={"group": group, "result": kind})

    async def _dead_count(self, group: str) -> None:
        """上报转死信计数。

        Args:
            group: 组名。
        """
        if self._metrics is None:
            return
        with contextlib.suppress(Exception):
            await self._metrics.counter(_METRIC_DEAD, labels={"consumer": group})

    async def _observe(self, group: str, result: str, seconds: float) -> None:
        """上报单次处理器耗时（指标失败不影响消费）。

        Args:
            group: 组名。
            result: `success` / `failure`。
            seconds: 耗时（秒）。
        """
        if self._metrics is None:
            return
        with contextlib.suppress(Exception):
            await self._metrics.histogram(_METRIC_DURATION, value=seconds, labels={"group": group, "result": result})


def _partition_key(event: EventEnvelope) -> str:
    """分区键：聚合键 → 租户 → 事件 ID（同聚合 / 同租户串行）。

    Args:
        event: 事件信封。

    Returns:
        str: 分区键。
    """
    return event.aggregate_key or event.tenant_id or event.event_id or ""


def _header(message: ReceivedMessage, name: str) -> str | None:
    """取消息头（缺失返回 None）。

    Args:
        message: 拉取到的消息。
        name: 头名。

    Returns:
        str | None: 头值。
    """
    value = message.headers.get(name)
    return None if value is None else str(value)


def _tally_of(kind: str) -> ConsumedTally:
    """把单条结果转成可合并汇总。

    Args:
        kind: 结果类别。

    Returns:
        ConsumedTally: 单条汇总。
    """
    if kind == "succeeded":
        return ConsumedTally(received=1, succeeded=1)
    if kind == "skipped":
        return ConsumedTally(received=1, skipped=1)
    if kind == "retried":
        return ConsumedTally(received=1, retried=1)
    return ConsumedTally(received=1, dead=1)
