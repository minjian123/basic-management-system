"""任务变更信号护栏：发布成功/失败 / 订阅唤醒 / 订阅异常退出不抛错。"""

import asyncio
from typing import Any, cast

import pytest
from fakeredis.aioredis import FakeRedis
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from bms_core.core.exceptions import RedisUnavailableError
from bms_core.core.roots import BaseFrameworkObject
from bms_core.tasks.signal import DEFAULT_CHANGE_CHANNEL, TaskChangeSignal, close_pubsub

pytestmark = pytest.mark.kiwi_id(2371)


def _fake() -> Redis:
    """假 Redis 客户端。

    Returns:
        Redis: fakeredis 实例。
    """
    return cast("Redis", FakeRedis(decode_responses=False))


class _PublishBoom(BaseFrameworkObject):
    """发布必失败的客户端替身（模拟 Redis 抖动）。"""

    def __init__(self, exc: Exception) -> None:
        """初始化。

        Args:
            exc: 发布时抛出的异常。
        """
        self._exc = exc

    async def publish(self, channel: str, body: str) -> int:
        """发布即失败。

        Args:
            channel: 信道。
            body: 消息体。

        Raises:
            Exception: 构造时给定的异常。
        """
        _ = (channel, body)
        raise self._exc


class _FailingPubSub(BaseFrameworkObject):
    """订阅即失败的 pub/sub 替身。"""

    async def subscribe(self, channel: str) -> None:
        """订阅即失败。

        Args:
            channel: 信道。

        Raises:
            RedisUnavailableError: 固定抛出。
        """
        _ = channel
        raise RedisUnavailableError("redis down")

    async def get_message(self, **kwargs: object) -> Any:
        """不会被调用。

        Args:
            **kwargs: 忽略。

        Returns:
            Any: 恒 None。
        """
        _ = kwargs
        return None


class _FailingSubscribeClient(BaseFrameworkObject):
    """pubsub 工厂返回失败替身的客户端。"""

    def pubsub(self) -> _FailingPubSub:
        """返回订阅即失败的替身。

        Returns:
            _FailingPubSub: 替身。
        """
        return _FailingPubSub()


class _BrokenFactoryClient(BaseFrameworkObject):
    """pubsub 工厂直接失败的客户端替身。"""

    def pubsub(self) -> Any:
        """取订阅对象即失败。

        Raises:
            RedisUnavailableError: 固定抛出。
        """
        raise RedisUnavailableError("pubsub unavailable")


class _BrokenPubSub(BaseFrameworkObject):
    """订阅成功但随后断开的 pub/sub 替身（无 `aclose`，覆盖关闭兜底分支）。"""

    async def subscribe(self, channel: str) -> None:
        """订阅成功（立即返回）。

        Args:
            channel: 信道。
        """
        _ = channel

    async def get_message(self, **kwargs: object) -> Any:
        """读取即断开。

        Args:
            **kwargs: 忽略。

        Raises:
            RedisConnectionError: 固定抛出。
        """
        _ = kwargs
        raise RedisConnectionError("closed")


class _NopubsubClient(BaseFrameworkObject):
    """pubsub 工厂返回「无 `aclose` 替身」的客户端。"""

    def pubsub(self) -> _BrokenPubSub:
        """返回断开替身。

        Returns:
            _BrokenPubSub: 替身。
        """
        return _BrokenPubSub()


def test_channel_default_and_custom() -> None:
    """信道名可取缺省或自定义。"""
    assert TaskChangeSignal(client=_fake()).channel == DEFAULT_CHANGE_CHANNEL
    assert TaskChangeSignal(client=_fake(), channel="custom").channel == "custom"


async def test_publish_returns_true_on_success() -> None:
    """发布成功返回 True（投递链路由 wake_loop 用例端到端断言）。"""
    client = _fake()
    signal = TaskChangeSignal(client=client, channel="chan")
    assert await signal.publish() is True


@pytest.mark.parametrize("exc", [RedisUnavailableError("down"), RedisConnectionError("lost")])
async def test_publish_failure_is_swallowed(exc: Exception) -> None:
    """发布失败只记 warn 并返回 False（绝不因通知失败阻断业务）。"""
    signal = TaskChangeSignal(client=cast("Redis", _PublishBoom(exc)))
    assert await signal.publish() is False


async def test_publish_uses_shared_client_when_not_injected(monkeypatch: pytest.MonkeyPatch) -> None:
    """未注入客户端时取进程共享客户端（不可用则返回 False）。"""

    def _boom() -> Redis:
        raise RedisUnavailableError("no shared client")

    monkeypatch.setattr("bms_core.tasks.signal.shared_async_client", _boom)
    assert await TaskChangeSignal().publish() is False


async def test_wake_loop_sets_event_on_message() -> None:
    """收到信号即置位唤醒事件。"""
    client = _fake()
    signal = TaskChangeSignal(client=client, channel="wake")
    event = asyncio.Event()
    task = asyncio.create_task(signal.wake_loop(event))
    await asyncio.sleep(0.05)
    await TaskChangeSignal(client=client, channel="wake").publish()
    await asyncio.wait_for(event.wait(), timeout=3)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    assert event.is_set() is True


async def test_wake_loop_exits_on_subscribe_failure() -> None:
    """订阅失败（Redis 不可用）不抛错，直接退出（调度退化为轮询）。"""
    signal = TaskChangeSignal(client=cast("Redis", _FailingSubscribeClient()))
    event = asyncio.Event()
    await asyncio.wait_for(signal.wake_loop(event), timeout=3)
    assert event.is_set() is False


async def test_wake_loop_exits_on_connection_error_without_aclose() -> None:
    """订阅中途断开且 pubsub 无 aclose 时也只退出（关闭走兜底分支）。"""
    signal = TaskChangeSignal(client=cast("Redis", _NopubsubClient()))
    event = asyncio.Event()
    await asyncio.wait_for(signal.wake_loop(event), timeout=3)
    assert event.is_set() is False


async def test_wake_loop_propagates_cancellation() -> None:
    """取消要向上传播（长驻循环不得吞掉 CancelledError）。"""
    signal = TaskChangeSignal(client=_fake(), channel="cancel")
    task = asyncio.create_task(signal.wake_loop(asyncio.Event()))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_wake_loop_exits_when_pubsub_factory_fails() -> None:
    """pubsub 工厂本身失败（未拿到订阅对象）：只退出，关闭兜底走 `pubsub is None` 分支。"""
    signal = TaskChangeSignal(client=cast("Redis", _BrokenFactoryClient()))
    event = asyncio.Event()
    await asyncio.wait_for(signal.wake_loop(event), timeout=3)
    assert event.is_set() is False


async def test_close_pubsub_tolerates_object_without_aclose() -> None:
    """对象没有 `aclose` 时直接返回（不臆造关闭动作）。"""
    await close_pubsub(object())
