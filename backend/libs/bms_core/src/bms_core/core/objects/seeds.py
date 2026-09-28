"""值对象体系 · 种子数据链层：带多语言载荷的字典种子。

**链结构（按公共段成层，本次 1 层）**：

- `BaseI18nSeedContract`（公共段 `i18n`）——种子项与种子类型共用多语言载荷位。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseI18nSeedContract"]


@dataclass(frozen=True)
class BaseI18nSeedContract(BaseValueObject):
    """种子数据契约（角色链层）：字典种子项的**多语言载荷**统一读面。

    公共段：`i18n`（语言 → 文案映射，缺省空映射）——种子项与种子类型共用；
    其余字段（编码 / 取值 / 排序 / 明细）各自声明，不入公共段。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("i18n",)
