"""值对象体系 · 字段规格链层：字段可选性规格。

**链结构（按公共段成层，本次 1 层）**：

- `BaseFieldSpecContract`（公共段 `required`）——导入列规格 / 事件字段规格共用可选性位。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseFieldSpecContract"]


@dataclass(frozen=True)
class BaseFieldSpecContract(BaseValueObject):
    """字段规格契约（角色链层）：字段的**可选性规格**。

    公共段：`required`（必填位）——导入列规格（`ColumnSpec`）与事件字段规格（`EventFieldSpec`）共用；
    其余字段（列名 / 标题 / 类型）各自声明，不入公共段。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("required",)
