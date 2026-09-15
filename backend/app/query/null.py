"""query 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.query.base.py 迁入）。"""

from collections.abc import Mapping

from app.core.capability import BaseNullObject
from app.query.base import BaseQueryProvider, BaseQueryProviderRegistry, QueryResult

__all__ = [
    "NullQueryProvider",
    "NullQueryProviderRegistry",
]


class NullQueryProvider(BaseQueryProvider, BaseNullObject):
    """占位查询提供者：恒定返回空结果（不执行 SQL）。"""

    @property
    def key(self) -> str:
        """提供者标识。

        Returns:
            str: 占位提供者 key。
        """
        return "null_query_provider"

    def describe(self) -> str:
        """元信息描述。

        Returns:
            str: 占位提供者说明。
        """
        return f"查询提供者 {self.key}（占位实现）"

    async def query(self, params: Mapping[str, object]) -> QueryResult:
        """恒定返回空结果。

        Args:
            params: 查询参数（占位忽略）。

        Returns:
            QueryResult: 空结果（`rows == ()` / `total == 0`）。
        """
        return QueryResult(rows=(), total=0)


class NullQueryProviderRegistry(BaseQueryProviderRegistry, BaseNullObject):
    """占位注册表：注册空操作、无提供者；`query` 固定返回空结果（不执行 SQL）。"""

    def register(self, provider: BaseQueryProvider) -> None:
        """空操作（占位不注册）。

        Args:
            provider: 查询提供者（占位忽略）。
        """

    def get(self, key: str) -> BaseQueryProvider | None:
        """无提供者。

        Args:
            key: 提供者标识（占位忽略）。

        Returns:
            BaseQueryProvider | None: None。
        """
        return None

    def keys(self) -> tuple[str, ...]:
        """空提供者清单。

        Returns:
            tuple[str, ...]: 空元组。
        """
        return ()

    async def query(self, key: str, params: Mapping[str, object]) -> QueryResult:
        """固定返回空结果（占位不抛错、不执行 SQL）。

        Args:
            key: 提供者标识（占位忽略）。
            params: 查询参数（占位忽略）。

        Returns:
            QueryResult: 空结果。
        """
        return QueryResult(rows=(), total=0)
