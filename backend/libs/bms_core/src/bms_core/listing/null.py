"""listing 能力域缺省实现（Null Object）：固定返回空 / None / 原样，不落库、无副作用。"""

from bms_core.core.capability import BaseNullObject
from bms_core.listing.base import BaseQuerySchemeStore, QueryScheme, QuerySchemeTarget

__all__ = ["NullQuerySchemeStore"]


class NullQuerySchemeStore(BaseQuerySchemeStore, BaseNullObject):
    """占位查询方案存储：列表空、详情 None、保存原样返回、删除失败、默认解析 None（不落库）。"""

    async def list(self, target: QuerySchemeTarget, *, field_key: str | None = None) -> tuple[QueryScheme, ...]:
        """列查询方案（占位恒空）。

        Args:
            target: 方案目标（占位忽略）。
            field_key: 表单标识（占位忽略）。

        Returns:
            tuple[QueryScheme, ...]: 空元组。
        """
        return ()

    async def get(self, scheme_id: int) -> QueryScheme | None:
        """取单个方案（占位恒未命中）。

        Args:
            scheme_id: 方案 ID（占位忽略）。

        Returns:
            QueryScheme | None: None。
        """
        return None

    async def save(self, scheme: QueryScheme) -> QueryScheme:
        """保存方案（占位原样返回）。

        Args:
            scheme: 方案。

        Returns:
            QueryScheme: 入参方案。
        """
        return scheme

    async def delete(self, scheme_id: int) -> bool:
        """删除方案（占位恒无既有方案）。

        Args:
            scheme_id: 方案 ID（占位忽略）。

        Returns:
            bool: False。
        """
        return False

    async def resolve_default(
        self,
        target: QuerySchemeTarget,
        *,
        field_key: str | None = None,
    ) -> QueryScheme | None:
        """解析默认方案（占位恒 None）。

        Args:
            target: 方案目标（占位忽略）。
            field_key: 表单标识（占位忽略）。

        Returns:
            QueryScheme | None: None。
        """
        return None
