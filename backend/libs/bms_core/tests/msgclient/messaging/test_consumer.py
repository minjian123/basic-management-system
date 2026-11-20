"""03-6 / 03-6-1 用例：消费端（Kiwi 2510；两条通道参数化各跑一遍）。

覆盖要点：加入组的分配解析（含字段缺失时的缺省）；拉取的消息解码（消息体 / 头 / 链路字段 / 可选整型）；
成员失效（`350014`）自动重新加入一次、第二次仍失败即上抛；确认与拒绝；心跳间隔取服务端值并有下限；
关闭幂等且「离开失败不影响退出」；心跳循环的三条退出路径。

**成员三端点（`join` / `heartbeat` / `leave`）只有 JSON 形态**：帧通道下这三条请求仍走 JSON
（`ApiRequest.frame_type is None`），所以本文件对它们的断言在两条通道上完全一致。
"""

from __future__ import annotations

import asyncio

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableList,
)
from bms_core.core.exceptions import ParamError
from bms_core.msgclient.messaging import (
    ClientAction,
    MessagingConfig,
    MsgClientError,
    ReceivedMessage,
    TransportChannel,
)
from bms_core.msgclient.retry import Clock

from ._support import ScriptedServer, build_config, build_consumer
from ._support import channel as channel  # 夹具出口（用例按名字注入）

pytestmark = pytest.mark.kiwi_id(2510)


class _HangClock:
    """睡眠即挂起的时钟：让心跳任务真的「等」，不会被 FakeClock 变成紧循环。"""

    def __init__(self) -> None:
        """初始化。"""
        self.sleeps: ConcurrentStableList[int] = ConcurrentStableList()

    def now_ms(self) -> int:
        """当前毫秒（恒 0，本文件不依赖时间）。

        Returns:
            int: 0。
        """
        return 0

    async def sleep_ms(self, ms: int) -> None:
        """记录并挂起（关闭时由 `Task.cancel()` 打断）。

        Args:
            ms: 毫秒。
        """
        self.sleeps.add(ms)
        await asyncio.sleep(3_600)


class _TickClock:
    """每次睡眠后回调一次的时钟（用于驱动心跳循环的三条退出路径）。"""

    def __init__(self, *, ticks: int, on_tick: object) -> None:
        """初始化。

        Args:
            ticks: 允许的睡眠次数（达到后不再调用回调）。
            on_tick: 每次睡眠后的回调（无参可调用）。
        """
        self._remaining = ticks
        self._on_tick = on_tick
        self.sleeps: ConcurrentStableList[int] = ConcurrentStableList()

    def now_ms(self) -> int:
        """当前毫秒（恒 0）。

        Returns:
            int: 0。
        """
        return 0

    async def sleep_ms(self, ms: int) -> None:
        """记录等待并按剩余次数触发回调。

        Args:
            ms: 毫秒。
        """
        self.sleeps.add(ms)
        if self._remaining > 0:
            self._remaining -= 1
            callback = self._on_tick
            assert callable(callback)
            callback()


def _config(channel: TransportChannel, *, clock: Clock | None = None, **overrides: object) -> MessagingConfig:
    """构造指定通道的配置。

    Args:
        channel: 通道。
        clock: 注入时钟（缺省用 fake）。
        overrides: 覆盖字段。

    Returns:
        MessagingConfig: 配置。
    """
    return build_config(channel=channel, clock=clock, **overrides)


def _assignment(partitions: object | None = None, *, interval_ms: int = 1_000) -> ConcurrentStableDict[str, object]:
    """构造加入组 / 心跳的响应数据。

    Args:
        partitions: 分配的分区号（None = 不给该字段，覆盖缺省分支）。
        interval_ms: 服务端要求的心跳间隔。

    Returns:
        ConcurrentStableDict[str, object]: 响应数据。
    """
    data: ConcurrentStableDict[str, object] = ConcurrentStableDict(
        {
            "group": "g1",
            "topic": "orders",
            "consumer_id": "c1",
            "generation": 2,
            "state": "stable",
            "member_count": 1,
            "heartbeat_interval_ms": interval_ms,
            "session_timeout_ms": 3_000,
        }
    )
    if partitions is not None:
        data.set("partitions", partitions)
    return data


