"""health 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.health.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.health.base import BaseHealthCheck, BaseHealthCheckRegistry

__all__ = [
    "NullHealthCheckRegistry",
]


class NullHealthCheckRegistry(BaseHealthCheckRegistry, BaseNullObject):
    """占位注册表：登记与解析继承公共实现；聚合固定通过（不探依赖，未接入真实探针时使用）。"""

    @classmethod
    def _provider_key(cls, provider: BaseHealthCheck) -> str:
        """注册项键：检查项 `key`。

        Args:
            provider: 检查项。

        Returns:
            str: 检查项键。
        """
        return provider.key

    def checks(self) -> tuple[BaseHealthCheck, ...]:
        """空检查项集。

        Returns:
            tuple[BaseHealthCheck, ...]: 空元组。
        """
        return ()
