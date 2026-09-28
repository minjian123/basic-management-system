"""值对象体系 · 登记记录链层：目录 / 登记表行的不可变记录。

**链结构（按公共段成层，本次 1 层）**：

- `BaseRegistryRecordContract`（**公共段为成对构造钩子** `from_row()`）——模块目录记录与表归属记录共用
  「ORM 行 → 不可变记录」的唯一受控构造入口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Self

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseRegistryRecordContract"]


@dataclass(frozen=True)
class BaseRegistryRecordContract(BaseValueObject, ABC):
    """登记记录契约（角色链层）：登记表行 → 不可变记录。

    **公共段为成对构造钩子**：`from_row(row)` 是唯一受控构造入口（ORM 行或任意同构对象 → 记录），
    由各成员声明字段与「字段 ← 行属性」映射；**无公共字段**（模块目录记录与表归属记录字段集互不相同，
    强行抽字段会造出只被一个成员满足的假公共段）。
    """

    @classmethod
    @abstractmethod
    def from_row(cls, row: object) -> Self:
        """按登记字段从 ORM 行（或任意同构对象）构造记录。

        Args:
            row: 具备登记字段的对象（如 `SysModule` / `SysTableOwnership` 行）。

        Returns:
            Self: 登记记录。

        Raises:
            AttributeError: 行对象缺少必需登记字段。
        """
