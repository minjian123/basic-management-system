"""04-6 用例之三（Kiwi 2444）：一元换实例判定、预算/幂等/熔断联动与不可用映射。"""

from __future__ import annotations

import pytest
from msgclient_support.rpc_retry import (
    FakeClock,
    error_response,
    result_response,
    scripted,
)
from msgclient_support.rpc_transport import ScriptedRpcTransport

from bms_core.circuit.base import CircuitState
from bms_core.core.concurrent import ConcurrentStableFrozenList, ConcurrentStableList
from bms_core.msgclient.circuit import InProcessCircuitBreaker
from bms_core.msgclient.instances import (
    InstanceOutcome,
    InstancePolicy,
    InstanceSelector,
    InstanceSnapshot,
    InstanceStrategy,
    InstanceUnavailable,
    StaticInstanceSelector,
    selector_for,
)
from bms_core.msgclient.retry import CircuitPolicy, RetryPolicy, RpcRetryBlockedError
from bms_core.msgclient.rpc import InstanceUnavailableError, RpcCallError, RpcClient
from bms_core.msgclient.transport import (
    PHASE_CONNECT,
    PHASE_RESET,
    RpcHttpRequest,
    RpcHttpResponse,
    RpcTransportClosedError,
    RpcTransportTimeoutError,
)

pytestmark = pytest.mark.kiwi_id(2444)

A = "http://a:8000"
"""实例 A。"""

B = "http://b:8000"
"""实例 B。"""


class _EmptyProvider:
    """空来源替身（目录不可用）。"""

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


def _client(
    selector: InstanceSelector,
    transport: object,
    *,
    clock: FakeClock | None = None,
    retry_policy: RetryPolicy | None = None,
    circuit: object | None = None,
) -> RpcClient:
    """构造被测客户端。

    Args:
        selector: 实例选择器。
        transport: 传输替身。
        clock: 假时钟。
        retry_policy: 重试策略。
        circuit: 熔断器。

    Returns:
        RpcClient: 客户端。
    """
    return RpcClient(
        selector,
        transport=transport,  # type: ignore[arg-type]
        clock=clock,
        retry_policy=retry_policy,
        circuit=circuit,  # type: ignore[arg-type]
    )


async def _routing(
    seen: ConcurrentStableList[str],
    *,
    fail_first: RpcHttpResponse | BaseException | None = None,
    fail_origin: str = A,
    always_fail: bool = False,
) -> ScriptedRpcTransport:
    """构造按 origin 路由的传输：`fail_origin` 第一次失败，其余成功。

    Args:
        seen: 记录每次请求的 origin。
        fail_first: 第一次请求 `fail_origin` 时返回 / 抛出的东西。
        fail_origin: 失败实例。
        always_fail: `fail_origin` 是否每次都失败（结果未知用例用）。

    Returns:
        ScriptedRpcTransport: 传输替身。
    """
    failed = False

    async def handler(request: RpcHttpRequest) -> RpcHttpResponse:
        nonlocal failed
        seen.append(request.origin)
        if request.origin == fail_origin and (always_fail or not failed):
            failed = True
            if isinstance(fail_first, BaseException):
                raise fail_first
            return fail_first if fail_first is not None else result_response()
        return result_response()

    return ScriptedRpcTransport(handler=handler)


# ---------------------------------------------------------------------------
# 1. 确定未执行 → 换实例
# ---------------------------------------------------------------------------


async def test_connect_failure_swaps_to_healthy_instance() -> None:
    """连接建立失败（phase=connect）：换到健康实例并成功。"""
    clock = FakeClock()
    selector = StaticInstanceSelector([A, B], clock=clock)
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(
        seen,
        fail_first=RpcTransportClosedError("connect failed", phase=PHASE_CONNECT),
    )
    client = _client(selector, transport, clock=clock)
    try:
        reply = await client.call("demo", "echo", b"x", idempotent=True)
    finally:
        await client.aclose()

    assert reply.payload == b"ok"
    assert list(seen) == [A, B]
    view = selector.snapshot("static")
    entry_a = next(entry for entry in view.entries if entry.origin == A)
    assert entry_a.failures == 1
    assert entry_a.evicted is False