@pytest.mark.asyncio
async def test_join_parses_assignment(channel: TransportChannel) -> None:
    """加入组：解析出分区、世代与心跳间隔；`heartbeat_delay_ms` 取服务端间隔（下限 1 秒）。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0, 1], interval_ms=1_000))
    consumer, stats = build_consumer(_config(channel, clock=_HangClock()), server)
    assignment = await consumer.join()

    assert list(assignment.partitions) == [0, 1]
    assert assignment.generation == 2
    assert assignment.member_count == 1
    assert consumer.heartbeat_delay_ms() == 1_000
    assert stats.snapshot().get("join_total") == 1
    assert server.request_paths() == ConcurrentStableFrozenList(["/api/v1/msg/join"])
    await consumer.close()


@pytest.mark.asyncio
async def test_join_defaults_when_fields_missing(channel: TransportChannel) -> None:
    """分配字段缺失：按缺省填（分区空、成员 0、心跳 10 秒、会话 30 秒）。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data={"generation": 1})
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    assignment = await consumer.join()

    assert list(assignment.partitions) == []
    assert assignment.member_count == 0
    assert assignment.heartbeat_interval_ms == 10_000
    assert assignment.session_timeout_ms == 30_000
    assert assignment.group == "g1"
    assert assignment.topic == "orders"
    assert assignment.consumer_id == "c1"
    await consumer.close()


@pytest.mark.asyncio
async def test_join_twice_keeps_single_heartbeat_task(channel: TransportChannel) -> None:
    """重复加入：不重复起心跳任务（否则每 join 一次多一个定时器）。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/join", data=_assignment([0]))
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    first = consumer._heartbeat_task  # pyright: ignore[reportPrivateUsage]
    await consumer.join()
    second = consumer._heartbeat_task  # pyright: ignore[reportPrivateUsage]
    assert first is second
    await consumer.close()


@pytest.mark.asyncio
async def test_poll_requires_join(channel: TransportChannel) -> None:
    """未加入组就拉取：参数错误（不是产品码——这是编程错误）。"""
    consumer, _ = build_consumer(_config(channel), ScriptedServer())
    with pytest.raises(ParamError, match="尚未 join"):
        await consumer.poll()


@pytest.mark.asyncio
async def test_poll_rejects_bad_limits(channel: TransportChannel) -> None:
    """条数与等待上限越界：分别拒绝（与服务端 1~100 / 0~60000 同口径）。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    with pytest.raises(ParamError, match="max_messages"):
        await consumer.poll(max_messages=0)
    with pytest.raises(ParamError, match="max_wait_ms"):
        await consumer.poll(max_wait_ms=60_001)
    await consumer.close()


@pytest.mark.asyncio
async def test_poll_decodes_messages(channel: TransportChannel) -> None:
    """拉取：消息体逐字节还原、头原样、链路字段与可选整型按存在与否取值；分区按分配轮转。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0, 1]))
    server.push(
        "/api/v1/msg/consume",
        data={
            "messages": [
                {
                    "message_id": "m1",
                    "topic": "orders",
                    "partition": 1,
                    "offset": 5,
                    "key": "k1",
                    "headers": {"h": "v"},
                    "delivery_count": 2,
                    "published_at": "2026-11-16T00:00:00Z",
                    "content_type": "application/json",
                    "compression": "none",
                    "uncompressed_len": 4,
                    "trace_id": "t",
                    "span_id": "s",
                    "trace_flags": "1",
                }
            ],
            "paused": True,
            "inflight_messages": 1,
            "inflight_bytes": 4,
        },
        payloads=ConcurrentStableFrozenList([b"body"]),
    )
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    result = await consumer.poll(max_messages=10, max_wait_ms=0)

    assert result.partition == 0
    assert result.paused is True
    assert result.inflight_messages == 1
    assert result.inflight_bytes == 4
    message = result.messages[0]
    assert message.payload == b"body"
    assert message.headers.get("h") == "v"
    assert message.offset == 5
    assert message.delivery_count == 2
    assert message.trace_id == "t"
    assert message.uncompressed_len == 4
    assert message.key == "k1"
    await consumer.close()


@pytest.mark.asyncio
async def test_poll_splits_multiple_payloads(channel: TransportChannel) -> None:
    """一批多条、消息体长度不同：逐条按边界还原（帧通道按 `length` 切片、JSON 通道各自 base64）。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push(
        "/api/v1/msg/consume",
        data={
            "messages": [
                {"message_id": "m1", "topic": "orders", "partition": 0, "offset": 0},
                {"message_id": "m2", "topic": "orders", "partition": 0, "offset": 1},
            ]
        },
        payloads=ConcurrentStableFrozenList([b"abc", b"de"]),
    )
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    result = await consumer.poll()
    assert [message.payload for message in result.messages] == [b"abc", b"de"]
    await consumer.close()


