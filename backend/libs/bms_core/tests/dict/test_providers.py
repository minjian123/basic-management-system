"""字典域内建查询提供者用例（`02_09` 改指补齐）。

覆盖 `bms_core/dict/providers.py`：`BuiltinDictQueryProvider` 的标识 / 描述 / 清单项，
`query` 的参数校验（缺 `data_source_key`）、关键字过滤（label / value / code）、分页截断与行映射，
以及 `_as_page` 的参数归一分支。
"""

from __future__ import annotations

from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.dict.base import DictItem
from bms_core.dict.providers import (
    PAGE_SIZE_MAX,
    BuiltinDictQueryProvider,
    _as_page,  # pyright: ignore[reportPrivateUsage]
    _to_row,  # pyright: ignore[reportPrivateUsage]
)


class _Loaded:
    """取数结果替身（只带 `items`）。"""

    def __init__(self, items: ConcurrentStableList[DictItem]) -> None:
        """初始化。

        Args:
            items: 条目集。
        """
        self.items = items


class _Source:
    """统一出口替身（记录查询参数并回固定条目集）。"""

    def __init__(self, items: ConcurrentStableList[DictItem]) -> None:
        """初始化。

        Args:
            items: 条目集。
        """
        self.items = items
        self.queries: ConcurrentStableList[Any] = ConcurrentStableList()

    async def by_type(self, query: object) -> _Loaded:
        """按参数回条目集。

        Args:
            query: 取数参数。

        Returns:
            _Loaded: 取数结果。
        """
        self.queries.add(query)
        return _Loaded(self.items)


def _provider(items: ConcurrentStableList[DictItem]) -> tuple[BuiltinDictQueryProvider, _Source]:
    """构造提供者与源替身。

    Args:
        items: 条目集。

    Returns:
        tuple[BuiltinDictQueryProvider, _Source]: (提供者, 源替身)。
    """
    source = _Source(items)
    return BuiltinDictQueryProvider(source=cast("Any", source)), source


def _params(**kwargs: object) -> ConcurrentStableDict[str, object]:
    """构造查询参数。

    Args:
        kwargs: 键值对。

    Returns:
        ConcurrentStableDict[str, object]: 参数。
    """
    params: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    for key, value in kwargs.items():
        params.set(key, value)
    return params


def test_provider_metadata() -> None:
    """提供者标识 / 描述 / 清单项（含参数 schema 子集）。"""
    provider, _source = _provider(ConcurrentStableList(()))
    assert provider.key == "builtin"
    assert provider.describe() == "字典条目查询（内建示例提供者）"

    info = provider.info()
    assert info.key == "builtin"
    assert info.target == "business"
    assert info.data_source_keys == ()
    assert info.param_schema.get("required") == ["data_source_key"]


async def test_provider_query_requires_data_source_key() -> None:
    """缺 `data_source_key`（缺失 / 非字符串 / 空串）→ 10001。"""
    provider, _source = _provider(ConcurrentStableList(()))
    for bad in (None, 123, ""):
        with pytest.raises(ParamError):
            await provider.query(_params(data_source_key=bad))


async def test_provider_query_filters_keyword_and_pages() -> None:
    """查询：关键字命中 label / value / code；页码与页长归一（页长夹取上限）。"""
    items = (
        DictItem(value="a", label="甲", code="alpha", sort=0),
        DictItem(value="b", label="乙", code="beta", sort=1),
        DictItem(value="c", label="丙", code="gamma", sort=2),
    )
    provider, source = _provider(items)  # pyright: ignore[reportArgumentType]  # 08_05：注解落集合类，值形态由契约/外部决定

    all_rows = await provider.query(_params(data_source_key="demo", page=1, size=9999))
    assert all_rows.total == 3
    assert [row.get("value") for row in all_rows.rows] == ["a", "b", "c"]
    assert source.queries[0].data_source_key == "demo"

    by_code = await provider.query(_params(data_source_key="demo", keyword=" bet "))
    assert by_code.total == 1
    assert by_code.rows[0].get("code") == "beta"

    by_label = await provider.query(_params(data_source_key="demo", keyword="丙"))
    assert [row.get("value") for row in by_label.rows] == ["c"]

    # 空白关键字不参与过滤；字符串页码可解析；页长上限夹取。
    second_page = await provider.query(_params(data_source_key="demo", keyword="   ", page="2", size="9999"))
    assert second_page.total == 3
    assert second_page.rows == ()
    assert PAGE_SIZE_MAX == 100


def test_to_row_maps_item_fields() -> None:
    """条目 → 结果行字段映射。"""
    row = _to_row(DictItem(value="a", label="甲", code="alpha", parent_id=9, sort=3, status="disabled", color="#fff"))
    assert row.get("value") == "a"
    assert row.get("parent_id") == 9
    assert row.get("status") == "disabled"
    assert row.get("color") == "#fff"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, 1),
        (7, 7),
        ("8", 8),
        ("x", 1),
        (None, 1),
    ],
)
def test_as_page_normalization(value: object, expected: int) -> None:
    """`_as_page`：布尔回落默认、整数原样、数字串解析、其余回落默认。"""
    assert _as_page(value) == expected
    assert _as_page(value, default=5) == (5 if value in (True, "x", None) else expected)
