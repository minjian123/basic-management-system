"""dashboard 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.dashboard.base.py 迁入）。"""

from collections.abc import Mapping

from app.core.capability import BaseNullObject
from app.dashboard.base import BaseDashboardCardProvider, BaseDashboardCardRegistry

__all__ = [
    "NullDashboardCardRegistry",
]


class NullDashboardCardRegistry(BaseDashboardCardRegistry, BaseNullObject):
    """占位注册表：登记与解析继承公共实现（唯一性拒重）；元数据与取数固定返回空映射（空卡片集）。"""

    @classmethod
    def _provider_key(cls, provider: BaseDashboardCardProvider) -> str:
        """注册项键：卡片 `key`。

        Args:
            provider: 卡片提供者。

        Returns:
            str: 卡片标识。
        """
        return provider.key

    def metadata(self, card_key: str) -> Mapping[str, object]:
        """固定返回空元数据（占位空卡片集）。

        Args:
            card_key: 卡片标识（占位忽略）。

        Returns:
            Mapping[str, object]: 空映射。
        """
        return {}

    async def fetch(self, card_key: str, params: Mapping[str, object]) -> Mapping[str, object]:
        """固定返回空数据（占位空卡片集）。

        Args:
            card_key: 卡片标识（占位忽略）。
            params: 取数参数（占位忽略）。

        Returns:
            Mapping[str, object]: 空映射。
        """
        return {}
