"""字典高级查询用例（`02_09` 改指补齐）：固定字段 schema + 条件引擎 + 分页执行。

覆盖 `bms_core/dict/query.py`：

- `DictQueryService.load_attrs`（固定字段 schema）与 `advanced_query`（`target=items` 条件引擎分页 /
  `target=business` 提供者委派 / 注册表缺失与分页夹取）；
- 条件引擎纯函数：`_match_group`（深度 / 逻辑 / 结构校验，AND/OR 与嵌套）、`_match_item`
  （字段白名单 / 操作符白名单 / 类型适用性）、`_compare`（各操作符族）与
  `_compare_ordered` / `_as_number` / `_as_list` / `_as_pair` / `_as_text` 值归一；
- `_to_adv_item` 条目映射。
"""

from __future__ import annotations

import json
from typing import Any, cast

import pytest

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList
from bms_core.core.exceptions import ParamError
from bms_core.dict.base import DictItem
from bms_core.dict.query import (
    DICT_ADV_FIXED_FIELDS,
    DICT_ADV_PAGE_SIZE_MAX,
    DICT_OPERATORS_BY_TYPE,
    DictAdvQueryPayload,
    DictQueryService,
    _as_list,  # pyright: ignore[reportPrivateUsage]
    _as_number,  # pyright: ignore[reportPrivateUsage]
    _as_pair,  # pyright: ignore[reportPrivateUsage]
    _as_text,  # pyright: ignore[reportPrivateUsage]
    _compare,  # pyright: ignore[reportPrivateUsage]
    _compare_ordered,  # pyright: ignore[reportPrivateUsage]
    _match_group,  # pyright: ignore[reportPrivateUsage]
    _match_item,  # pyright: ignore[reportPrivateUsage]
    _to_adv_item,  # pyright: ignore[reportPrivateUsage]
)


def _item(value: str, *, label: str = "", sort: int = 0, parent_id: int | None = None) -> DictItem:
    """构造字典条目。

    Args:
        value: 条目值。
        label: 条目标签。
        sort: 排序值。
        parent_id: 上级条目 ID。

    Returns:
        DictItem: 条目。
    """
    return DictItem(value=value, label=label or value, sort=sort, parent_id=parent_id)


def _group(logic: str, children_json: str) -> ConcurrentStableDict[str, object]:
    """构造条件组（`children` 经 JSON 解析，与请求体同形态）。

    Args:
        logic: 逻辑（AND / OR）。
        children_json: 子项 JSON 文本（或 `null`）。

    Returns:
        ConcurrentStableDict[str, object]: 条件组。
    """
    group: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    group.set("logic", logic)
    group.set("children", json.loads(children_json))
    return group


def _node(node_json: str) -> ConcurrentStableDict[str, object]:
    """构造条件项（JSON 解析，与请求体同形态）。

    Args:
        node_json: 条件项 JSON 文本。

    Returns:
        ConcurrentStableDict[str, object]: 条件项。
    """
    return ConcurrentStableDict(json.loads(node_json))


class _Loaded:
    """取数结果替身（只带 `items`）。"""

    def __init__(self, items: ConcurrentStableList[DictItem]) -> None:
        """初始化。

        Args:
            items: 条目集。
        """
        self.items = items


class _Source:
    """统一出口替身（记录取数参数并回固定条目集）。"""

    def __init__(self, items: ConcurrentStableList[DictItem]) -> None:
        """初始化。

        Args:
            items: 条目集。
        """
        self.items = items
        self.queries: ConcurrentStableList[Any] = ConcurrentStableList()

    async def by_type(self, query: object) -> _Loaded:
        """按查询参数回条目集。

        Args:
            query: 取数参数。

        Returns:
            _Loaded: 取数结果。
        """
        self.queries.add(query)
        return _Loaded(self.items)


class _ProviderResult:
    """提供者结果替身（`rows` + `total`）。"""

    def __init__(self) -> None:
        """初始化固定结果。"""
        self.rows = (ConcurrentStableDict({"id": 1}),)
        self.total = 1


