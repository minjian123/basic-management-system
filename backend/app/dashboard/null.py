"""dashboard 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.dashboard.base.py 迁入）。"""

from collections.abc import Mapping

from app.core.capability import BaseNullObject
from app.dashboard.base import BaseDashboardCardProvider, BaseDashboardCardRegistry

__all__ = [
    "NullDashboardCardRegistry",
]


class NullDashboardCardRegistry(BaseDashboardCardRegistry, BaseNullObject):
    """占位注册表：注册空操作、无卡片；元数据与取数固定返回空映射（空卡片集）。"""

    def register(self, provider: BaseDashboardCardProvider) -> None:
        """空操作（占位不注册）。

        Args:
            provider: 卡片提供者（占位忽略）。
        """

    def get(self, key: str) -> BaseDashboardCardProvider | None:
        """无卡片。

        Args:
            key: 卡片标识（占位忽略）。

        Returns:
            BaseDashboardCardProvider | None: None。
        """
        return None

    def keys(self) -> tuple[str, ...]:
        """空卡片集。

        Returns:
            tuple[str, ...]: 空元组。
        """
        return ()

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
