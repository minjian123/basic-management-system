"""契约集合元数据与序列化链测试（Kiwi 2223：契约零漂移与序列化形态）。

覆盖：`Annotated[集合类[X], CONTRACT_COLLECTION]` 校验转集合类、默认空集合工厂、`Optional` 联合形态；
`model_dump()` 输出集合类实例（元素递归 + ID 字符串化）、`model_dump_json()` 输出 `array` / `object`；
契约 JSON Schema 与 `list[X]` / `dict[K, V]` / `frozenset[X]` 逐字节一致（不产生 `$defs` 命名漂移）；
`stringify_ids` 同型重组、`BaseObject._convert` 识别集合类、`stable_json_dumps` 前置规整为内置容器。
"""

import json
from typing import Annotated, cast

import pytest
from pydantic import Field

from bms_core.core.base import BaseObject
from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.core.serialization import stable_json_dumps, stringify_ids
from bms_core.schemas.base import (
    CONTRACT_COLLECTION,
    CONTRACT_STABLE_DICT,
    CONTRACT_STABLE_LIST,
    CONTRACT_STABLE_SET,
    BaseSchema,
)


class _Item(BaseSchema):
    """契约集合元素（含整型 ID，验证递归序列化）。"""

    id: int
    name: str


def _empty_items() -> list[_Item]:
    """对照契约空列表工厂。"""
    return []


def _empty_index() -> dict[str, _Item]:
    """对照契约空映射工厂。"""
    return {}


class _PlainEnvelope(BaseSchema):
    """对照契约：同名字段用内置容器声明。"""

    items: list[_Item] = Field(default_factory=_empty_items)
    index: dict[str, _Item] = Field(default_factory=_empty_index)
    tags: frozenset[str] = Field(default_factory=frozenset)
    optional_items: list[_Item] | None = None


class _Envelope(BaseSchema):
    """契约集合字段：内联元数据 + 空集合工厂常量。"""

    items: Annotated[ConcurrentStableList[_Item], CONTRACT_COLLECTION] = Field(default_factory=CONTRACT_STABLE_LIST)
    index: Annotated[ConcurrentStableDict[str, _Item], CONTRACT_COLLECTION] = Field(
        default_factory=CONTRACT_STABLE_DICT
    )
    tags: Annotated[ConcurrentStableSet[str], CONTRACT_COLLECTION] = Field(default_factory=CONTRACT_STABLE_SET)
    optional_items: Annotated[ConcurrentStableList[_Item] | None, CONTRACT_COLLECTION] = None


class _Holder(BaseObject):
    """普通类（非 Pydantic / 非 dataclass）：验证 `BaseObject._convert` 识别集合类。"""

    def __init__(self, items: ConcurrentStableList[object]) -> None:
        self.items = items


def _envelope(**overrides: object) -> _Envelope:
    """构造含集合字段的契约实例（默认插入序样本）。"""
    payload: dict[str, object] = {
        "items": [{"id": 1, "name": "甲"}, {"id": 2, "name": "乙"}],
        "index": {"k1": {"id": 3, "name": "丙"}},
        "tags": ["beta", "alpha"],
        "optional_items": [{"id": 4, "name": "丁"}],
    }
    payload.update(overrides)
    return _Envelope(**payload)  # pyright: ignore[reportArgumentType]  # 按 dict 载荷校验


@pytest.mark.kiwi_id(2223)
def test_contract_fields_validate_to_insertion_order_collections() -> None:
    """契约字段校验后落插入序集合类，且保输入插入序。"""
    envelope = _envelope()
    assert isinstance(envelope.items, ConcurrentStableList)
    assert isinstance(envelope.index, ConcurrentStableDict)
    assert isinstance(envelope.tags, ConcurrentStableSet)
    assert isinstance(envelope.optional_items, ConcurrentStableList)
    assert [item.id for item in envelope.items] == [1, 2]
    assert [item.id for item in envelope.optional_items] == [4]
    assert list(envelope.index) == ["k1"]
    assert envelope.tags.to_list() == ["beta", "alpha"]


@pytest.mark.kiwi_id(2223)
def test_contract_defaults_are_empty_collections_and_union_none() -> None:
    """空集合工厂常量默认值；`Optional` 联合形态可空。"""
    envelope = _Envelope()
    assert isinstance(envelope.items, ConcurrentStableList) and len(envelope.items) == 0
    assert isinstance(envelope.index, ConcurrentStableDict) and len(envelope.index) == 0
    assert isinstance(envelope.tags, ConcurrentStableSet) and len(envelope.tags) == 0
    assert envelope.optional_items is None


@pytest.mark.kiwi_id(2223)
def test_contract_validates_from_attributes_and_collection_instances() -> None:
    """`from_attributes` 校验：传入集合类实例（同型）直接可用。"""
    envelope = _Envelope.model_validate({"items": ConcurrentStableList([_Item(id=7, name="庚")])})
    assert isinstance(envelope.items, ConcurrentStableList)
    assert [item.id for item in envelope.items] == [7]


