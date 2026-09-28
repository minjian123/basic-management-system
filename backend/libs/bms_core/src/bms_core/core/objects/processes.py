"""值对象体系 · 流程链层：流程定义与流程实例的共同归属键。

**链结构（按公共段成层，本次 1 层）**：

- `BaseProcessContract`（公共段 `definition_key`）——定义侧与实例侧共用流程归属键。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseProcessContract"]


@dataclass(frozen=True)
class BaseProcessContract(BaseValueObject):
    """流程契约（角色链层）：流程定义与流程实例的**归属键**统一读面。

    公共段：`definition_key`（流程定义键）——实例按此键回溯定义（`ProcessInstance.definition_key` ↔
    `ProcessDefinition.definition_key`），调用方无需区分两侧字段名。
    """

    COMMON_FIELDS: ClassVar[tuple[str, ...]] = ("definition_key",)
