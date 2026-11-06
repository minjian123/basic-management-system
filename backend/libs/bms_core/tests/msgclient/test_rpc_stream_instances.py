"""04-6 用例之四（Kiwi 2444）：流式选择实例、打开阶段健康反馈与租约生命周期。"""

from __future__ import annotations

import pytest
from msgclient_support.frame_errors import rpc_stream_frame
from msgclient_support.rpc_retry import FakeClock
from msgclient_support.rpc_transport import ScriptedRpcTransport

from bms_core.core.concurrent import ConcurrentStableFrozenList
from bms_core.msgclient.frame import decode_frame
from bms_core.msgclient.instances import (
    InstancePolicy,
    InstanceSelector,
    InstanceSnapshot,
    InstanceStrategy,
    StaticInstanceSelector,
)
from bms_core.msgclient.rpc import InstanceUnavailableError, RpcCallError, RpcClient
from bms_core.msgclient.transport import (
    PHASE_CONNECT,
    PHASE_READ_BODY,
    RpcHttpRequest,
    RpcTransportClosedError,
    RpcTransportTimeoutError,
)
from bms_core.msgclient.values import RpcReply

pytestmark = pytest.mark.kiwi_id(2444)

A = "http://a:8000"
"""实例 A。"""

B = "http://b:8000"
"""实例 B。"""

SERVICE = "demo"
"""服务标识。"""

METHOD = "ticker"
"""流式方法名。"""


def _frame(request: RpcHttpRequest, *, end: bool = True) -> bytes:
    """按请求的 `request_id` 编一帧流结果。

    Args:
        request: 传输层请求（取 `request_id`）。
        end: 是否末帧。

    Returns:
        bytes: 帧字节。
    """
    request_id = str(decode_frame(request.body).header["request_id"])
    return rpc_stream_frame(
        request_id=request_id,
        service=SERVICE,
        method=METHOD,
        reply=RpcReply(payload=b"ok"),
        seq=0,
        used_ms=0,
        remaining_ms=30_000,
        end_of_stream=end,
    )


def _client(transport: ScriptedRpcTransport, *, clock: FakeClock) -> tuple[RpcClient, StaticInstanceSelector]:
    """构造被测客户端与选择器。

    Args:
        transport: 传输替身。
        clock: 假时钟。

    Returns:
        tuple: 客户端与选择器。
    """
    selector = StaticInstanceSelector([A, B], clock=clock)
    return RpcClient(selector, transport=transport, clock=clock), selector


async def test_stream_selects_instance_on_open_not_on_construct() -> None:
    """构造句柄不发请求；进入上下文才选实例并打开。"""
    clock = FakeClock()
    transport = ScriptedRpcTransport(stream_chunks=lambda request: (_frame(request),))
    client, selector = _client(transport, clock=clock)
    try:
        handle = client.stream(SERVICE, METHOD)
        assert transport.open_requests == []
        async with handle as replies:
            assert transport.open_requests[0].origin == A
            items = [reply async for reply in replies]
    finally:
        await client.aclose()

    assert [item.payload for item in items] == [b"ok"]
    assert selector.snapshot("static").entries[0].inflight == 0


async def test_stream_open_failure_feedback_and_no_retry() -> None:
    """打开失败：记实例失败、归还租约、直接上抛（流式不进重试层）。"""
    clock = FakeClock()
    transport = ScriptedRpcTransport(open_error=RpcTransportClosedError("connect failed", phase=PHASE_CONNECT))
    client, selector = _client(transport, clock=clock)
    try:
        with pytest.raises(RpcCallError):
            async with client.stream(SERVICE, METHOD):
                pass
    finally:
        await client.aclose()

    entry = selector.snapshot("static").entries[0]
    assert entry.origin == A
    assert entry.failures == 1
    assert entry.inflight == 0
    assert len(transport.open_requests) == 1


async def test_stream_read_error_does_not_evict_instance() -> None:
    """流中错误只影响本次调用，不把实例摘除（只反馈打开阶段）。"""
    clock = FakeClock()
    transport = ScriptedRpcTransport(
        stream_chunks=lambda request: (_frame(request, end=False),),
        stream_error=RpcTransportClosedError("read failed", phase=PHASE_READ_BODY),
    )
    client, selector = _client(transport, clock=clock)
    try:
        with pytest.raises(RpcCallError):
            async with client.stream(SERVICE, METHOD) as replies:
                async for _ in replies:
                    pass
    finally:
        await client.aclose()

    entry = selector.snapshot("static").entries[0]
    assert entry.failures == 0
    assert entry.evicted is False
    assert entry.inflight == 0


