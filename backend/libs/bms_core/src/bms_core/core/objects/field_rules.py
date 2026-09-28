"""值对象体系 · 字段规则链层：按字段定向的规则。

**链结构（按公共段成层，本次 1 层）**：

- `BaseFieldRuleContract`（公共段 `field`）——脱敏规则与数据范围条件的定向字段位。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseFieldRuleContract"]


@dataclass(frozen=True)
class BaseFieldRuleContract(BaseValueObject):
    """字段规则契约（角色链层）：**按字段定向**的规则统一读面。

    公共段：`field`（规则作用的字段名）——脱敏规则（`MaskRule`）与数据范围条件（`ScopeCondition`）
    共用；规则引擎按同一字段名定位作用目标。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("field",)