@pytest.mark.asyncio
async def test_poll_message_edges(channel: TransportChannel) -> None:
    """消息字段缺失 / 形态不符：载荷空、键空、头非对象、可选整型非整数都按缺省落。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([3]))
    server.push(
        "/api/v1/msg/consume",
        data={
            "messages": [
                {
                    "message_id": "m1",
                    "partition": 3,
                    "offset": 0,
                    "headers": "not-a-map",
                    "uncompressed_len": "x",
                }
            ]
        },
    )
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    result = await consumer.poll()
    message = result.messages[0]
    assert message.payload == b""
    assert message.key is None
    assert message.headers == ConcurrentStableFrozenDict[str, str]()
    assert message.uncompressed_len is None
    assert message.trace_id is None
    assert result.paused is False
    await consumer.close()


@pytest.mark.asyncio
async def test_poll_rejoins_once_on_member_invalid(channel: TransportChannel) -> None:
    """`350014`：自动重新加入一次并按新分配继续拉取。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/consume", code=350014)
    server.push("/api/v1/msg/join", data=_assignment([5]))
    server.push("/api/v1/msg/consume", data={"messages": []})
    consumer, stats = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    result = await consumer.poll()

    assert result.partition == 5
    assert stats.snapshot().get("rejoin_total") == 1
    await consumer.close()


@pytest.mark.asyncio
async def test_poll_empty_assignment_after_rejoin_returns_empty_batch(channel: TransportChannel) -> None:
    """重平衡窗口：重新加入后分配暂时为空 → 返回空批，不得因取模零除崩掉单元。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/consume", code=350014)
    server.push("/api/v1/msg/join", data=_assignment([]))
    consumer, stats = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()

    result = await consumer.poll()

    assert list(result.messages) == []
    assert result.paused is False
    assert stats.snapshot().get("rejoin_total") == 1
    await consumer.close()


@pytest.mark.asyncio
async def test_poll_raises_after_second_refresh(channel: TransportChannel) -> None:
    """重新加入后仍 `350014`：不再重试，直接上抛 `refresh`。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/consume", code=350014)
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/consume", code=350014)
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    with pytest.raises(MsgClientError) as captured:
        await consumer.poll()
    assert captured.value.action is ClientAction.REFRESH
    await consumer.close()


@pytest.mark.asyncio
async def test_ack_and_ack_many(channel: TransportChannel) -> None:
    """确认：单条取回已提交位点；批量按顺序确认并以最后一条为准；空批次返回 0。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/ack", data={"committed_offset": 6})
    server.push("/api/v1/msg/ack", data={"committed_offset": 8})
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()

    message = ReceivedMessage(message_id="m1", topic="orders", partition=0, offset=5)
    assert (await consumer.ack(message)).committed_offset == 6
    second = ReceivedMessage(message_id="m2", topic="orders", partition=0, offset=7)
    assert (await consumer.ack_many(ConcurrentStableList([second]))).committed_offset == 8
    assert (await consumer.ack_many(ConcurrentStableList([]))).committed_offset == 0
    await consumer.close()


@pytest.mark.asyncio
async def test_nack_and_reason_validation(channel: TransportChannel) -> None:
    """拒绝：给出原因即受理并前进位点；原因不在闭集则参数错误。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/nack", data={"committed_offset": 9})
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    message = ReceivedMessage(message_id="m1", topic="orders", partition=0, offset=8)
    assert (await consumer.nack(message, reason="schema_invalid")).committed_offset == 9
    with pytest.raises(ParamError, match="reason 只能是"):
        await consumer.nack(message, reason="other")
    await consumer.close()


@pytest.mark.asyncio
async def test_heartbeat_updates_assignment(channel: TransportChannel) -> None:
    """心跳：把返回的分配写回，世代与分区跟着变。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/heartbeat", data=_assignment([2, 3]))
    consumer, stats = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    assignment = await consumer.heartbeat()
    assert list(assignment.partitions) == [2, 3]
    assert stats.snapshot().get("heartbeat_total") == 1
    await consumer.close()


@pytest.mark.asyncio
async def test_heartbeat_delay_clamped_to_one_second(channel: TransportChannel) -> None:
    """服务端给的心跳间隔很小：客户端不低于 1 秒（避免打成紧循环）。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0], interval_ms=100))
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    assert consumer.heartbeat_delay_ms() == 1_000
    await consumer.close()


