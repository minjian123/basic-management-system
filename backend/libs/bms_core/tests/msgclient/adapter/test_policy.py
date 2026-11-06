"""07B `06_01` 步 2 用例（Kiwi 2441）：`ServiceCallPolicy` → 协议策略的换算与熔断代理。

纯函数 + 一个按调用开关的熔断代理；不启网络，退避/预算本身由 04-4 用例覆盖。
"""

from __future__ import annotations

import pytest

from bms_core.circuit.base import CircuitState
from bms_core.msgclient.adapter.policy import (
    PolicyCircuitBreaker,
    circuit_scope,
    deadline_ms_of,
    default_circuit,
    release_circuit,
    retry_policy_of,
)
from bms_core.msgclient.circuit import InProcessCircuitBreaker
from bms_core.msgclient.constants import RPC_RETRY_CAP_MS, RPC_RETRY_MULTIPLIER
from bms_core.msgclient.retry import JitterMode
from bms_core.servicecall.base import ServiceCallPolicy

pytestmark = pytest.mark.kiwi_id(2441)


def test_deadline_ms_of_scales_seconds() -> None:
    """`timeout`（秒）→ 帧预算（毫秒）：换算只此一处。"""
    assert deadline_ms_of(ServiceCallPolicy(timeout=5.0)) == 5000
    assert deadline_ms_of(ServiceCallPolicy(timeout=0.25)) == 250


def test_retry_policy_of_maps_widenable_fields() -> None:
    """`max_retries` / `retry_backoff` 直译，倍数与封顶取协议缺省。"""
    policy = retry_policy_of(ServiceCallPolicy(max_retries=3, retry_backoff=0.25))
    assert policy.max_retries == 3
    assert policy.base_ms == 250
    assert policy.multiplier == RPC_RETRY_MULTIPLIER
    assert policy.cap_ms == RPC_RETRY_CAP_MS
    assert policy.jitter is JitterMode.FULL
    assert policy.auto_idempotency_key is True


def test_retry_policy_of_keeps_zero_backoff() -> None:
    """`retry_backoff=0` 原样传（退避下限由协议层的 `max(1, …)` 兜，不在换算处伪造）。"""
    assert retry_policy_of(ServiceCallPolicy(retry_backoff=0.0)).base_ms == 0


def test_default_circuit_is_proxy_over_three_state() -> None:
    """缺省熔断器是三态实现的策略代理（不是恒闭合的空实现）。"""
    circuit = default_circuit()
    assert isinstance(circuit, PolicyCircuitBreaker)


async def test_policy_circuit_counts_when_enabled() -> None:
    """开关打开时按三态计数：连续失败达阈值即断开。"""
    proxy = PolicyCircuitBreaker(InProcessCircuitBreaker())
    token = circuit_scope(ServiceCallPolicy(circuit_breaker=True))
    try:
        assert await proxy.allow("service:demo") is True
        for _ in range(5):
            await proxy.record_failure("service:demo")
        assert await proxy.state("service:demo") is CircuitState.OPEN
        assert await proxy.allow("service:demo") is False
    finally:
        release_circuit(token)


async def test_policy_circuit_bypassed_when_disabled() -> None:
    """开关关闭时恒放行且**不计数**（不能把这次算成成功，否则污染别人的失败计数）。"""
    proxy = PolicyCircuitBreaker(InProcessCircuitBreaker())
    token = circuit_scope(ServiceCallPolicy(circuit_breaker=False))
    try:
        for _ in range(6):
            await proxy.record_failure("service:demo")
        await proxy.record_success("service:demo")
        assert await proxy.state("service:demo") is CircuitState.CLOSED
        assert await proxy.allow("service:demo") is True
        assert await proxy.state("service:demo") is CircuitState.CLOSED
    finally:
        release_circuit(token)


async def test_policy_circuit_records_success_when_enabled() -> None:
    """开关打开时成功会清零连续失败（闭合态保持闭合）。"""
    proxy = PolicyCircuitBreaker(InProcessCircuitBreaker())
    token = circuit_scope(ServiceCallPolicy(circuit_breaker=True))
    try:
        await proxy.record_failure("service:demo")
        await proxy.record_success("service:demo")
        assert await proxy.state("service:demo") is CircuitState.CLOSED
    finally:
        release_circuit(token)
