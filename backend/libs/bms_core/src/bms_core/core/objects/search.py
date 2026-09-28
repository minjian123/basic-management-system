"""值对象体系 · 检索链层：检索查询与文档。

**链结构（按公共段成层，本次 1 层）**：

- `BaseSearchContract`（公共段 `index`）——查询侧与文档侧共用索引位。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseSearchContract"]


@dataclass(frozen=True)
class BaseSearchContract(BaseValueObject):
    """检索契约（角色链层）：检索**索引位**统一读面。

    公共段：`index`（目标索引名）——查询（`SearchQuery`）与文档（`SearchDocument`）共用，
    检索后端按同一索引名路由。

    说明：`SearchResult` **不属本层**（字段为 `hits` / `total`、无 `index`，见 09_03 设计 §2 注 5）。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("index",)
