"""circuit 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.circuit.base.py 迁入）。"""

from bms_core.circuit.base import BaseCircuitBreaker, CircuitState
from bms_core.core.capability import BaseNullObject

__all__ = [
    "NullCircuitBreaker",
]


class NullCircuitBreaker(BaseCircuitBreaker, BaseNullObject):
    """占位熔断器：**恒定闭合**（不计数、不熔断，未接入真实实现时使用）。"""

    async def allow(self, dependency: str) -> bool:
        """恒定放行。

        Args:
            dependency: 依赖标识（占位不区分）。

        Returns:
            bool: True。
        """
        return True

    async def record_success(self, dependency: str) -> None:
        """记录成功（占位空操作）。

        Args:
            dependency: 依赖标识（占位不区分）。
        """
        return None

    async def record_failure(self, dependency: str) -> None:
        """记录失败（占位空操作）。

        Args:
            dependency: 依赖标识（占位不区分）。
        """
        return None

    async def state(self, dependency: str) -> CircuitState:
        """恒定闭合。

        Args:
            dependency: 依赖标识（占位不区分）。

        Returns:
            CircuitState: `CircuitState.CLOSED`。
        """
        return CircuitState.CLOSED
