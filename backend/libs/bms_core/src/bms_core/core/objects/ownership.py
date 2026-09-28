"""值对象体系 · 数据所有权链层：越界登记与例外登记。

**链结构（按公共段成层，本次 1 层）**：

- `BaseOwnershipContract`（公共段 `service` + `PREFIX_FIELD` 映射）——越界与例外登记共用归属服务位。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseOwnershipContract"]


@dataclass(frozen=True)
class BaseOwnershipContract(BaseValueObject):
    """数据所有权契约（角色链层）：表归属登记的**归属服务位**统一读面。

    公共段：`service`（声明归属的服务）——越界登记（`OwnershipViolation`）与例外登记
    （`OwnershipException`）共用。

    前缀位字段名历史不统一（`OwnershipViolation.prefix` / `OwnershipException.target_prefix`）——
    以 `PREFIX_FIELD` 声明承载字段（调用方按 `PREFIX_FIELD` 取用）；**不提供统一读取属性**：
    `prefix` 会与 `OwnershipViolation.prefix`（dataclass 字段）同名冲突（同租户层 `code` 的处理口径）。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("service",)
    PREFIX_FIELD: ClassVar[str] = ""
    """本类承载「前缀位」的字段名（成员声明）。"""
