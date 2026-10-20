"""哈希分工与值对象字段归位回归（Kiwi 2328）：可变形态不可哈希 + frozen 值对象字段落不可变形态。

覆盖（08_05 详细设计 §3.4）：

1. **哈希分工**：可变形态（`ConcurrentStable*`）`__hash__ = None`、`hash()` 抛 `TypeError`（与内置
   `list` / `dict` / `set` 一致）；内容哈希只给不可变形态（`ConcurrentStableFrozen*`）；
2. **值对象字段归位**：`BaseValueObject`（frozen dataclass）的集合字段落不可变形态后
   `len({同内容两实例}) == 1`（此前为 2 —— `eq` 相等而 `hash` 不同）；
3. **frozen 语义不变**：归位后 frozen dataclass 赋值仍抛 `FrozenInstanceError`。

> 值对象清单见 08_05 详细设计 §3.4「值对象字段归位」表（16 处主清单 + 08_05 扩面至全部 frozen 值对象
> 集合字段）；本用例取各类**代表性实例**断言不变量，不逐类枚举（逐类断言由各模块自身用例覆盖）。
"""

import dataclasses

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.objects import BaseValueObject

pytestmark = pytest.mark.kiwi_id(2328)


@dataclasses.dataclass(frozen=True)
class _WithFrozenFields(BaseValueObject):
    """测试用 frozen 值对象（集合字段一律落不可变形态）。"""

    items: ConcurrentStableFrozenList[str] = dataclasses.field(
        default_factory=lambda: ConcurrentStableFrozenList[str]()
    )
    codes: ConcurrentStableFrozenSet[str] = dataclasses.field(default_factory=lambda: ConcurrentStableFrozenSet[str]())
    mapping: ConcurrentStableFrozenDict[str, int] = dataclasses.field(
        default_factory=lambda: ConcurrentStableFrozenDict[str, int]()
    )


def test_hash_split_mutable_forms_unhashable() -> None:
    """哈希分工（可变侧）：三形态 `__hash__ = None` 且 `hash()` 抛 `TypeError`。"""
    for instance in (
        ConcurrentStableList([1]),
        ConcurrentStableSet([1]),
        ConcurrentStableDict({"a": 1}),
    ):
        assert type(instance).__hash__ is None
        with pytest.raises(TypeError, match="unhashable"):
            hash(instance)


def test_hash_split_frozen_forms_hashable() -> None:
    """哈希分工（不可变侧）：三形态可哈希且与 `eq` 语义对齐。"""
    assert hash(ConcurrentStableFrozenList([1])) == hash(ConcurrentStableFrozenList([1]))
    assert hash(ConcurrentStableFrozenSet([1])) == hash(ConcurrentStableFrozenSet([1]))
    assert hash(ConcurrentStableFrozenDict({"a": 1})) == hash(ConcurrentStableFrozenDict({"a": 1}))


def test_value_object_field_placement_dedupes_by_content() -> None:
    """值对象字段归位：同内容两实例 `eq` 相等且 `hash` 相同 ⇒ `set` 去重为 1。"""
    left = _WithFrozenFields(
        items=ConcurrentStableFrozenList(["a", "b"]),
        codes=ConcurrentStableFrozenSet(["x", "y"]),
        mapping=ConcurrentStableFrozenDict({"k": 1}),
    )
    right = _WithFrozenFields(
        items=ConcurrentStableFrozenList(["a", "b"]),
        codes=ConcurrentStableFrozenSet(["y", "x"]),
        mapping=ConcurrentStableFrozenDict({"k": 1}),
    )
    assert left == right
    assert hash(left) == hash(right)
    assert len({left, right}) == 1
    assert {left: "hit"}[right] == "hit"


def test_value_object_field_placement_keeps_frozen_semantics() -> None:
    """归位后 frozen 语义不变：字段赋值仍抛 `FrozenInstanceError`。"""
    instance = _WithFrozenFields(items=ConcurrentStableFrozenList(["a"]))
    with pytest.raises(dataclasses.FrozenInstanceError):
        instance.items = ConcurrentStableFrozenList(["b"])  # type: ignore[misc]


def test_value_object_fields_are_immutable_forms() -> None:
    """归位后字段类型为不可变形态（构造后写抛 `TypeError`）。"""
    instance = _WithFrozenFields(items=ConcurrentStableFrozenList(["a"]))
    assert type(instance.items) is ConcurrentStableFrozenList
    assert type(instance.codes) is ConcurrentStableFrozenSet
    assert type(instance.mapping) is ConcurrentStableFrozenDict
    with pytest.raises(TypeError, match="只读快照"):
        instance.items.append("b")


def test_mutable_collection_field_would_break_invariant() -> None:
    """反证（不变量为何需要归位）：可变集合字段使 `eq` 相等而 `hash` 不同 ⇒ 去重失效。"""

    @dataclasses.dataclass(frozen=True)
    class _MutableField(BaseValueObject):
        items: ConcurrentStableList[str] = dataclasses.field(default_factory=lambda: ConcurrentStableList[str]())

    left = _MutableField(items=ConcurrentStableList(["a"]))
    right = _MutableField(items=ConcurrentStableList(["a"]))
    assert left == right
    with pytest.raises(TypeError, match="unhashable"):
        hash(left)


@pytest.mark.parametrize(
    "value_object",
    [
        # 08_05 主清单代表性值对象：字段落不可变形态后应可哈希（`hash()` 不抛错）
        "bms_core.audit.hashchain:HashChainEntry",
        "bms_core.db.migration:MigrationChain",
        "bms_core.idp.registry:IdentityProviderSpec",
        "bms_core.query.base:QueryResult",
        "bms_core.search.base:SearchHit",
        "bms_core.servicecall.base:ServiceRequest",
        "bms_core.tracing.base:SpanContext",
        "bms_core.transaction.base:BranchOp",
        "bms_core.transfer.importer:ImportResult",
        "bms_core.ws.base:RealtimeEvent",
    ],
)
def test_named_value_objects_collection_fields_are_hashable(value_object: str) -> None:
    """主清单值对象的集合字段均为不可变形态（字段类型可哈希，`hash(field)` 不抛错）。"""
    import importlib

    module_name, class_name = value_object.split(":")
    cls = getattr(importlib.import_module(module_name), class_name)
    assert dataclasses.is_dataclass(cls)
    for field in dataclasses.fields(cls):
        annotation = str(field.type)
        if "ConcurrentStable" not in annotation:
            continue
        assert "ConcurrentStableFrozen" in annotation or field.name.startswith("_"), (
            f"{class_name}.{field.name} 仍为可变集合类：{annotation}"
        )
