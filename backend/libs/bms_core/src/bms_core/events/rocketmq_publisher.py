"""事件发布真实实现 `RocketMqEventPublisher`：把发件箱投递的事件投到 RocketMQ 5.x。

- **接入形态**：5.x gRPC 客户端（`rocketmq-python-client`，模块名 `rocketmq`），端点取 broker proxy
  （`--enable-proxy` 后的 8081）。remoting 的 9876 / 10911 不走。
- **一个 topic 一个 producer**：SDK 的 `Producer` 在 `startup()` 时声明 topic 集合，动态新增 topic
  需重建 producer；按 topic 缓存 producer 既避免重建，也让「新增事件域」无需重启。
- **同步 SDK 不占事件循环**：`send` 是阻塞调用，统一 `asyncio.to_thread` 执行——否则一次网络抖动
  会卡死整个进程的请求。
- **失败语义**：发送异常上抛 `EventPublishError`，由投递器 `mark_failed` 退避重试 / 转死信；
  本类不做重试（重试归发件箱，避免两处重试叠加）。
- **延迟导入**：SDK 在首次发布时才导入——未部署 broker 的环境不需要它，启动也不受影响；
  单测经 `producer_factory` / `message_factory` 注入替身，全程不碰 SDK。
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from bms_core.core.capability import BaseAsyncResource
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import Settings
from bms_core.core.exceptions import OutboxDeliveryError
from bms_core.core.logging import get_logger
from bms_core.events.base import EventEnvelope, EventPublisher
from bms_core.events.topic import ATTR_EVENT_ID, encode_event, event_attributes, topic_for

__all__ = ["EventPublishError", "RocketMqEventPublisher", "current_traceparent"]

_LOGGER = get_logger("bms")

_TRACEPARENT_KEY = "traceparent"
"""W3C 链路上下文键（`opentelemetry.propagate` 的 carrier 键）。"""


class EventPublishError(OutboxDeliveryError):
    """事件投递失败（复用发件箱投递段 `10009`）。

    由投递器 `mark_failed` 按失败分支处理：指数退避重试，超限转死信（不在此处重试）。
    """

    def __init__(self, message: str | None = None, *, data: object | None = None) -> None:
        super().__init__(message, data=data)


def current_traceparent() -> str | None:
    """取当前 OTel 链路的 W3C `traceparent`（无 OTel / 无活动 span 返回 None）。

    Returns:
        str | None: `traceparent` 头值。
    """
    try:
        from opentelemetry import propagate
    except Exception:  # pragma: no cover - 依赖缺失时退化为只透传 trace_id
        return None
    carrier: ConcurrentStableDict[str, str] = ConcurrentStableDict()
    try:
        propagate.inject(carrier)
    except Exception:  # pragma: no cover - 上下文损坏时不阻断发布
        return None
    return carrier.get(_TRACEPARENT_KEY)


class RocketMqEventPublisher(EventPublisher, BaseAsyncResource):
    """RocketMQ 事件发布（每 topic 一个 producer，懒启动、幂等关闭）。"""

    plugin_name = "rocketmq"

    def __init__(
        self,
        *,
        endpoints: str,
        namespace: str = "",
        access_key: str = "",
        secret_key: str = "",
        request_timeout_seconds: float = 3.0,
        producer_factory: Callable[[str], Any] | None = None,
        message_factory: Callable[[], Any] | None = None,
    ) -> None:
        """初始化（不建连；首次发布时按需启动 producer）。

        Args:
            endpoints: gRPC 接入点（`host:port`）。
            namespace: 命名空间（空 = 不启用）。
            access_key: 访问密钥 ID（ACL 开启时必填）。
            secret_key: 访问密钥。
            request_timeout_seconds: 单次请求超时（秒）。
            producer_factory: producer 工厂 `(topic) -> producer`（单测注入替身）。
            message_factory: 消息工厂 `() -> message`（单测注入替身）。
        """
        self._endpoints = endpoints
        self._namespace = namespace
        self._access_key = access_key
        self._secret_key = secret_key
        self._request_timeout_seconds = request_timeout_seconds
        self._producer_factory = producer_factory
        self._message_factory = message_factory
        self._producers: ConcurrentStableDict[str, Any] = ConcurrentStableDict()
        self._config: Any = None

    @property
    def event_type(self) -> str:
        """事件类型（发布侧无固定类型，返回通配标识）。

        Returns:
            str: 通配标识 `*`。
        """
        return "*"

    async def publish(self, event: EventEnvelope) -> None:
        """发布事件（同步 SDK 移到线程池，失败抛 `EventPublishError`）。

        Args:
            event: 事件信封。

        Raises:
            EventPublishError: 发送失败（由投递器退避重试 / 转死信）。
        """
        topic = topic_for(event.event_type)
        body = encode_event(event)
        attributes = event_attributes(event, traceparent=current_traceparent())
        tag = event.event_type.rsplit(".", 1)[-1]
        keys = attributes.get(ATTR_EVENT_ID, "")
        try:
            await asyncio.to_thread(self._send_sync, topic, body, attributes, tag, keys)
        except EventPublishError:
            raise
        except Exception as exc:
            raise EventPublishError(
                f"事件投递失败：{event.event_type}（{topic}）：{exc!r}",
                data={"event_type": event.event_type, "topic": topic},
            ) from exc

    async def publish_transactional(self, event: EventEnvelope) -> None:
        """事务消息发布（基线委托普通发送）。

        架构口径：事务消息为备选方案、**当前不作基线**——一致性由事务性发件箱保证，
        故此处直接委托 `publish`；接口保留以便后续切换实现。

        Args:
            event: 事件信封。
        """
        await self.publish(event)

    async def setup(self) -> None:
        """生命周期钩子（producer 懒启动，此处不建连）。"""

    async def aclose(self) -> None:
        """释放 producer 与客户端配置（幂等）。"""
        producers = list(self._producers.values())
        self._producers.clear()
        for producer in producers:
            try:
                await asyncio.to_thread(producer.shutdown)
            except Exception as exc:  # 关闭失败不阻断其它资源回收
                _LOGGER.warning("rocketmq_producer_shutdown_failed", error=repr(exc))
        self._config = None

    @classmethod
    def from_settings(cls, settings: Settings) -> RocketMqEventPublisher:
        """按配置构造（装配工厂用）。

        Args:
            settings: 应用配置（`[rocketmq]`）。

        Returns:
            RocketMqEventPublisher: 发布实例。
        """
        rocketmq = settings.rocketmq
        return cls(
            endpoints=rocketmq.endpoints,
            namespace=rocketmq.namespace,
            access_key=rocketmq.access_key,
            secret_key=rocketmq.secret_key,
            request_timeout_seconds=rocketmq.request_timeout_seconds,
        )

    def _send_sync(
        self,
        topic: str,
        body: bytes,
        attributes: ConcurrentStableDict[str, str],
        tag: str,
        keys: str,
    ) -> None:
        """同步发送（在线程池中执行）。

        Args:
            topic: 目标 topic。
            body: 消息体。
            attributes: 消息属性。
            tag: 消息 tag（动作段）。
            keys: 消息 keys（幂等键）。
        """
        producer = self._producer(topic)
        message = self._build_message(topic, body, attributes, tag, keys)
        producer.send(message)

    def _producer(self, topic: str) -> Any:
        """取（或创建）该 topic 的 producer。

        Args:
            topic: topic 名。

        Returns:
            Any: producer 实例（官方 SDK 对象或测试替身）。
        """
        existing = self._producers.get(topic)
        if existing is not None:
            return existing
        producer = self._producer_factory(topic) if self._producer_factory else self._sdk_producer(topic)
        self._producers[topic] = producer
        return producer

    def _sdk_producer(self, topic: str) -> Any:
        """用官方 SDK 创建 producer 并启动（延迟导入）。

        Args:
            topic: topic 名。

        Returns:
            Any: SDK producer。

        Raises:
            EventPublishError: 端点未配置 / SDK 未安装 / 启动失败。
        """
        if not self._endpoints:
            raise EventPublishError(
                "RocketMQ 端点未配置（[rocketmq].endpoints / BMS_ROCKETMQ__ENDPOINTS）",
                data={"topic": topic},
            )
        try:
            from rocketmq import Producer
        except ImportError as exc:  # pragma: no cover - 依赖缺失属部署问题
            raise EventPublishError(
                "缺少 RocketMQ 客户端依赖（rocketmq-python-client）", data={"topic": topic}
            ) from exc
        config = self._client_configuration()
        if config is None:  # pragma: no cover - 由 _client_configuration 保证非空
            raise EventPublishError("RocketMQ 客户端配置未就绪", data={"topic": topic})
        producer = Producer(config, (topic,))
        producer.startup()
        _LOGGER.info("rocketmq_producer_started", topic=topic, endpoints=self._endpoints)
        return producer

    def _client_configuration(self) -> Any:
        """构造（并缓存）客户端配置。

        Returns:
            Any: `ClientConfiguration`；依赖缺失时 None。
        """
        if self._config is not None:
            return self._config
        try:
            from rocketmq import ClientConfiguration, Credentials
        except ImportError:  # pragma: no cover - 依赖缺失属部署问题
            return None
        has_credentials = bool(self._access_key and self._secret_key)
        credentials = Credentials(self._access_key, self._secret_key) if has_credentials else Credentials()
        self._config = (
            ClientConfiguration(self._endpoints, credentials, self._namespace)
            if self._namespace
            else ClientConfiguration(self._endpoints, credentials)
        )
        return self._config

    def _build_message(
        self,
        topic: str,
        body: bytes,
        attributes: ConcurrentStableDict[str, str],
        tag: str,
        keys: str,
    ) -> Any:
        """构造消息对象（测试可经 message 替身断言字段）。

        Args:
            topic: 目标 topic。
            body: 消息体。
            attributes: 消息属性。
            tag: 消息 tag。
            keys: 消息 keys。

        Returns:
            Any: 消息对象。
        """
        message = self._message_factory() if self._message_factory else self._sdk_message()
        message.topic = topic
        message.body = body
        message.tag = tag
        message.keys = keys
        for name, value in attributes.items():
            message.add_property(name, value)
        return message

    def _sdk_message(self) -> Any:
        """构造 SDK 空消息（延迟导入）。

        Returns:
            Any: SDK `Message`。
        """
        from rocketmq import Message

        return Message()
