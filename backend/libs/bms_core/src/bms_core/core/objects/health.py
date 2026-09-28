"""值对象体系 · 健康链层：健康检查结果与汇总报告。

**链结构（按公共段成层，本次 1 层）**：

- `BaseHealthResultContract`（公共段 `ok`）——单项检查结果与整体报告共用结论位。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseHealthResultContract"]


@dataclass(frozen=True)
class BaseHealthResultContract(BaseValueObject):
    """健康结果契约（角色链层）：健康检查的**结论位**统一读面。

    公共段：`ok`（是否健康）——单项检查结果与整体汇总报告共用；探针 / 门禁按同一字段判定，
    无需区分「单项」与「报告」。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("ok",)
