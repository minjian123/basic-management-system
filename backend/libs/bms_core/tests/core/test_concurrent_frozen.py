"""不可变集合形态与哈希不变量回归（Kiwi 2327）：`BaseImmutable` + 三形态 + 内容哈希 + 派生运算。

覆盖（08_05 详细设计 §3.3 / §3.4 / §3.5）：

1. **构造期写、构造后恒冻结**：三形态构造走分段写路径，构造完成即冻结，此后一切写操作抛 `TypeError`；
2. **内容哈希与 `eq` 对齐**：列表按序、集合与映射无序；哈希值缓存生效；嵌套一致；
3. **可作 `dict` 键 / `set` 去重**：同内容实例去重为 1；
4. **派生运算不撞冻结**：`|` / `union` / `intersection` / `difference` / `symmetric_difference` 返回同类
   不可变实例、保插入序、原实例不变；
5. **可变形态不可哈希**：`ConcurrentStable*` 三者 `hash()` 抛 `TypeError`（与内置 `list` / `dict` / `set` 一致）。
"""

import copy
from typing import Any

import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableFrozenList,
    ConcurrentStableFrozenSet,
    ConcurrentStableList,
    ConcurrentStableSet,
)
from bms_core.core.locking import LockStrategy

pytestmark = pytest.mark.kiwi_id(2327)


# --------------------------------------------------------------------------- 构造期写、构造后冻结


@pytest.mark.parametrize(
    ("factory", "items"),
    [
        (ConcurrentStableFrozenList, [3, 1, 2]),
        (ConcurrentStableFrozenSet, [3, 1, 2]),
        (ConcurrentStableFrozenDict, [("a", 1), ("b", 2)]),
    ],
)
def test_frozen_forms_accept_items_at_construction(factory: Any, items: ConcurrentStableList[Any]) -> None:
    """三形态构造期可写：初始元素按给定顺序成为插入序。"""
    instance = factory(items)
    assert len(instance) == len(items)
    assert instance.collection_kind == "stable_frozen"


@pytest.mark.parametrize(
    ("factory", "items"),
    [
        (ConcurrentStableFrozenList, [1, 2]),
        (ConcurrentStableFrozenSet, [1, 2]),
        (ConcurrentStableFrozenDict, [("a", 1)]),
    ],
)
def test_frozen_forms_reject_writes_after_construction(factory: Any, items: ConcurrentStableList[Any]) -> None:
    """构造后恒冻结：写操作一律抛 `TypeError`（与 `freeze()` 同语义）。"""
    instance = factory(items)
    with pytest.raises(TypeError, match="只读快照"):
        instance.clear()
    if hasattr(instance, "add"):
        with pytest.raises(TypeError, match="只读快照"):
            instance.add(3)
    if isinstance(instance, ConcurrentStableFrozenDict):
        with pytest.raises(TypeError, match="只读快照"):
            instance["b"] = 2
        with pytest.raises(TypeError, match="只读快照"):
            del instance["a"]


def test_frozen_list_rejects_inplace_append_and_iadd() -> None:
    """不可变列表：`append` / `+=` 均抛 `TypeError`（`+=` 会写自身，故显式拒绝）。"""
    instance = ConcurrentStableFrozenList([1, 2])
    with pytest.raises(TypeError, match="只读快照"):
        instance.append(3)
    with pytest.raises(TypeError, match="不可变形态"):
        instance += [3]


def test_frozen_dict_rejects_inplace_or() -> None:
    """不可变字典：`|=` 抛 `TypeError`（原地合并会写自身）。"""
    instance = ConcurrentStableFrozenDict({"a": 1})
    with pytest.raises(TypeError, match="不可变形态"):
        instance |= {"b": 2}


def test_frozen_freeze_returns_self() -> None:
    """`freeze()` 幂等：不可变形态返回自身（无需再复制一份冻结副本）。"""
    instance = ConcurrentStableFrozenList([1, 2])
    assert instance.freeze() is instance