async def test_transient_error_frame_swaps_instance() -> None:
    """服务端明确瞬时错误（350005 / transient / retryable）：换实例。"""
    clock = FakeClock()
    selector = StaticInstanceSelector([A, B], clock=clock)
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(seen, fail_first=error_response(350005))
    client = _client(selector, transport, clock=clock)
    try:
        reply = await client.call("demo", "echo", b"x", idempotent=True)
    finally:
        await client.aclose()

    assert reply.payload == b"ok"
    assert list(seen) == [A, B]


# ---------------------------------------------------------------------------
# 2. 结果未知 → 同实例
# ---------------------------------------------------------------------------


async def test_reset_does_not_swap_instance() -> None:
    """读体 / 等头中断（phase=reset）：可能已执行，不换实例。"""
    clock = FakeClock()
    selector = StaticInstanceSelector([A, B], clock=clock)
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(
        seen,
        fail_first=RpcTransportClosedError("reset", phase=PHASE_RESET),
        always_fail=True,
    )
    client = _client(selector, transport, clock=clock)
    try:
        with pytest.raises(RpcCallError):
            await client.call("demo", "echo", b"x", idempotent=True)
    finally:
        await client.aclose()

    assert seen[0] == A
    assert all(origin == A for origin in seen)


async def test_timeout_does_not_swap_instance() -> None:
    """本地超时：结果未知，不换实例。"""
    clock = FakeClock()
    selector = StaticInstanceSelector([A, B], clock=clock)
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(seen, fail_first=RpcTransportTimeoutError("timeout"), always_fail=True)
    client = _client(selector, transport, clock=clock)
    try:
        with pytest.raises(RpcCallError):
            await client.call("demo", "echo", b"x", idempotent=True)
    finally:
        await client.aclose()

    assert all(origin == A for origin in seen)


async def test_unknown_error_frame_does_not_swap_instance() -> None:
    """`350004` / category=unknown：可能已执行，同实例重试。"""
    clock = FakeClock()
    selector = StaticInstanceSelector([A, B], clock=clock)
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(
        seen,
        fail_first=error_response(350004, category="unknown", retryable=False),
        always_fail=True,
    )
    client = _client(selector, transport, clock=clock)
    try:
        with pytest.raises(RpcCallError):
            await client.call("demo", "echo", b"x", idempotent=True)
    finally:
        await client.aclose()

    assert all(origin == A for origin in seen)


async def test_non_idempotent_without_key_is_blocked() -> None:
    """非幂等且无键：04-4 阻止重试，零换实例。"""
    clock = FakeClock()
    selector = StaticInstanceSelector([A, B], clock=clock)
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(
        seen,
        fail_first=RpcTransportClosedError("connect failed", phase=PHASE_CONNECT),
    )
    client = _client(
        selector,
        transport,
        clock=clock,
        retry_policy=RetryPolicy(auto_idempotency_key=False),
    )
    try:
        with pytest.raises(RpcRetryBlockedError):
            await client.call("demo", "echo", b"x")
    finally:
        await client.aclose()

    assert list(seen) == [A]


async def test_single_instance_falls_back_to_same_origin() -> None:
    """单实例：排除后无可选实例时允许回退同一实例，不直接判死。"""
    clock = FakeClock()
    selector = StaticInstanceSelector([A], clock=clock)
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(
        seen,
        fail_first=RpcTransportClosedError("connect failed", phase=PHASE_CONNECT),
    )
    client = _client(selector, transport, clock=clock)
    try:
        reply = await client.call("demo", "echo", b"x", idempotent=True)
    finally:
        await client.aclose()

    assert reply.payload == b"ok"
    assert list(seen) == [A, A]


# ---------------------------------------------------------------------------
# 3. 不可用映射与熔断联动
# ---------------------------------------------------------------------------


async def test_empty_snapshot_maps_to_instance_unavailable() -> None:
    """目录为空：抛 `InstanceUnavailableError`（`RpcCallError` 子类，不新增产品码）。"""
    selector = selector_for(_EmptyProvider(), clock=FakeClock())
    client = _client(selector, scripted())
    try:
        with pytest.raises(InstanceUnavailableError) as caught:
            await client.call("demo", "echo")
    finally:
        await client.aclose()

    assert caught.value.retryable is True
    assert caught.value.reason == "empty_snapshot"


