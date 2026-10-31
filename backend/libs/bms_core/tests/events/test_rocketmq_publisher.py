"""RocketMQ 发布实现护栏：topic 派生 / producer 复用 / 消息字段 / 失败包装 / 关闭。

依据《详细设计 · 事件总线》§4.2：业务不直连 MQ，投递器经 `EventPublisher` 端口转发；
本实现只负责最后一跳——同步 SDK 移出事件循环、按 topic 复用 producer、失败上抛交投递器重试。
"""

import asyncio

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.events.base import EventEnvelope
from bms_core.events.rocketmq_publisher import EventPublishError, RocketMqEventPublisher
from bms_core.events.topic import ATTR_EVENT_ID, ATTR_EVENT_TYPE, decode_event


class _Message:
    """消息替身（与 SDK `Message` 同形的最小接口）。"""

    def __init__(self) -> None:
        """初始化空消息。"""
        self.topic: str | None = None
        self.body: bytes | None = None
        self.tag: str | None = None
        self.keys: str | None = None
        self.properties: ConcurrentStableDict[str, str] = ConcurrentStableDict()

    def add_property(self, name: str, value: str) -> None:
        """加属性。

        Args:
            name: 属性名。
            value: 属性值。
        """
        self.properties[name] = value


class _Producer:
    """producer 替身：记录发送内容与关闭次数。"""

    def __init__(self, topic: str) -> None:
        """初始化。

        Args:
            topic: 该 producer 声明的 topic。
        """
        self.topic = topic
        self.sent: ConcurrentStableList[_Message] = ConcurrentStableList()
        self.shutdown_calls = 0
        self.fail: Exception | None = None

    def send(self, message: _Message) -> None:
        """发送（可注入失败）。

        Args:
            message: 消息。

        Raises:
            Exception: 注入的失败。
        """
        if self.fail is not None:
            raise self.fail
        self.sent.add(message)

    def shutdown(self) -> None:
        """关闭。"""
        self.shutdown_calls += 1


class _Factory:
    """producer 工厂替身：按 topic 产出并留档。"""

    def __init__(self) -> None:
        """初始化。"""
        self.created: ConcurrentStableList[_Producer] = ConcurrentStableList()
        self.error: Exception | None = None

    def __call__(self, topic: str) -> _Producer:
        """按 topic 建 producer。

        Args:
            topic: topic 名。

        Returns:
            _Producer: producer 替身。

        Raises:
            Exception: 注入的建连失败。
        """
        if self.error is not None:
            raise self.error
        producer = _Producer(topic)
        self.created.add(producer)
        return producer


def _publisher(factory: _Factory) -> RocketMqEventPublisher:
    """构造注入替身的发布器。

    Args:
        factory: producer 工厂替身。

    Returns:
        RocketMqEventPublisher: 发布器。
    """
    return RocketMqEventPublisher(endpoints="127.0.0.1:8081", producer_factory=factory, message_factory=_Message)


def _event(event_type: str = "sys.user.created", **overrides: object) -> EventEnvelope:
    """构造事件。

    Args:
        event_type: 事件类型。
        **overrides: 覆盖字段。

    Returns:
        EventEnvelope: 事件信封。
    """
    base: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "event_type": event_type,
            "event_id": "evt-1",
            "tenant_id": "1234567890",
            "aggregate_key": "1234567890",
            "payload": ConcurrentStableDict({"user_id": "u-1"}),
        }
    )
    base.update(overrides)
    return EventEnvelope(**base)  # type: ignore[arg-type]


async def test_publish_routes_to_domain_object_topic() -> None:
    """topic 取事件名前两段（`sys.user.created` → `bms.sys.user`）。"""
    factory = _Factory()
    await _publisher(factory).publish(_event())
    assert [producer.topic for producer in factory.created] == ["bms.sys.user"]