def test_frozen_forms_accept_non_sharded_strategy() -> None:
    """非 `SHARDED` 策略同样可构造（`_spawn` / `_mutable_spawn` 策略保真分支）。"""
    frozen_list = ConcurrentStableFrozenList([1, 2], strategy=LockStrategy.RW)
    assert frozen_list.to_list() == [1, 2]
    assert frozen_list._mutable_spawn().to_list() == [1, 2]  # pyright: ignore[reportPrivateUsage]  # 用例专门验证内部机制
    frozen_set = ConcurrentStableFrozenSet([1], strategy=LockStrategy.RW)
    assert frozen_set.to_list() == [1]
    assert frozen_set._mutable_spawn().to_list() == [1]  # pyright: ignore[reportPrivateUsage]  # 用例专门验证内部机制
    frozen_dict = ConcurrentStableFrozenDict({"a": 1}, strategy=LockStrategy.RW)
    assert frozen_dict.to_list() == [("a", 1)]
    assert frozen_dict._mutable_spawn().to_list() == [("a", 1)]  # pyright: ignore[reportPrivateUsage]  # 用例专门验证内部机制


# --------------------------------------------------------------------------- 内容哈希与 eq 对齐


def test_frozen_list_hash_is_order_sensitive() -> None:
    """列表哈希按序：`[1, 2]` 与 `[2, 1]` 相等性为假、哈希不同（与 `__eq__` 对齐）。"""
    left = ConcurrentStableFrozenList([1, 2])
    right = ConcurrentStableFrozenList([2, 1])
    assert left != right
    assert hash(left) != hash(right)
    assert hash(left) == hash(ConcurrentStableFrozenList([1, 2]))


def test_frozen_set_hash_is_order_insensitive() -> None:
    """集合哈希无序：不同插入序的同内容实例相等且哈希相同。"""
    left = ConcurrentStableFrozenSet([1, 2, 3])
    right = ConcurrentStableFrozenSet([3, 2, 1])
    assert left == right
    assert hash(left) == hash(right)


def test_frozen_dict_hash_is_order_insensitive() -> None:
    """映射哈希无序：不同插入序的同内容实例相等且哈希相同。"""
    left = ConcurrentStableFrozenDict({"a": 1, "b": 2})
    right = ConcurrentStableFrozenDict({"b": 2, "a": 1})
    assert left == right
    assert hash(left) == hash(right)


def test_frozen_hash_is_cached() -> None:
    """哈希值缓存：二次调用直接命中缓存（首次计算后写回 `_hash_cache`）。"""
    instance = ConcurrentStableFrozenList([1, 2, 3])
    first = hash(instance)
    assert instance._hash_cache == first  # pyright: ignore[reportPrivateUsage]  # 用例专门验证内部机制
    assert hash(instance) == first


def test_frozen_forms_work_as_dict_keys_and_set_members() -> None:
    """可作 `dict` 键 / `set` 成员：同内容实例命中同一桶、去重生效。"""
    key = ConcurrentStableFrozenDict({"a": 1})
    mapping = {key: "value"}
    assert mapping[ConcurrentStableFrozenDict({"a": 1})] == "value"
    assert len({ConcurrentStableFrozenSet([1, 2]), ConcurrentStableFrozenSet([2, 1])}) == 1
    assert len({ConcurrentStableFrozenList([1, 2]), ConcurrentStableFrozenList([1, 2])}) == 1


def test_frozen_nested_hash_consistent() -> None:
    """嵌套一致：含嵌套不可变集合的实例同内容哈希相同。"""
    left = ConcurrentStableFrozenList([ConcurrentStableFrozenDict({"a": 1}), ConcurrentStableFrozenSet([2])])
    right = ConcurrentStableFrozenList([ConcurrentStableFrozenDict({"a": 1}), ConcurrentStableFrozenSet([2])])
    assert left == right
    assert hash(left) == hash(right)
    assert {left: "hit"}[right] == "hit"


def test_frozen_hash_payload_handles_plain_containers() -> None:
    """哈希规范化覆盖内置容器（`hash_payload` 的映射 / 集合 / 序列三分支）。"""
    from bms_core.core.concurrent import hash_payload

    assert hash_payload({"a": 1}) == hash_payload({"a": 1})
    assert hash_payload({1, 2}) == hash_payload({2, 1})
    assert hash_payload([1, 2]) != hash_payload([2, 1])
    assert hash_payload("plain") == "plain"


# --------------------------------------------------------------------------- 派生运算


def test_frozen_set_union_does_not_hit_freeze() -> None:
    """`union` 走「先算可变临时实例、最后一次冻结」：结果同类冻结、保插入序、原实例不变。"""
    base = ConcurrentStableFrozenSet([1, 2])
    merged = base.union([3, 2])
    assert type(merged) is ConcurrentStableFrozenSet
    assert merged.to_list() == [1, 2, 3]
    assert base.to_list() == [1, 2]
    assert merged._frozen is True  # pyright: ignore[reportPrivateUsage]  # 用例专门验证内部机制


