"""值对象体系 · 判定链层：一次放行 / 拒绝判定的统一读面。

**链结构（按公共段成层，本次 1 层）**：

- `BaseDecisionContract`（公共段 `allowed`）——限流 / 重放 / 边缘信任三处判定共用结论字段名。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseDecisionContract"]


@dataclass(frozen=True)
class BaseDecisionContract(BaseValueObject):
    """判定契约（角色链层）：限流 / 重放 / 边缘信任的统一判定读面。

    公共段：`allowed`（`True` 放行、`False` 拒绝）——三处判定结论统一以该名表达，调用方无需按来源记名字。

    `reason`（拒绝原因）为**可选说明位**，不列入公共段：`RateLimitDecision` 以计数位（`limit` /
    `remaining` / `reset_after`）表达而不带原因，强行列入会让公共段在其上不成立。

    历史命名更正（09_03 批次 ⑤，设计 §5 字段名统一项）：`EdgeTrustDecision.trusted` → `allowed`。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("allowed",)
