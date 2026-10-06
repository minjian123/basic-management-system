"""consistency 能力域缺省实现（Null Object）：即返回、不拦业务。

缺省 `null` 表示**不使用一致性屏障**——`await_applied` 立即返回、不等待也不报错，
不改变既有语义；需一致性保护的调用方按需切 `redis` 提供者显式启用。
"""

from bms_core.consistency.base import BaseConsistencyBarrier
from bms_core.core.capability import BaseNullObject

__all__ = [
    "NullConsistencyBarrier",
]


class NullConsistencyBarrier(BaseConsistencyBarrier, BaseNullObject):
    """占位一致性屏障：即返回、无副作用（未启用屏障时使用）。"""

    async def await_applied(
        self,
        *,
        scope: str,
        target_version: int,
        tenant: str | None = None,
        timeout_ms: int | None = None,
        poll_ms: int | None = None,
    ) -> None:
        """即返回（占位不等待、不校验）。

        Args:
            scope: 收敛域键（占位忽略）。
            target_version: 目标版本（占位忽略）。
            tenant: 租户标识（占位忽略）。
            timeout_ms: 等待超时（占位忽略）。
            poll_ms: 轮询间隔（占位忽略）。
        """

    async def applied_version(self, *, scope: str, tenant: str | None = None) -> int:
        """恒定返回 0（占位无版本记录）。

        Args:
            scope: 收敛域键（占位忽略）。
            tenant: 租户标识（占位忽略）。

        Returns:
            int: 0。
        """
        return 0

    async def mark_applied(self, *, scope: str, version: int, tenant: str | None = None) -> None:
        """空操作（占位不记录版本）。

        Args:
            scope: 收敛域键（占位忽略）。
            version: 已应用版本（占位忽略）。
            tenant: 租户标识（占位忽略）。
        """
