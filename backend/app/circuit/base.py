"""熔断能力域：依赖熔断三态契约（真实计数 / 阈值 / 半开探测随性能与安全 / 分布式与监控阶段回补）。

- `CircuitState`：熔断状态枚举（`closed` 闭合放行 / `open` 断开快速失败 / `half_open` 半开探测）。
- `BaseCircuitBreaker`：能力域中间层契约（`key = "circuit_breaker"`）——`allow` 放行判定 +
  `record_success` / `record_failure` 结果记录 + `state` 状态查询。
- `get_circuit_breaker`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

与降级域分工：熔断回答「**要不要发这次调用**」（快速失败），降级回答「**失败后怎么办**」（动作选择）；
依赖标识清单**单向复用** `app/fallback/base.py` 的 `DEPENDENCIES`（circuit → fallback，不反向）。
"""

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import cast

from fastapi import Request

from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable
from app.fallback.base import DEPENDENCIES

__all__ = [
    "DEPENDENCIES",
    "BaseCircuitBreaker",
    "CircuitState",
    "get_circuit_breaker",
]


class CircuitState(StrEnum):
    """熔断状态。"""

    CLOSED = "closed"
    """闭合：正常放行。"""

    OPEN = "open"
    """断开：快速失败（不放行）。"""

    HALF_OPEN = "half_open"
    """半开：探测放行（成功则闭合、失败则回到断开）。"""


class BaseCircuitBreaker(BasePluggable, ABC):
    """熔断契约：放行判定 + 结果记录 + 状态查询（基座不接管调用链）。"""

    key: str = "circuit_breaker"
    plugin_key: str = "circuit_breaker"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def allow(self, dependency: str) -> bool:
        """是否放行本次调用。

        Args:
            dependency: 依赖标识（建议取 `DEPENDENCIES` 之一）。

        Returns:
            bool: 放行为 True；`open` 状态返回 False（调用方快速失败并交给降级动作处理）。
        """

    @abstractmethod
    async def record_success(self, dependency: str) -> None:
        """记录调用成功（清零失败计数；半开探测成功则闭合）。

        Args:
            dependency: 依赖标识。
        """

    @abstractmethod
    async def record_failure(self, dependency: str) -> None:
        """记录调用失败（达阈值则断开；半开探测失败则回到断开）。

        Args:
            dependency: 依赖标识。
        """

    @abstractmethod
    async def state(self, dependency: str) -> CircuitState:
        """当前熔断状态（供告警 / 可观测性读取）。

        Args:
            dependency: 依赖标识。

        Returns:
            CircuitState: 熔断状态。
        """


def get_circuit_breaker(request: Request) -> BaseCircuitBreaker:
    """取应用级熔断器（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseCircuitBreaker: 应用装配的熔断器实例。
    """
    return cast("BaseCircuitBreaker", request.app.state.circuit_breaker)