async def test_publish_reuses_producer_per_topic() -> None:
    """同 topic 多次发布复用同一 producer（SDK 的 topic 集合在 startup 时确定）。"""
    factory = _Factory()
    publisher = _publisher(factory)
    await publisher.publish(_event())
    await publisher.publish(_event(event_id="evt-2"))
    assert len(factory.created) == 1
    assert len(factory.created[0].sent) == 2


async def test_publish_creates_producer_per_topic() -> None:
    """不同域对象各自一个 producer。"""
    factory = _Factory()
    publisher = _publisher(factory)
    await publisher.publish(_event("sys.user.created"))
    await publisher.publish(_event("wf.task.completed"))
    assert sorted(producer.topic for producer in factory.created) == ["bms.sys.user", "bms.wf.task"]


async def test_message_carries_envelope_and_attributes() -> None:
    """消息体可解码回原信封；tag 取动作段；keys 为幂等键；属性含类型。"""
    factory = _Factory()
    await _publisher(factory).publish(_event("wf.task.completed"))

    message = factory.created[0].sent[0]
    assert message.tag == "completed"
    assert message.keys == "evt-1"
    assert message.properties[ATTR_EVENT_TYPE] == "wf.task.completed"
    assert message.properties[ATTR_EVENT_ID] == "evt-1"
    decoded = decode_event(message.body or b"", message.properties)
    assert decoded.event_type == "wf.task.completed"
    assert decoded.event_id == "evt-1"
    assert decoded.tenant_id == "1234567890"
    assert dict(decoded.payload) == {"user_id": "u-1"}


async def test_send_failure_wrapped_as_publish_error() -> None:
    """发送异常包装为 `EventPublishError`（投递器据此退避 / 转死信）。"""
    factory = _Factory()
    factory.error = RuntimeError("broker down")
    with pytest.raises(EventPublishError, match="事件投递失败"):
        await _publisher(factory).publish(_event())


async def test_missing_endpoints_rejected() -> None:
    """端点未配置时明确报错（装配错误，不静默丢事件）。"""
    publisher = RocketMqEventPublisher(endpoints="", message_factory=_Message)
    with pytest.raises(EventPublishError, match="端点未配置"):
        await publisher.publish(_event())


async def test_transactional_delegates_to_publish() -> None:
    """事务消息接口基线委托普通发送（一致性由发件箱保证）。"""
    factory = _Factory()
    publisher = _publisher(factory)
    await publisher.publish_transactional(_event())
    assert len(factory.created[0].sent) == 1


async def test_close_shuts_down_all_producers() -> None:
    """关闭释放全部 producer，且幂等。"""
    factory = _Factory()
    publisher = _publisher(factory)
    await publisher.publish(_event("sys.user.created"))
    await publisher.publish(_event("wf.task.completed"))
    await publisher.aclose()
    await publisher.aclose()
    assert [producer.shutdown_calls for producer in factory.created] == [1, 1]


async def test_close_swallows_producer_shutdown_error() -> None:
    """单个 producer 关闭失败不阻断其它资源回收。"""

    class _BadProducer(_Producer):
        """关闭即抛错的 producer。"""

        def shutdown(self) -> None:
            """关闭失败。"""
            raise RuntimeError("shutdown boom")

    publisher = RocketMqEventPublisher(
        endpoints="127.0.0.1:8081",
        producer_factory=lambda topic: _BadProducer(topic),
        message_factory=_Message,
    )
    await publisher.publish(_event())
    await publisher.aclose()


async def test_event_type_is_wildcard() -> None:
    """发布侧无固定事件类型（端口要求 `event_type`，返回通配标识）。"""
    assert _publisher(_Factory()).event_type == "*"


async def test_publish_is_thread_safe_enough_for_batch() -> None:
    """多事件并发发布不丢消息（同步发送在线程池执行）。"""
    factory = _Factory()
    publisher = _publisher(factory)
    await asyncio.gather(*(publisher.publish(_event(event_id=f"evt-{index}")) for index in range(5)))
    assert len(factory.created[0].sent) == 5
