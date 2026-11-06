"""`ServiceCallPolicy` → 协议策略的**唯一换算处**（07B `06_01` 步 2）。

**为什么单独一个模块**：同一份 `ServiceCallPolicy` 要被翻译成三种东西——帧预算（`deadline_ms`）、
重试策略（`RetryPolicy`）、熔断开关。换算散在调用点就会出现「这里减了 1000，那里忘了」，
而这类偏差只在跨通道对比时才暴露。

**不重复实现退避 / 熔断算法**：退避、抖动、预算、三态全在 `bms_core.msgclient.retry` /
`circuit`（04-4 交付）；本模块只做**字段换算**与**开关到实例的选择**。

**逐调用而非一次性**：`RetryPolicy` 每次调用换算后传入 `RpcClient.call(policy=…)`；熔断开关经
`ContextVar` 作用域生效（`RpcClient` 的熔断器是实例级，逐调用开关只能这样表达，且按任务隔离、
并发安全）。同一进程内不同调用点给不同策略时，行为才可解释。
"""

from __future__ import annotations

from contextvars import ContextVar, Token

from bms_core.circuit.base import BaseCircuitBreaker, CircuitState
from bms_core.msgclient.circuit import InProcessCircuitBreaker
from bms_core.msgclient.constants import MS_PER_SECOND, RPC_RETRY_CAP_MS, RPC_RETRY_MULTIPLIER
from bms_core.msgclient.retry import JitterMode, RetryPolicy
from bms_core.servicecall.base import ServiceCallPolicy

__all__ = [
    "PolicyCircuitBreaker",
    "circuit_scope",
    "deadline_ms_of",
    "default_circuit",
    "release_circuit",
    "retry_policy_of",
]
_CIRCUIT_ENABLED: ContextVar[bool] = ContextVar("bms_msg_adapter_circuit_enabled", default=True)
"""本协程链上「是否启用熔断」的开关（由 `circuit_scope` 设置、`release_circuit` 复位）。"""


class PolicyCircuitBreaker(BaseCircuitBreaker):
    """三态熔断器的**策略代理**：逐调用开关关闭时恒放行且不计数。

    `RpcClient` 的熔断器是构造注入的实例级依赖，无法逐调用替换；把开关做成代理上的
    `ContextVar` 读取，既保住「一个客户端、一条连接池」，又让 `ServiceCallPolicy.circuit_breaker`
    真正逐调用生效。关闭语义是「完全不参与」——不是「当成成功」，否则会污染别人的失败计数。
    """

    def __init__(self, inner: BaseCircuitBreaker) -> None:
        """初始化。

        Args:
            inner: 实际计数的熔断器（缺省三态实现）。
        """
        self._inner = inner

    async def allow(self, dependency: str) -> bool:
        """放行判定（开关关闭时恒放行）。

        Args:
            dependency: 依赖标识。

        Returns:
            bool: 放行为 True。
        """
        if not _CIRCUIT_ENABLED.get():
            return True
        return await self._inner.allow(dependency)

    async def record_success(self, dependency: str) -> None:
        """记录成功（开关关闭时不计数）。

        Args:
            dependency: 依赖标识。
        """
        if _CIRCUIT_ENABLED.get():
            await self._inner.record_success(dependency)

    async def record_failure(self, dependency: str) -> None:
        """记录失败（开关关闭时不计数）。

        Args:
            dependency: 依赖标识。
        """
        if _CIRCUIT_ENABLED.get():
            await self._inner.record_failure(dependency)

    async def state(self, dependency: str) -> CircuitState:
        """当前状态（读的是内层真实状态，便于排障）。

        Args:
            dependency: 依赖标识。

        Returns:
            CircuitState: 三态之一。
        """
        return await self._inner.state(dependency)


def deadline_ms_of(policy: ServiceCallPolicy) -> int:
    """`ServiceCallPolicy.timeout`（秒）→ 帧预算 `deadline_ms`（毫秒）。

    越界（> `RPC_DEADLINE_MAX_MS`）由 `RpcClient` 的 `validate_budget_ms` 以 `10001` 拦下——
    预算上限是协议口径，不在本层重复校验。

    Args:
        policy: 调用韧性策略。

    Returns:
        int: 预算毫秒。
    """
    return int(policy.timeout * MS_PER_SECOND)


def retry_policy_of(policy: ServiceCallPolicy) -> RetryPolicy:
    """`ServiceCallPolicy` → `RetryPolicy`（倍数 / 封顶 / 抖动取协议缺省，不由调用方配）。

    - `max_budget` 保持协议缺省（调用链共享上限）：调用方给更大的 `max_retries` 只影响单跳重试
      上限，不会突破「A→B→C 共用一份预算」的防风暴约束。
    - `auto_idempotency_key` 恒开：bms 端口语义是「重试由策略决定」，调用方不下发幂等键；
      关掉会让无键调用在首个可重试错误处被判「非幂等禁止重试」，与 `max_retries > 0` 矛盾。

    Args:
        policy: 调用韧性策略。

    Returns:
        RetryPolicy: 协议侧重试策略。
    """
    return RetryPolicy(
        max_retries=policy.max_retries,
        base_ms=int(policy.retry_backoff * MS_PER_SECOND),
        multiplier=RPC_RETRY_MULTIPLIER,
        cap_ms=RPC_RETRY_CAP_MS,
        jitter=JitterMode.FULL,
        auto_idempotency_key=True,
    )


def circuit_scope(policy: ServiceCallPolicy) -> Token[bool]:
    """进入本次调用的熔断作用域（`policy.circuit_breaker=False` 即关闭）。

    Args:
        policy: 调用韧性策略。

    Returns:
        Token[bool]: 复位令牌（调用方 `finally` 交 `release_circuit`）。
    """
    return _CIRCUIT_ENABLED.set(policy.circuit_breaker)


def release_circuit(token: Token[bool]) -> None:
    """退出熔断作用域。

    Args:
        token: `circuit_scope` 返回的令牌。
    """
    _CIRCUIT_ENABLED.reset(token)


def default_circuit() -> BaseCircuitBreaker:
    """msg 通道缺省熔断器：三态实现 + 策略代理（同 `service:<key>` 依赖标识）。

    取协议包自带的 `InProcessCircuitBreaker` 而不是 `[circuit_breaker]` 配置解析结果：基座缺省
    解析出的是恒闭合的 `NullCircuitBreaker`，直接沿用等于「开关打开但永不熔断」。生产是否默认
    启用三态由本函数的替换点决定（`[circuit_breaker]` 落地真实实现后改判定）。

    Returns:
        BaseCircuitBreaker: 策略代理包装的三态熔断器。
    """
    return PolicyCircuitBreaker(InProcessCircuitBreaker())