def test_frozen_set_operators_return_frozen_instances() -> None:
    """集合运算符（`|` / `&` / `-` / `^`）均返回同类不可变实例。"""
    base = ConcurrentStableFrozenSet([1, 2, 3])
    assert base | {4}.__class__({4}) == ConcurrentStableFrozenSet([1, 2, 3, 4])
    assert base & ConcurrentStableFrozenSet([2, 3]) == ConcurrentStableFrozenSet([2, 3])
    assert base - ConcurrentStableFrozenSet([1]) == ConcurrentStableFrozenSet([2, 3])
    assert base ^ ConcurrentStableFrozenSet([3, 4]) == ConcurrentStableFrozenSet([1, 2, 4])
    for result in (
        base | ConcurrentStableFrozenSet([4]),
        base & ConcurrentStableFrozenSet([2]),
        base - ConcurrentStableFrozenSet([1]),
        base ^ ConcurrentStableFrozenSet([4]),
    ):
        assert type(result) is ConcurrentStableFrozenSet
        assert result._frozen is True  # pyright: ignore[reportPrivateUsage]  # 用例专门验证内部机制


def test_frozen_set_other_derivations_return_frozen() -> None:
    """`intersection` / `difference` / `symmetric_difference` 返回同类不可变实例。"""
    base = ConcurrentStableFrozenSet([1, 2, 3])
    assert base.intersection([2, 3, 4]) == ConcurrentStableFrozenSet([2, 3])
    assert base.difference([1]) == ConcurrentStableFrozenSet([2, 3])
    assert base.symmetric_difference([3, 4]) == ConcurrentStableFrozenSet([1, 2, 4])
    for result in (
        base.intersection([2]),
        base.difference([1]),
        base.symmetric_difference([4]),
    ):
        assert type(result) is ConcurrentStableFrozenSet
        assert result._frozen is True  # pyright: ignore[reportPrivateUsage]  # 用例专门验证内部机制


def test_frozen_dict_or_does_not_hit_freeze() -> None:
    """`d | other` 返回同类不可变实例（同键覆盖、插入位置不变）。"""
    base = ConcurrentStableFrozenDict({"a": 1})
    merged = base | {"b": 2}
    assert type(merged) is ConcurrentStableFrozenDict
    assert merged.to_dict() == {"a": 1, "b": 2}
    assert base.to_dict() == {"a": 1}
    assert merged._frozen is True  # pyright: ignore[reportPrivateUsage]  # 用例专门验证内部机制


def test_frozen_list_add_returns_frozen_instance() -> None:
    """`l + items` 返回同类不可变实例（原实例不变）。"""
    base = ConcurrentStableFrozenList([1, 2])
    merged = base.__add__([3])  # 显式调用：本用例专门验证 `+` 的派生语义（RUF005 的列表展开建议不适用）
    assert type(merged) is ConcurrentStableFrozenList
    assert merged.to_list() == [1, 2, 3]
    assert base.to_list() == [1, 2]
    assert merged._frozen is True  # pyright: ignore[reportPrivateUsage]  # 用例专门验证内部机制


def test_frozen_copy_and_deepcopy_return_independent_instances() -> None:
    """`copy.copy` / `copy.deepcopy` 返回内容独立、仍冻结的同类实例。"""
    base = ConcurrentStableFrozenList([1, [2]])
    shallow = copy.copy(base)
    deep = copy.deepcopy(base)
    assert shallow.to_list() == base.to_list()
    assert deep.to_list() == base.to_list()
    assert shallow is not base
    assert deep is not base
    assert shallow._frozen is True and deep._frozen is True  # pyright: ignore[reportPrivateUsage]  # 用例专门验证冻结标记


# --------------------------------------------------------------------------- 可变形态不可哈希


@pytest.mark.parametrize(
    ("factory", "items"),
    [
        (ConcurrentStableList, [1, 2]),
        (ConcurrentStableSet, [1, 2]),
        (ConcurrentStableDict, [("a", 1)]),
    ],
)
def test_mutable_forms_are_unhashable(factory: Any, items: ConcurrentStableList[Any]) -> None:
    """可变形态不可哈希（与内置 `list` / `dict` / `set` 一致）。"""
    instance = factory(items)
    assert factory.__hash__ is None
    with pytest.raises(TypeError, match="unhashable"):
        hash(instance)