async def test_instance_unavailable_is_rpc_call_error() -> None:
    """`InstanceUnavailableError` 可被适配层按 `RpcCallError` 捕获。"""
    from bms_core.msgclient.rpc import RpcCallError

    selector = selector_for(_EmptyProvider(), clock=FakeClock())
    client = _client(selector, scripted())
    try:
        with pytest.raises(RpcCallError):
            await client.call("demo", "echo")
    finally:
        await client.aclose()


async def test_circuit_still_counts_instance_failures() -> None:
    """实例失败与依赖熔断独立计数：一次失败仍计熔断。"""
    clock = FakeClock()
    breaker = InProcessCircuitBreaker(policy=CircuitPolicy(failure_threshold=1), clock=clock)
    selector = StaticInstanceSelector([A], clock=clock)
    transport = scripted(RpcTransportClosedError("connect failed", phase=PHASE_CONNECT))
    client = _client(
        selector,
        transport,
        clock=clock,
        retry_policy=RetryPolicy(max_retries=0),
        circuit=breaker,
    )
    try:
        with pytest.raises(RpcCallError):
            await client.call("demo", "echo", b"x", idempotent=True)
    finally:
        await client.aclose()

    assert await breaker.state("service:demo") is CircuitState.OPEN


async def test_least_inflight_is_used_by_client() -> None:
    """客户端按注入策略选实例（最少在途；平局回到 A）。"""
    clock = FakeClock()
    selector = StaticInstanceSelector(
        [A, B],
        policy=InstancePolicy(strategy=InstanceStrategy.LEAST_INFLIGHT),
        clock=clock,
    )
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(seen)
    client = _client(selector, transport, clock=clock)
    try:
        await client.call("demo", "echo", idempotent=True)
    finally:
        await client.aclose()
    assert list(seen) == [A]


async def test_unavailable_does_not_leak_inflight() -> None:
    """不可用时不 acquire，在途计数保持 0。"""
    selector = selector_for(_EmptyProvider(), clock=FakeClock())
    client = _client(selector, scripted())
    try:
        with pytest.raises(InstanceUnavailableError):
            await client.call("demo", "echo")
    finally:
        await client.aclose()
    assert len(selector.snapshot("msg").entries) == 0


def test_instance_unavailable_is_internal_exception() -> None:
    """内部异常与对外异常分离（避免 `instances.py` 反向依赖 `rpc.py`）。"""
    assert issubclass(InstanceUnavailable, Exception)
    assert not issubclass(InstanceUnavailable, InstanceUnavailableError)


def test_may_have_executed_for_unknown_category() -> None:
    """`category=unknown`（非 350004）也按「可能已执行」处理。"""
    from bms_core.msgclient.errors import ErrorCategory

    error = RpcCallError(9999, "unknown", category=ErrorCategory.UNKNOWN)
    assert RpcClient._may_have_executed(error) is True  # pyright: ignore[reportPrivateUsage]


async def test_unknown_category_without_deadline_code_stays_on_same_instance() -> None:
    """`category=unknown` 但不是 `350004`：同样不换实例。"""
    clock = FakeClock()
    selector = StaticInstanceSelector([A, B], clock=clock)
    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(
        seen,
        fail_first=error_response(9999, category="unknown", retryable=False),
        always_fail=True,
    )
    client = _client(selector, transport, clock=clock)
    try:
        with pytest.raises(RpcCallError):
            await client.call("demo", "echo", b"x", idempotent=True)
    finally:
        await client.aclose()
    assert list(seen)
    assert all(origin == A for origin in seen)


async def test_probe_failure_does_not_retry() -> None:
    """半开探测失败：续摘并直接上抛，不再消耗重试预算。"""
    clock = FakeClock()
    selector = StaticInstanceSelector(
        [A],
        policy=InstancePolicy(failure_threshold=1),
        clock=clock,
    )
    lease = selector.acquire("demo")
    selector.release(lease, InstanceOutcome.FAILURE)
    clock.advance(30_000)

    seen: ConcurrentStableList[str] = ConcurrentStableList()
    transport = await _routing(
        seen,
        fail_first=RpcTransportClosedError("probe failed", phase=PHASE_CONNECT),
        always_fail=True,
    )
    client = _client(selector, transport, clock=clock)
    try:
        with pytest.raises(RpcCallError):
            await client.call("demo", "echo", b"x", idempotent=True)
    finally:
        await client.aclose()
    assert list(seen) == [A]
