"""search 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.search.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.search.base import (
    NULL_SEARCH_HIT_ID,
    BaseSearchIndex,
    SearchDocument,
    SearchHit,
    SearchQuery,
    SearchResult,
)

__all__ = [
    "NullSearchIndex",
]


class NullSearchIndex(BaseSearchIndex, BaseNullObject):
    """占位全文检索：写入 / 删除空操作，检索固定返回单条占位命中（不连 ES）。"""

    async def index(self, document: SearchDocument) -> None:
        """空操作（占位不写索引）。

        Args:
            document: 待索引文档（占位忽略）。
        """

    async def delete(self, index: str, doc_id: str) -> None:
        """空操作（占位不删除）。

        Args:
            index: 索引名（占位忽略）。
            doc_id: 文档 id（占位忽略）。
        """

    async def search(self, query: SearchQuery) -> SearchResult:
        """固定返回单条占位命中（不连 ES）。

        Args:
            query: 检索请求（占位忽略）。

        Returns:
            SearchResult: 单条占位命中（id 为 `NULL_SEARCH_HIT_ID`、`total=1`）。
        """
        return SearchResult(hits=(SearchHit(id=NULL_SEARCH_HIT_ID, score=0.0),), total=1)
