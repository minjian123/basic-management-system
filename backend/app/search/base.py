"""全文检索能力域：统一索引契约（真实 ElasticSearch 8.x 随全文检索阶段回补）。

- `SEARCH_INDEX_PREFIX`：索引名前缀（`bms-`，架构 24：`bms-main` / `bms-prd-*` / `bms-log-*` / `bms-file`）。
- `DEFAULT_SEARCH_SIZE` / `NULL_SEARCH_HIT_ID`：默认返回条数与占位命中 id。
- `SearchDocument` / `SearchQuery` / `SearchHit` / `SearchResult`：写入 / 查询 / 命中 / 结果数据契约（frozen）。
- `BaseSearchIndex`：能力域中间层契约（`key = "search_index"`）——异步 `index` / `delete` / `search`。
- `NullSearchIndex`：占位实现——写入 / 删除空操作、`search` 固定返回单条占位命中（**不连 ES**）。
- `get_search_index`：依赖注入提供者（应用级单例；公共依赖经 `app/api/deps.py` 统一导出）。

口径：索引均含 `tenant_id` 字段、查询**强制**租户隔离并叠加动作级数据权限过滤——`tenant_id` 与权限过滤由**实现**
从上下文（`core/context.py` 的 `current_tenant`）与权限基座注入，契约方法不显式传租户参数、调用方不可绕过；
检索只返回 id + 分数 + 高亮，详情回查数据库。同步管线 / 重建 / 降级归全文检索阶段上层。
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from fastapi import Request

from app.core.base import BaseObject
from app.core.capability import BaseNullObject
from app.core.plugin import DEFAULT_CONTRACT_VERSION, NULL_PLUGIN_NAME, BasePluggable

__all__ = [
    "DEFAULT_SEARCH_SIZE",
    "NULL_SEARCH_HIT_ID",
    "SEARCH_INDEX_PREFIX",
    "BaseSearchIndex",
    "NullSearchIndex",
    "SearchDocument",
    "SearchHit",
    "SearchQuery",
    "SearchResult",
    "get_search_index",
]

SEARCH_INDEX_PREFIX = "bms-"
"""索引名前缀（架构 24：`bms-main` / `bms-prd-*` / `bms-log-*` / `bms-file`）；占位期仅登记不校验。"""

DEFAULT_SEARCH_SIZE = 20
"""默认返回条数。"""

NULL_SEARCH_HIT_ID = "null-search-hit"
"""占位命中 id（NullSearchIndex.search 固定返回，便于断言）。"""


@dataclass(frozen=True)
class SearchDocument(BaseObject):
    """待索引文档（`tenant_id` 由实现从上下文注入，不在本契约显式声明）。"""

    index: str
    """索引名（建议以 `SEARCH_INDEX_PREFIX` 开头）。"""

    doc_id: str
    """文档 id（业务主键，字符串化）。"""

    fields: Mapping[str, object]
    """索引字段映射。"""


@dataclass(frozen=True)
class SearchQuery(BaseObject):
    """检索请求。"""

    index: str
    """索引名。"""

    text: str
    """检索关键词。"""

    filters: Mapping[str, object] | None = None
    """业务过滤条件（租户隔离与数据权限过滤由实现强制叠加，不在此传）。"""

    offset: int = 0
    """起始偏移。"""

    size: int = DEFAULT_SEARCH_SIZE
    """返回条数。"""


@dataclass(frozen=True)
class SearchHit(BaseObject):
    """命中项（只含 id / 分数 / 高亮，详情回查数据库）。"""

    id: str
    """文档 id。"""

    score: float
    """相关度分数。"""

    highlight: Mapping[str, str] | None = None
    """高亮片段（字段 → 片段）。"""


@dataclass(frozen=True)
class SearchResult(BaseObject):
    """检索结果。"""

    hits: tuple[SearchHit, ...]
    """命中项（分页后）。"""

    total: int = 0
    """命中总数。"""


class BaseSearchIndex(BasePluggable, ABC):
    """全文检索契约：写入 / 删除 / 检索（租户隔离与数据权限过滤由实现强制注入）。"""

    key: str = "search_index"
    plugin_key: str = "search_index"
    plugin_name: str = NULL_PLUGIN_NAME
    contract_version: str = DEFAULT_CONTRACT_VERSION

    @abstractmethod
    async def index(self, document: SearchDocument) -> None:
        """写入 / 更新单个文档。

        Args:
            document: 待索引文档（`tenant_id` 由实现从上下文注入）。
        """

    @abstractmethod
    async def delete(self, index: str, doc_id: str) -> None:
        """删除文档（幂等，不存在不报错）。

        Args:
            index: 索引名。
            doc_id: 文档 id。
        """

    @abstractmethod
    async def search(self, query: SearchQuery) -> SearchResult:
        """检索（强制租户隔离 + 数据权限过滤；只返回 id + 分数 + 高亮）。

        Args:
            query: 检索请求。

        Returns:
            SearchResult: 检索结果。
        """


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


def get_search_index(request: Request) -> BaseSearchIndex:
    """取应用级全文检索索引（依赖注入提供者）。

    Args:
        request: 请求对象。

    Returns:
        BaseSearchIndex: 应用装配的索引实例。
    """
    return cast("BaseSearchIndex", request.app.state.search_index)
