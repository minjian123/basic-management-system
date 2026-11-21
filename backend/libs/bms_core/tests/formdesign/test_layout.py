"""布局结构的值对象归位（基座体系 §3.1，Kiwi 2535）：布局模型全为冻结值对象。"""

from __future__ import annotations

import dataclasses

import pytest

from bms_core.core.objects import BaseValueObject
from bms_core.formdesign.layout import (
    FormLayout,
    LayoutDetailColumn,
    LayoutDictAdvanced,
    LayoutFieldRef,
    LayoutGroup,
    LayoutMain,
    LayoutQuery,
    LayoutSection,
)

pytestmark = pytest.mark.kiwi_id(2535)

_LAYOUT_VALUE_TYPES = (
    LayoutFieldRef,
    LayoutGroup,
    LayoutSection,
    LayoutMain,
    LayoutQuery,
    LayoutDetailColumn,
    LayoutDictAdvanced,
    FormLayout,
)
"""布局结构的值对象类型（字段引用 → 整体布局）。"""


@pytest.mark.parametrize("value_type", _LAYOUT_VALUE_TYPES)
def test_layout_structures_are_frozen_value_objects(value_type: type[BaseValueObject]) -> None:
    """布局结构均属值对象体系，且为不可变数据类（写入即拒绝）。"""
    assert issubclass(value_type, BaseValueObject)
    assert dataclasses.is_dataclass(value_type)
    probe = object.__new__(value_type)
    with pytest.raises(dataclasses.FrozenInstanceError):
        probe.__setattr__("probe", True)