@pytest.mark.kiwi_id(2223)
def test_model_dump_keeps_collection_instances_and_stringifies_ids() -> None:
    """`model_dump()` 输出集合类实例，元素递归 dump 且 ID 字符串化。"""
    dumped = _envelope().model_dump()
    assert isinstance(dumped["items"], ConcurrentStableList)
    assert isinstance(dumped["index"], ConcurrentStableDict)
    assert isinstance(dumped["tags"], ConcurrentStableSet)
    assert isinstance(dumped["optional_items"], ConcurrentStableList)
    dumped_items = cast("ConcurrentStableList[dict[str, object]]", dumped["items"])
    assert list(dumped_items) == [
        {"id": "1", "name": "甲"},
        {"id": "2", "name": "乙"},
    ]
    assert dumped["index"]["k1"] == {"id": "3", "name": "丙"}
    assert dumped["tags"].to_list() == ["beta", "alpha"]


@pytest.mark.kiwi_id(2223)
def test_model_dump_json_outputs_arrays_and_objects() -> None:
    """`model_dump_json()` 输出内置容器（array / object），无集合类字符串泄漏。"""
    raw = _envelope().model_dump_json()
    assert "ConcurrentStable" not in raw
    assert json.loads(raw) == {
        "items": [{"id": "1", "name": "甲"}, {"id": "2", "name": "乙"}],
        "index": {"k1": {"id": "3", "name": "丙"}},
        "tags": ["beta", "alpha"],
        "optional_items": [{"id": "4", "name": "丁"}],
    }
    assert json.loads(_Envelope().model_dump_json()) == {
        "items": [],
        "index": {},
        "tags": [],
        "optional_items": None,
    }


@pytest.mark.kiwi_id(2223)
def test_contract_json_schema_matches_builtin_containers() -> None:
    """契约 JSON Schema 与内置容器逐字节一致，且不产生 `$defs` 命名引用漂移。"""
    actual = _Envelope.model_json_schema()["properties"]
    expected = _PlainEnvelope.model_json_schema()["properties"]
    for field in ("items", "index", "tags", "optional_items"):
        assert actual[field] == expected[field], field
    defs = _Envelope.model_json_schema().get("$defs", {})
    for name in ("ConcurrentStableList", "ConcurrentStableDict", "ConcurrentStableSet"):
        assert name not in defs


@pytest.mark.kiwi_id(2223)
def test_stringify_ids_rebuilds_collection_types() -> None:
    """`stringify_ids` 识别集合类并同型重组（映射键 `*_id` 递归字符串化）。"""
    items = stringify_ids(ConcurrentStableList([{"id": 1, "name": "a"}]))
    assert isinstance(items, ConcurrentStableList)
    assert items == [{"id": "1", "name": "a"}]

    mapping = stringify_ids(ConcurrentStableDict({"a_id": 1, "nested": {"b_id": 2}}))
    assert isinstance(mapping, ConcurrentStableDict)
    assert mapping["a_id"] == "1"
    assert mapping["nested"] == {"b_id": "2"}

    members = stringify_ids(ConcurrentStableSet(["x", "y"]))
    assert isinstance(members, ConcurrentStableSet)
    assert members == {"x", "y"}

    assert stringify_ids("id") == "id"
    assert stringify_ids([{"id": 1}]) == [{"id": "1"}]


@pytest.mark.kiwi_id(2223)
def test_base_object_convert_recognizes_collections() -> None:
    """`BaseObject._convert` 识别集合类（同型重组），普通类 `to_dict()` 不损坏序列化。"""
    converted = BaseObject._convert(ConcurrentStableList([1, 2]))  # pyright: ignore[reportPrivateUsage]
    assert isinstance(converted, ConcurrentStableList)
    assert converted == [1, 2]

    holder = _Holder(ConcurrentStableList([{"id": 7, "name": "甲"}]))
    dumped = holder.to_dict()
    assert isinstance(dumped["items"], ConcurrentStableList)
    assert dumped["items"] == [{"id": "7", "name": "甲"}]
    assert "ConcurrentStable" not in stable_json_dumps(dumped)
    assert json.loads(holder.to_json()) == {"items": [{"id": "7", "name": "甲"}]}


@pytest.mark.kiwi_id(2223)
def test_stable_json_dumps_normalizes_collections() -> None:
    """`stable_json_dumps` 前置规整集合类为内置容器（含嵌套），输出合法 JSON。"""
    raw = stable_json_dumps(
        {
            "items": ConcurrentStableList([{"id": 1}]),
            "index": ConcurrentStableDict({"k": ConcurrentStableSet(["a"])}),
        }
    )
    assert "ConcurrentStable" not in raw
    assert json.loads(raw) == {"items": [{"id": 1}], "index": {"k": ["a"]}}
