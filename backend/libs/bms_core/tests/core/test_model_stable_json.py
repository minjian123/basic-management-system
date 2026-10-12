"""`models/base.py` 稳定 JSON 类型用例：JSON 读回集合类递归转换（含内置 set / frozenset 分支）。"""

from __future__ import annotations

from typing import cast

import pytest
from sqlalchemy.dialects import sqlite

from bms_core.core.concurrent import ConcurrentStableDict, ConcurrentStableList, ConcurrentStableSet
from bms_core.models.base import StableJson, to_stable_value


@pytest.mark.kiwi_id(1050)
def test_to_stable_value_recurses_mapping_and_sequence() -> None:
    """映射 / 列表递归转插入序集合类（嵌套保持同型）。"""
    mapped = to_stable_value({"a": 1, "b": {"c": 2}})
    assert isinstance(mapped, ConcurrentStableDict)
    assert mapped == {"a": 1, "b": {"c": 2}}

    listed = to_stable_value([1, {"a": 2}])
    assert isinstance(listed, ConcurrentStableList)
    assert listed == [1, {"a": 2}]


@pytest.mark.kiwi_id(1050)
def test_to_stable_value_converts_builtin_sets() -> None:
    """内置 `set` / `frozenset` 递归转 `ConcurrentStableSet`（JSON 读回不产生，直调补齐分支）。"""
    as_set = to_stable_value({1, 2})
    assert isinstance(as_set, ConcurrentStableSet)
    assert as_set == {1, 2}

    as_frozen = to_stable_value(frozenset({3, 4}))
    assert isinstance(as_frozen, ConcurrentStableSet)
    assert as_frozen == {3, 4}

    nested = to_stable_value({"k": {5}})
    assert isinstance(nested, ConcurrentStableDict)
    assert isinstance(nested["k"], ConcurrentStableSet)
    assert nested["k"] == {5}


@pytest.mark.kiwi_id(1050)
def test_to_stable_value_keeps_scalars() -> None:
    """标量 / 字符串 / bytes 原样返回（不包装）。"""
    assert to_stable_value(1) == 1
    assert to_stable_value("x") == "x"
    assert to_stable_value(b"x") == b"x"
    assert to_stable_value(None) is None


@pytest.mark.kiwi_id(1050)
def test_stable_json_bind_and_result_roundtrip() -> None:
    """`StableJson` 列类型：落库规整为内置容器，读回递归转为插入序集合类；None 两端直通。"""
    column: StableJson[object] = StableJson()
    dialect = sqlite.dialect()

    bound = column.process_bind_param(ConcurrentStableDict({"a": ConcurrentStableList([1, 2])}), dialect)
    assert bound == {"a": [1, 2]}
    assert column.process_bind_param(None, dialect) is None

    read = column.process_result_value({"a": [1, 2]}, dialect)
    assert isinstance(read, ConcurrentStableDict)
    assert isinstance(cast("ConcurrentStableDict[str, object]", read)["a"], ConcurrentStableList)
    assert column.process_result_value(None, dialect) is None
