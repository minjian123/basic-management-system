"""全文检索基座契约测试（Kiwi 49）：契约 / 标识 / 常量 / 数据契约 / 占位固定返回 / 依赖解析。"""

from dataclasses import FrozenInstanceError

import pytest
from fastapi import FastAPI

from bms_core.core.base import BaseObject
from bms_core.core.capability import BaseCapability, BaseNullObject
from bms_core.core.concurrent import (
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
)
from bms_core.search.base import (
    DEFAULT_SEARCH_SIZE,
    NULL_SEARCH_HIT_ID,
    SEARCH_INDEX_PREFIX,
    BaseSearchIndex,
    SearchDocument,
    SearchHit,
    SearchQuery,
    SearchResult,
)
from bms_core.search.null import NullSearchIndex


@pytest.mark.kiwi_id(49)
def test_inheritance_and_key() -> None:
    """契约继承链、占位标记与能力域标识。"""
    assert issubclass(BaseCapability, BaseObject)
    assert issubclass(BaseSearchIndex, BaseCapability)
    assert issubclass(NullSearchIndex, BaseSearchIndex)
    assert issubclass(NullSearchIndex, BaseNullObject)
    assert BaseSearchIndex.key == "search_index"

    index = NullSearchIndex()
    assert index.placeholder is True
    assert "占位实现" in index.describe()


@pytest.mark.kiwi_id(49)
def test_constants() -> None:
    """索引前缀与默认返回条数常量。"""
    assert SEARCH_INDEX_PREFIX == "bms-"
    assert DEFAULT_SEARCH_SIZE == 20


@pytest.mark.kiwi_id(49)
def test_data_contracts_defaults_and_frozen() -> None:
    """`SearchQuery` / `SearchHit` / `SearchResult` 默认值正确且不可变。"""
    query = SearchQuery(index="bms-main", text="kw")
    assert query.offset == 0
    assert query.size == DEFAULT_SEARCH_SIZE
    assert query.filters is None
    assert SearchHit(id="1", score=1.0).highlight is None
    assert SearchResult(hits=ConcurrentStableFrozenList(())).total == 0

    field = "text"
    with pytest.raises(FrozenInstanceError):
        setattr(query, field, "other")


@pytest.mark.kiwi_id(49)
async def test_null_index_and_delete_noop() -> None:
    """占位写入 / 删除为空操作。"""
    index = NullSearchIndex()
    document = SearchDocument(index="bms-main", doc_id="1", fields=ConcurrentStableFrozenDict({"name": "甲"}))
    assert await index.index(document) is None
    assert await index.delete("bms-main", "1") is None


@pytest.mark.kiwi_id(49)
async def test_null_search_fixed_hit() -> None:
    """占位 search 固定返回单条占位命中。"""
    index = NullSearchIndex()
    result = await index.search(SearchQuery(index="bms-main", text="kw"))
    assert result.total == 1
    assert len(result.hits) == 1
    assert result.hits[0] == SearchHit(id=NULL_SEARCH_HIT_ID, score=0.0)


@pytest.mark.kiwi_id(49)
async def test_dependency_provider_resolves(service_app: FastAPI) -> None:
    """依赖解析：装配态索引是占位实现（固定一条命中），提供者与本应用一致。

    插件实例按应用隔离（13_11）：不比跨应用实例同一性。
    """
    index = service_app.state.search_index
    assert isinstance(index, NullSearchIndex)
    assert service_app.state.plugin_providers["search_index"] == "null"
    result = await index.search(SearchQuery(index="bms-main", text="kw"))
    assert result.total == 1
