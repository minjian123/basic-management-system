"""03-6 用例：生产端（Kiwi 2510）。

覆盖要点：单条发布的请求体组装与回执解析；本地幂等表的三条路径（命中 / 过期 / 容量淘汰）；
`350033` 改投（含节点地址命中、未命中、改投用尽）；`350005` 退避（`Retry-After` 封顶）与重试用尽；
`350032` 结果未知默认不重试、开启 `retry_ambiguous` 后才重试；批量的成功 / 部分失败 / 快速失败。
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace

import pytest
from msgclient_support.rpc_retry import FakeClock

from bms_core.core.concurrent import ConcurrentStableFrozenDict, ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.msgclient.messaging import ClientAction, MsgClientError, OutgoingMessage
from bms_core.msgclient.retry import JitterMode, RetryPolicy

from ._support import ScriptedServer, build_config, build_producer, ok_body

pytestmark = pytest.mark.kiwi_id(2510)


def _message(**overrides: object) -> OutgoingMessage:
    """构造一条待发布消息。

    Args:
        overrides: 覆盖字段。

    Returns:
        OutgoingMessage: 消息。
    """
    base = OutgoingMessage(namespace="ns", topic="orders", payload=b"hello")
    return replace(base, **overrides)


@pytest.mark.asyncio
async def test_publish_success_body_and_ack() -> None:
    """发布成功：请求体含 base64 载荷与可选字段；回执按响应解析（含 offset / deliver_at）。"""
    server = ScriptedServer()
    server.push(
        "/msg/publish",
        body=ok_body(
            data={
                "message_id": "m1",
                "log_id": "l1",
                "topic": "orders",
                "partition": 2,
                "offset": 7,
                "deliver_at": "2026-11-16T00:00:00Z",
            }
        ),
    )
    producer, stats = build_producer(build_config(), server)
    ack = await producer.publish(
        _message(key="k", acks="all", idempotency_key="idem-1", trace_id="t", span_id="s", trace_flags="1")
    )

    decoded = json.loads(server.requests[0].read())
    assert decoded["payload"] == base64.b64encode(b"hello").decode("ascii")
    assert decoded["acks"] == "all"
    assert decoded["key"] == "k"
    assert decoded["headers"]["x-msg-idem-key"] == "idem-1"
    assert decoded["trace_id"] == "t"

    assert ack.message_id == "m1"
    assert ack.partition == 2
    assert ack.offset == 7
    assert ack.deliver_at == "2026-11-16T00:00:00Z"
    assert ack.deduplicated is False
    assert stats.snapshot().get("requests_total{op=publish}") == 1


@pytest.mark.asyncio
async def test_publish_ack_without_offset_and_deliver_at() -> None:
    """普通发布的回执：offset 缺失照实落 None，`topic` 回落入参。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(data={"message_id": "m1", "log_id": "l1", "partition": 1}))
    producer, _ = build_producer(build_config(), server)
    ack = await producer.publish(_message())
    assert ack.offset is None
    assert ack.deliver_at is None
    assert ack.topic == "orders"