def test_heartbeat_delay_defaults_without_join(channel: TransportChannel) -> None:
    """未加入组：心跳间隔按 10 秒缺省算（6000ms）。"""
    consumer, _ = build_consumer(_config(channel), ScriptedServer())
    assert consumer.heartbeat_delay_ms() == 6_000


@pytest.mark.asyncio
async def test_close_swallows_leave_failure_and_is_idempotent(channel: TransportChannel) -> None:
    """关闭：离开组失败只记计数不抛；重复关闭直接返回。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/leave", code=350013)
    consumer, stats = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    await consumer.close()
    assert stats.snapshot().get("leave_failed_total{code=350013}") == 1
    await consumer.close()


@pytest.mark.asyncio
async def test_operations_reject_after_close(channel: TransportChannel) -> None:
    """关闭后再操作：参数错误（要求新建实例，避免复用半关闭状态）。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    server.push("/api/v1/msg/leave", code=0)
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.join()
    await consumer.close()
    with pytest.raises(ParamError, match="客户端已关闭"):
        await consumer.join()
    with pytest.raises(ParamError, match="客户端已关闭"):
        await consumer.poll()
    message = ReceivedMessage(message_id="m1", topic="orders", partition=0, offset=0)
    with pytest.raises(ParamError, match="客户端已关闭"):
        await consumer.ack(message)


@pytest.mark.asyncio
async def test_heartbeat_loop_returns_when_already_closed(channel: TransportChannel) -> None:
    """心跳循环：已关闭时一次都不进循环。"""
    consumer, _ = build_consumer(
        _config(channel, clock=_TickClock(ticks=0, on_tick=lambda: None)),
        ScriptedServer(),
    )
    consumer._closed = True  # pyright: ignore[reportPrivateUsage]
    await consumer._heartbeat_loop()  # pyright: ignore[reportPrivateUsage]


@pytest.mark.asyncio
async def test_heartbeat_loop_exits_when_closed_during_sleep(channel: TransportChannel) -> None:
    """心跳循环：睡眠期间被关闭则直接退出，不再发心跳。"""
    server = ScriptedServer()
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    clock = _TickClock(ticks=1, on_tick=lambda: setattr(consumer, "_closed", True))
    consumer.config = _config(channel, clock=clock)

    await consumer._heartbeat_loop()  # pyright: ignore[reportPrivateUsage]

    assert len(server.requests) == 0


@pytest.mark.asyncio
async def test_heartbeat_loop_records_failure_and_continues(channel: TransportChannel) -> None:
    """心跳失败：记一次失败计数后继续下一轮（成员失效由拉取路径的重连处置）。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/heartbeat", code=350013)
    consumer, stats = build_consumer(_config(channel), server)
    ticks = [0]

    def _on_tick() -> None:
        """第 2 次睡眠时关闭（第 1 次留给失败分支）。"""
        ticks[0] += 1
        if ticks[0] >= 2:
            consumer._closed = True  # pyright: ignore[reportPrivateUsage]

    consumer.config = _config(channel, clock=_TickClock(ticks=2, on_tick=_on_tick))
    await consumer._heartbeat_loop()  # pyright: ignore[reportPrivateUsage]

    assert stats.snapshot().get("heartbeat_failed_total{code=350013}") == 1


def test_assignment_and_poll_result_defaults_are_empty() -> None:
    """分配与拉取结果的空缺省：未给分区 / 消息时是空列表（调用方不必判 None）。"""
    from bms_core.msgclient.messaging import Assignment, PollResult

    assignment = Assignment(group="g1", topic="orders", consumer_id="c1")
    assert list(assignment.partitions) == []
    assert assignment.generation == 0
    assert assignment.state == ""
    assert PollResult().messages == ConcurrentStableFrozenList()


@pytest.mark.asyncio
async def test_assignment_property_before_and_after_join(channel: TransportChannel) -> None:
    """`assignment` 属性：未加入为 None，加入后是当前分配。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/join", data=_assignment([0]))
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    assert consumer.assignment is None
    await consumer.join()
    assert consumer.assignment is not None
    await consumer.close()


@pytest.mark.asyncio
async def test_close_without_join_skips_heartbeat_cancel(channel: TransportChannel) -> None:
    """未加入组就关闭：没有心跳任务可取消，仍照常离开组并关传输层。"""
    server = ScriptedServer()
    server.push("/api/v1/msg/leave", code=0)
    consumer, _ = build_consumer(_config(channel, clock=_HangClock()), server)
    await consumer.close()
    assert server.request_paths() == ConcurrentStableFrozenList(["/api/v1/msg/leave"])