class _Registry:
    """查询提供者注册表替身（记录键与参数）。"""

    def __init__(self) -> None:
        """初始化空记录。"""
        self.calls: ConcurrentStableList[tuple[str, ConcurrentStableDict[str, object]]] = ConcurrentStableList()

    async def query(self, key: str, params: ConcurrentStableDict[str, object]) -> _ProviderResult:
        """记录调用并回固定结果。

        Args:
            key: 提供者键。
            params: 参数。

        Returns:
            _ProviderResult: 结果。
        """
        self.calls.add((key, params))
        return _ProviderResult()


async def test_load_attrs_returns_fixed_field_schema() -> None:
    """`load_attrs` 返回固定字段 schema（无扩展属性表）。"""
    service = DictQueryService(source=cast("Any", _Source(ConcurrentStableList(()))))
    attrs = await service.load_attrs("demo", "zh-CN")
    assert tuple(attr.attr_key for attr in attrs) == DICT_ADV_FIXED_FIELDS
    assert attrs[0].operators == DICT_OPERATORS_BY_TYPE["text"]


async def test_advanced_query_items_clamps_paging_and_filters() -> None:
    """`target=items`：分页夹取（页码 ≥ 1、页长 ≤ 上限）+ 条件过滤 + 结果映射。"""
    items = (_item("a", sort=1), _item("b", sort=5), _item("c", sort=9))
    service = DictQueryService(source=cast("Any", _Source(items)))  # pyright: ignore[reportArgumentType]  # 08_05：注解落集合类，值形态由契约/外部决定

    conditions = _group("AND", '[{"field": "value", "operator": "eq", "value": "b"}]')
    result = await service.advanced_query("demo", DictAdvQueryPayload(page=0, size=1000, conditions=conditions))
    assert result.page == 1
    assert result.size == DICT_ADV_PAGE_SIZE_MAX
    assert result.total == 1
    assert [row.value for row in result.items] == ["b"]
    assert result.items[0].parent_id is None

    unfiltered = await service.advanced_query("demo", DictAdvQueryPayload())
    assert unfiltered.total == 3
    assert [row.value for row in unfiltered.items] == ["a", "b", "c"]


async def test_advanced_query_business_requires_registry() -> None:
    """`target=business` 未给注册表 → 10001。"""
    service = DictQueryService(source=cast("Any", _Source(ConcurrentStableList(()))))
    with pytest.raises(ParamError):
        await service.advanced_query("demo", DictAdvQueryPayload(target="business"))


async def test_advanced_query_business_delegates_with_params() -> None:
    """`target=business`：经注册表执行，参数合并（`data_source_key` 补位 + 分页写入）。"""
    registry = _Registry()
    service = DictQueryService(source=cast("Any", _Source(ConcurrentStableList(()))))
    params: ConcurrentStableDict[str, object] = ConcurrentStableDict()
    params.set("keyword", "x")

    result = await service.advanced_query(
        "demo",
        DictAdvQueryPayload(target="business", params=params, page=2, size=5),
        registry=cast("Any", registry),
    )

    key, sent = registry.calls[0]
    assert key == "builtin"
    assert sent.get("keyword") == "x"
    assert sent.get("data_source_key") == "demo"
    assert sent.get("page") == 2
    assert sent.get("size") == 5
    assert result.total == 1
    assert result.rows[0].get("id") == 1


def test_match_group_validation_branches() -> None:
    """条件组校验：深度超限 / 逻辑非法 / 子项结构非法 → 10001；缺失或空子项 → 恒真。"""
    item = _item("a")
    nested = _group("AND", '[{"logic": "AND", "children": [{"logic": "AND", "children": []}]}]')
    with pytest.raises(ParamError):
        _match_group(nested, item, depth=1)
    with pytest.raises(ParamError):
        _match_group(_group("XOR", "[]"), item, depth=1)
    with pytest.raises(ParamError):
        _match_group(_group("AND", '["not-a-mapping"]'), item, depth=1)

    assert _match_group(_group("AND", "null"), item, depth=1) is True
    assert _match_group(_group("AND", "[]"), item, depth=1) is True