@pytest.mark.asyncio
async def test_idempotency_hit_skips_request() -> None:
    """同幂等键第二次调用：不发请求、返回 `deduplicated=True`，并记一次命中。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(data={"message_id": "m1", "log_id": "l1", "partition": 0}))
    producer, stats = build_producer(build_config(), server)
    first = await producer.publish(_message(idempotency_key="k1"))
    second = await producer.publish(_message(idempotency_key="k1"))
    assert len(server.requests) == 1
    assert first.deduplicated is False
    assert second.deduplicated is True
    assert second.message_id == first.message_id
    assert stats.snapshot().get("dedup_hits_total") == 1


@pytest.mark.asyncio
async def test_idempotency_expires() -> None:
    """超过 TTL：条目过期后重新发请求。"""
    clock = FakeClock()
    server = ScriptedServer()
    for _ in range(2):
        server.push("/msg/publish", body=ok_body(data={"message_id": "m1", "log_id": "l1", "partition": 0}))
    producer, _ = build_producer(build_config(clock=clock, idempotency_ttl_ms=1_000), server)
    await producer.publish(_message(idempotency_key="k1"))
    clock.advance(1_001)
    await producer.publish(_message(idempotency_key="k1"))
    assert len(server.requests) == 2


@pytest.mark.asyncio
async def test_idempotency_capacity_evicts_oldest() -> None:
    """容量为 1：写入第二个键时按插入序淘汰第一个，旧键再发会重新请求。"""
    server = ScriptedServer()
    for _ in range(3):
        server.push("/msg/publish", body=ok_body(data={"message_id": "m1", "log_id": "l1", "partition": 0}))
    producer, _ = build_producer(build_config(idempotency_capacity=1), server)
    await producer.publish(_message(idempotency_key="k1"))
    await producer.publish(_message(idempotency_key="k2"))
    await producer.publish(_message(idempotency_key="k1"))
    assert len(server.requests) == 3


@pytest.mark.asyncio
async def test_publish_rejects_empty_namespace() -> None:
    """命名空间为空：发布前拦住（服务端会判 350010，早点说清）。"""
    producer, _ = build_producer(build_config(), ScriptedServer())
    with pytest.raises(ParamError, match="namespace 不能为空"):
        await producer.publish(_message(namespace=" "))


@pytest.mark.asyncio
async def test_publish_rejects_empty_topic() -> None:
    """主题为空：同样发布前拦住。"""
    producer, _ = build_producer(build_config(), ScriptedServer())
    with pytest.raises(ParamError, match="topic 不能为空"):
        await producer.publish(_message(topic=""))


@pytest.mark.asyncio
async def test_publish_rejects_bad_acks() -> None:
    """`acks` 不在闭集：拒绝（服务端只收 1 / all）。"""
    producer, _ = build_producer(build_config(), ScriptedServer())
    with pytest.raises(ParamError, match="acks 只能是 1 或 all"):
        await producer.publish(_message(acks="2"))


@pytest.mark.asyncio
async def test_publish_rejects_long_key() -> None:
    """分区键超长：拒绝（服务端上限 256）。"""
    producer, _ = build_producer(build_config(), ScriptedServer())
    with pytest.raises(ParamError, match="key 长度不得超过"):
        await producer.publish(_message(key="k" * 257))


@pytest.mark.asyncio
async def test_refresh_redirects_to_leader_address() -> None:
    """`350033` 且节点地址表命中：第二次请求直接打到新 leader 地址。"""
    clock = FakeClock()
    server = ScriptedServer()
    server.push(
        "/msg/publish",
        body=ok_body(350033, data={"leader": "msg-2", "epoch": 4, "reason": "not_leader"}),
    )
    server.push("/msg/publish", body=ok_body(data={"message_id": "m2", "log_id": "l2", "partition": 0}))
    config = build_config(
        clock=clock,
        endpoints=ConcurrentStableFrozenList(["http://msg-1:8000", "http://msg-2:8000"]),
        node_addresses=ConcurrentStableFrozenDict({"msg-2": "http://msg-9:8000"}),
    )
    producer, stats = build_producer(config, server)
    ack = await producer.publish(_message())

    assert ack.message_id == "m2"
    assert str(server.requests[0].url).startswith("http://msg-1:8000")
    assert str(server.requests[1].url).startswith("http://msg-9:8000")
    assert clock.sleeps == [200]
    assert stats.snapshot().get("redirects_total{reason=350033}") == 1


@pytest.mark.asyncio
async def test_refresh_without_leader_address_rotates_endpoint() -> None:
    """`350033` 但节点地址表没这个节点：换地址轮询（第二个地址）。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(350033, data={"leader": "msg-x"}))
    server.push("/msg/publish", body=ok_body(data={"message_id": "m2", "log_id": "l2", "partition": 0}))
    config = build_config(endpoints=ConcurrentStableFrozenList(["http://msg-1:8000", "http://msg-2:8000"]))
    producer, _ = build_producer(config, server)
    await producer.publish(_message())
    assert str(server.requests[1].url).startswith("http://msg-2:8000")


@pytest.mark.asyncio
async def test_refresh_with_empty_leader_keeps_rotation() -> None:
    """`350033` 但 `data.leader` 为空串：不改投目标，走轮询。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(350033, data={"leader": ""}))
    server.push("/msg/publish", body=ok_body(data={"message_id": "m2", "log_id": "l2", "partition": 0}))
    producer, _ = build_producer(build_config(), server)
    await producer.publish(_message())
    assert len(server.requests) == 2


@pytest.mark.asyncio
async def test_refresh_with_non_string_leader_keeps_rotation() -> None:
    """`350033` 但 `data.leader` 不是字符串：同样走轮询。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(350033, data={"leader": 123}))
    server.push("/msg/publish", body=ok_body(data={"message_id": "m2", "log_id": "l2", "partition": 0}))
    producer, _ = build_producer(build_config(), server)
    await producer.publish(_message())
    assert len(server.requests) == 2


@pytest.mark.asyncio
async def test_refresh_exhausted_raises_refresh() -> None:
    """改投次数用尽：抛出 `refresh` 类错误并记一次错误。"""
    server = ScriptedServer()
    for _ in range(2):
        server.push("/msg/publish", body=ok_body(350033, data={"leader": "msg-2"}))
    producer, stats = build_producer(build_config(max_redirects=1), server)
    with pytest.raises(MsgClientError) as captured:
        await producer.publish(_message())
    assert captured.value.action is ClientAction.REFRESH
    assert len(server.requests) == 2
    assert stats.snapshot().get("errors_total{code=350033}") == 1


@pytest.mark.asyncio
async def test_retry_then_success_uses_backoff() -> None:
    """限流一次后成功：按指数退避等待一次（100ms），并记一次重试。"""
    clock = FakeClock()
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(350005))
    server.push("/msg/publish", body=ok_body(data={"message_id": "m2", "log_id": "l2", "partition": 0}))
    producer, stats = build_producer(build_config(clock=clock), server)
    await producer.publish(_message())
    assert clock.sleeps == [100]
    assert stats.snapshot().get("retries_total{op=publish,reason=350005}") == 1