async def test_stream_aclose_releases_lease() -> None:
    """`aclose()` 释放租约（在途归零、幂等）。"""
    clock = FakeClock()
    transport = ScriptedRpcTransport(stream_chunks=lambda request: (_frame(request),))
    client, selector = _client(transport, clock=clock)
    try:
        handle = client.stream(SERVICE, METHOD)
        await handle.__aenter__()
        assert selector.snapshot("static").entries[0].inflight == 1
        await handle.aclose()
        await handle.aclose()
    finally:
        await client.aclose()

    assert selector.snapshot("static").entries[0].inflight == 0


async def test_stream_uses_least_inflight_policy() -> None:
    """流式与其他调用共享同一选择器策略（最少在途）。"""
    clock = FakeClock()
    transport = ScriptedRpcTransport(stream_chunks=lambda request: (_frame(request),))
    selector = StaticInstanceSelector(
        [A, B],
        policy=InstancePolicy(strategy=InstanceStrategy.LEAST_INFLIGHT),
        clock=clock,
    )
    client = RpcClient(selector, transport=transport, clock=clock)
    try:
        async with client.stream(SERVICE, METHOD) as replies:
            async for _ in replies:
                pass
    finally:
        await client.aclose()
    assert transport.open_requests[0].origin == A


class _EmptyProvider:
    """空来源替身。"""

    def resolve(self, service: str) -> InstanceSnapshot:
        """返回空快照。

        Args:
            service: 逻辑服务标识（未使用）。

        Returns:
            InstanceSnapshot: 空快照。
        """
        del service
        return InstanceSnapshot(
            pool_key="msg",
            addresses=ConcurrentStableFrozenList(),
            revision=0,
            fetched_at_ms=0,
        )


async def test_stream_empty_source_raises_unavailable() -> None:
    """无可用实例：打开阶段映射为 `InstanceUnavailableError`。"""
    clock = FakeClock()
    selector = InstanceSelector(_EmptyProvider(), clock=clock)
    client = RpcClient(selector, transport=ScriptedRpcTransport(), clock=clock)
    try:
        with pytest.raises(InstanceUnavailableError):
            async with client.stream(SERVICE, METHOD):
                pass
    finally:
        await client.aclose()


async def test_stream_open_timeout_releases_lease() -> None:
    """打开超时：记实例失败、归还租约，再抛 `RpcCallTimeoutError`。"""
    clock = FakeClock()
    transport = ScriptedRpcTransport(open_error=RpcTransportTimeoutError("timeout"))
    client, selector = _client(transport, clock=clock)
    try:
        with pytest.raises(RpcCallError):
            async with client.stream(SERVICE, METHOD):
                pass
    finally:
        await client.aclose()
    entry = selector.snapshot("static").entries[0]
    assert entry.failures == 1
    assert entry.inflight == 0


async def test_stream_open_unexpected_error_releases_lease() -> None:
    """打开阶段未预期异常：租约必须归还，异常原样上抛。"""
    clock = FakeClock()
    transport = ScriptedRpcTransport(open_error=RuntimeError("boom"))
    client, selector = _client(transport, clock=clock)
    try:
        with pytest.raises(RuntimeError):
            async with client.stream(SERVICE, METHOD):
                pass
    finally:
        await client.aclose()
    assert selector.snapshot("static").entries[0].inflight == 0


async def test_stream_aclose_before_open_is_noop() -> None:
    """从未打开的句柄 `aclose()` 幂等（不访问选择器、不泄漏）。"""
    clock = FakeClock()
    transport = ScriptedRpcTransport(stream_chunks=lambda request: (_frame(request),))
    client, selector = _client(transport, clock=clock)
    try:
        handle = client.stream(SERVICE, METHOD)
        await handle.aclose()
        await handle.aclose()
    finally:
        await client.aclose()
    assert len(selector.snapshot("static").entries) == 0
