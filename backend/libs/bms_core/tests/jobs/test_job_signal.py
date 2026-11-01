"""作业唤醒信号用例：发布成功 / 失败降级、订阅唤醒、关闭尽力而为。"""

from __future__ import annotations

import asyncio
from typing import Any, cast

import pytest
from redis.exceptions import RedisError

from bms_core.core.concurrent import ConcurrentStableList
from bms_core.jobs import signal as job_signal
from bms_core.jobs.signal import DEFAULT_JOB_CHANGE_CHANNEL, JobChangeSignal, close_pubsub

pytestmark = pytest.mark.kiwi_id(2388)


class _FakeRedis:
    """Redis 替身：记录发布并可按需抛错。"""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.published: ConcurrentStableList[tuple[str, str]] = ConcurrentStableList()

    async def publish(self, channel: str, body: str) -> int:
        """记录发布（或抛预设错误）。"""
        if self.error is not None:
            raise self.error
        self.published.append((channel, body))
        return 1

    def pubsub(self) -> Any:
        """返回订阅替身（本类只用于发布分支）。"""
        raise AssertionError("不应进入订阅分支")


class _FakePubSub:
    """订阅替身：按预设脚本返回消息，脚本耗尽后抛 RedisError 退出。"""

    def __init__(self, script: ConcurrentStableList[object]) -> None:
        self.script = script
        self.subscribed: ConcurrentStableList[str] = ConcurrentStableList()
        self.closed = False

    async def subscribe(self, channel: str) -> None:
        """记录订阅信道。"""
        self.subscribed.append(channel)

    async def get_message(self, *, ignore_subscribe_messages: bool, timeout: float) -> object:
        """取预设脚本（耗尽即抛 RedisError）。"""
        del ignore_subscribe_messages, timeout
        if not self.script:
            raise RedisError("gone")
        item = self.script.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item

    async def aclose(self) -> None:
        """标记关闭。"""
        self.closed = True


def test_channel_defaults_and_override() -> None:
    """信道名：缺省全局信道，可显式覆盖。"""
    assert JobChangeSignal().channel == DEFAULT_JOB_CHANGE_CHANNEL
    assert JobChangeSignal(channel="t").channel == "t"


def test_redis_uses_shared_client_when_not_injected(monkeypatch: pytest.MonkeyPatch) -> None:
    """未注入客户端：取进程共享客户端。"""
    sentinel = object()
    monkeypatch.setattr(job_signal, "shared_async_client", lambda: sentinel)
    assert JobChangeSignal()._redis() is sentinel  # pyright: ignore[reportPrivateUsage]


async def test_publish_success_and_failure() -> None:
    """发布：成功返回 True；Redis 异常只记 warn 并返回 False（不影响写库）。"""
    client = _FakeRedis()
    assert await JobChangeSignal(client=cast("Any", client), channel="t").publish() is True
    assert client.published == [("t", "1")]

    failing = _FakeRedis(error=RedisError("down"))
    assert await JobChangeSignal(client=cast("Any", failing), channel="t").publish() is False


async def test_wake_loop_sets_event_and_closes_pubsub(monkeypatch: pytest.MonkeyPatch) -> None:
    """订阅：收到 message 即唤醒；脚本耗尽后按 Redis 异常退出并关闭订阅。"""
    pubsub = _FakePubSub(ConcurrentStableList([{"type": "subscribe"}, {"type": "message"}, RedisError("gone")]))

    class _Client(_FakeRedis):
        def pubsub(self) -> Any:
            return pubsub

    signal = JobChangeSignal(client=cast("Any", _Client()), channel="t")
    event = asyncio.Event()
    await asyncio.wait_for(signal.wake_loop(event), timeout=2)
    assert event.is_set()
    assert pubsub.subscribed == ["t"]
    assert pubsub.closed is True


async def test_wake_loop_reraises_cancel() -> None:
    """订阅：取消异常原样上抛（不吞）。"""
    pubsub = _FakePubSub(ConcurrentStableList([asyncio.CancelledError()]))

    class _Client(_FakeRedis):
        def pubsub(self) -> Any:
            return pubsub

    signal = JobChangeSignal(client=cast("Any", _Client()), channel="t")
    with pytest.raises(asyncio.CancelledError):
        await signal.wake_loop(asyncio.Event())
    assert pubsub.closed is True


async def test_wake_loop_skips_close_when_pubsub_missing() -> None:
    """订阅：客户端取 pubsub 失败时 pubsub 未赋值，finally 跳过关闭。"""

    class _Client(_FakeRedis):
        def pubsub(self) -> Any:
            raise RedisError("no pubsub")

    signal = JobChangeSignal(client=cast("Any", _Client()), channel="t")
    await signal.wake_loop(asyncio.Event())


async def test_close_pubsub_branches() -> None:
    """关闭：无 `aclose` 直接返回；同步关闭不 await；异步关闭 await。"""
    await close_pubsub(object())

    class _Sync:
        def __init__(self) -> None:
            self.called = False

        def aclose(self) -> None:
            self.called = True

    sync = _Sync()
    await close_pubsub(sync)
    assert sync.called is True

    class _Async:
        def __init__(self) -> None:
            self.called = False

        async def aclose(self) -> None:
            self.called = True

    asynchronous = _Async()
    await close_pubsub(asynchronous)
    assert asynchronous.called is True