@pytest.mark.asyncio
async def test_retry_after_capped_by_policy() -> None:
    """`Retry-After` 优先，但受策略封顶（3000ms 压到 2000ms）。"""
    clock = FakeClock()
    server = ScriptedServer()
    server.push(
        "/msg/publish",
        body=ok_body(350005),
        headers=ConcurrentStableFrozenDict({"Retry-After": "3"}),
    )
    server.push("/msg/publish", body=ok_body(data={"message_id": "m2", "log_id": "l2", "partition": 0}))
    producer, _ = build_producer(build_config(clock=clock), server)
    await producer.publish(_message())
    assert clock.sleeps == [2_000]


@pytest.mark.asyncio
async def test_retry_exhausted_raises_retry() -> None:
    """重试次数用尽：抛出 `retry` 类错误。"""
    server = ScriptedServer()
    for _ in range(2):
        server.push("/msg/publish", body=ok_body(350005))
    producer, stats = build_producer(build_config(retry=_retry_policy(max_retries=1)), server)
    with pytest.raises(MsgClientError) as captured:
        await producer.publish(_message())
    assert captured.value.action is ClientAction.RETRY
    assert stats.snapshot().get("errors_total{code=350005}") == 1


@pytest.mark.asyncio
async def test_ambiguous_not_retried_by_default() -> None:
    """`350032` 提交超时：默认不重试，抛错并标结果未知。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(350032, data={"reason": "commit_timeout"}))
    producer, _ = build_producer(build_config(), server)
    with pytest.raises(MsgClientError) as captured:
        await producer.publish(_message())
    assert captured.value.outcome_unknown is True
    assert len(server.requests) == 1


@pytest.mark.asyncio
async def test_ambiguous_retried_when_enabled() -> None:
    """开启 `retry_ambiguous` 后：`350032` 会再发一次（仍保留结果未知标记）。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(350032))
    server.push("/msg/publish", body=ok_body(data={"message_id": "m2", "log_id": "l2", "partition": 0}))
    producer, _ = build_producer(build_config(retry_ambiguous=True), server)
    ack = await producer.publish(_message())
    assert ack.message_id == "m2"
    assert len(server.requests) == 2


@pytest.mark.asyncio
async def test_publish_many_all_success() -> None:
    """批量：两条都成功，结果按原始下标归位。"""
    server = ScriptedServer()
    for index in range(2):
        server.push("/msg/publish", body=ok_body(data={"message_id": f"m{index}", "log_id": "l", "partition": 0}))
    producer, _ = build_producer(build_config(publish_concurrency=1), server)
    result = await producer.publish_many(
        ConcurrentStableList([_message(), _message()]),
    )
    assert result.requested == 2
    assert [item.index for item in result.succeeded] == [0, 1]
    assert result.failed == ConcurrentStableFrozenList()


@pytest.mark.asyncio
async def test_publish_many_partial_failure() -> None:
    """批量：一条被拒（主题不存在）不影响另一条，失败项带下标与错误。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(350001))
    server.push("/msg/publish", body=ok_body(data={"message_id": "m1", "log_id": "l", "partition": 0}))
    producer, _ = build_producer(build_config(publish_concurrency=1), server)
    result = await producer.publish_many(ConcurrentStableList([_message(), _message()]))
    assert [item.index for item in result.succeeded] == [1]
    assert [item.index for item in result.failed] == [0]
    failed = result.failed[0]
    assert failed.error is not None and failed.error.code == 350001


@pytest.mark.asyncio
async def test_publish_many_fail_fast_cancels_unstarted() -> None:
    """快速失败：并发度为 1 时，首个失败后未开始的条目被标记为取消（未发请求）。"""
    server = ScriptedServer()
    server.push("/msg/publish", body=ok_body(350001))
    producer, _ = build_producer(build_config(publish_concurrency=1), server)
    result = await producer.publish_many(
        ConcurrentStableList([_message(), _message(), _message()]),
        fail_fast=True,
    )
    assert len(server.requests) == 1
    cancelled = [item.index for item in result.failed if item.cancelled]
    assert cancelled == [1, 2]


@pytest.mark.asyncio
async def test_publish_many_empty() -> None:
    """空批量：不起协程、不报错，`requested` 为 0。"""
    producer, _ = build_producer(build_config(), ScriptedServer())
    result = await producer.publish_many(ConcurrentStableList([]))
    assert result.requested == 0
    assert result.succeeded == ConcurrentStableFrozenList()


@pytest.mark.asyncio
async def test_producer_close() -> None:
    """关闭生产端即关闭传输层（幂等）。"""
    producer, _ = build_producer(build_config(), ScriptedServer())
    await producer.close()
    await producer.close()


def _retry_policy(*, max_retries: int) -> RetryPolicy:
    """构造指定重试次数的策略（无抖动，退避可精确断言）。

    Args:
        max_retries: 重试次数上限。

    Returns:
        RetryPolicy: 策略。
    """
    return RetryPolicy(max_retries=max_retries, base_ms=100, multiplier=2, cap_ms=2_000, jitter=JitterMode.NONE)