def test_match_group_and_or_with_nesting() -> None:
    """条件组：AND 全真、OR 任一真；嵌套子组递归求值。"""
    item = _item("b", sort=5)
    and_group = _group(
        "AND",
        '[{"field": "value", "operator": "eq", "value": "b"}, {"field": "sort", "operator": "gt", "value": 1}]',
    )
    assert _match_group(and_group, item, depth=1) is True

    nested_group = _group(
        "OR",
        '[{"field": "value", "operator": "eq", "value": "zzz"}, '
        '{"logic": "AND", "children": [{"field": "value", "operator": "contains", "value": "b"}]}]',
    )
    assert _match_group(nested_group, item, depth=1) is True


def test_match_item_rejects_unknown_field_and_operator() -> None:
    """条件项：字段不在白名单 / 操作符不支持 / 操作符不适用类型 → 10001。"""
    item = _item("a")
    with pytest.raises(ParamError):
        _match_item(_node('{"field": "nope", "operator": "eq", "value": "a"}'), item)
    with pytest.raises(ParamError):
        _match_item(_node('{"field": "value", "operator": "nope", "value": "a"}'), item)
    with pytest.raises(ParamError):
        _match_item(_node('{"field": "sort", "operator": "contains", "value": "a"}'), item)


@pytest.mark.parametrize(
    ("item", "node", "expected"),
    [
        (_item("a"), {"field": "code", "operator": "is_null", "value": None}, False),
        (_item("a"), {"field": "status", "operator": "is_null", "value": None}, False),
        (_item("a"), {"field": "code", "operator": "not_null", "value": None}, True),
        (_item("a"), {"field": "value", "operator": "in", "value": ["a", "b"]}, True),
        (_item("c"), {"field": "value", "operator": "not_in", "value": ["a", "b"]}, True),
        (_item("abc"), {"field": "value", "operator": "contains", "value": "b"}, True),
        (_item("abc"), {"field": "value", "operator": "not_contains", "value": "z"}, True),
        (_item("abc"), {"field": "value", "operator": "starts_with", "value": "ab"}, True),
        (_item("a"), {"field": "value", "operator": "ne", "value": "b"}, True),
        (_item("a", sort=5), {"field": "sort", "operator": "lt", "value": 9}, True),
        (_item("a", sort=5), {"field": "sort", "operator": "between", "value": [1, 9]}, True),
    ],
)
def test_match_item_operator_families(item: DictItem, node: Any, expected: bool) -> None:
    """条件项：各操作符族（空值 / 集合 / 模糊 / 等值 / 有序）命中判定。"""
    assert _match_item(_node(json.dumps(node)), item) is expected


def test_compare_rejects_unsupported_operator() -> None:
    """未知操作符 → 10001。"""
    with pytest.raises(ParamError):
        _compare("a", "nope", "a", "text")


def test_compare_ordered_handles_between_and_gt() -> None:
    """有序比较：`between` 区间命中；`gt` 严格大于；非数值回落字符串长度序 + 非法值 10001。"""
    assert _compare_ordered(5, "between", [1, 9]) is True
    assert _compare_ordered(5, "gt", 3) is True
    assert _compare_ordered(5, "gt", 9) is False
    assert _compare_ordered("5", "gt", 3) is True
    with pytest.raises(ParamError):
        _compare_ordered(5, "between", [1])


def test_value_normalizers_branches() -> None:
    """值归一：`_as_number` / `_as_list` / `_as_pair` / `_as_text` 边界。"""
    assert _as_number(True) == 1.0
    assert _as_number(False) == 0.0
    assert _as_number(3) == 3.0
    assert _as_number("x") == 0.0

    assert list(_as_list("a")) == ["a"]
    assert list(_as_list(json.loads('["a", "b"]'))) == ["a", "b"]
    with pytest.raises(ParamError):
        _as_list([])
    with pytest.raises(ParamError):
        _as_list(None)

    assert _as_pair(json.loads("[1, 2]")) == (1, 2)
    with pytest.raises(ParamError):
        _as_pair("nope")

    assert _as_text(1) == "1"
    with pytest.raises(ParamError):
        _as_text(None)


def test_to_adv_item_maps_parent_id_to_string() -> None:
    """`_to_adv_item`：`parent_id` 有值转字符串、无值保持 `None`。"""
    mapped = _to_adv_item(_item("a", parent_id=9))
    assert mapped.parent_id == "9"
    assert _to_adv_item(_item("a")).parent_id is None
