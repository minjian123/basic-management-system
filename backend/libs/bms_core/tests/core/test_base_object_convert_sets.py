"""`BaseObject` 字段递归转换的集合分支补齐用例（`bms_core/core/base.py`）。"""

from __future__ import annotations

from typing import Any, cast

from bms_core.core.base import BaseObject
from bms_core.core.concurrent import ConcurrentStableSet


def test_convert_handles_builtin_and_baseobject_sets() -> None:
    """递归转换：内置 `set` 按列表输出；基座集合类（`BaseObject`）同型重组。"""
    assert BaseObject._convert({1, 2}) == [1, 2]  # pyright: ignore[reportPrivateUsage]
    rebuilt = BaseObject._convert(ConcurrentStableSet([1, 2]))  # pyright: ignore[reportPrivateUsage]
    assert list(cast("Any", rebuilt)) == [1, 2]
