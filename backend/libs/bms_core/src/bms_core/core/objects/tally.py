"""值对象体系 · 计数汇总链层：多项计数的只读汇总结果。

**链结构（按公共段成层，本次 1 层）**：

- `BaseTallyContract`（**不变式**：`COUNT_FIELDS` 声明**整数计数位** + `counts` 只读映射）——发件汇总 /
  边界统计等**计数字段**的汇总结果共用统一遍历面。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseTallyContract"]


@dataclass(frozen=True)
class BaseTallyContract(BaseValueObject):
    """计数汇总契约（角色链层）：多项计数的**只读汇总**结果。

    **公共段为不变式**（不是单个字段）：成员以 `COUNT_FIELDS` 声明本类的**计数位**字段名，
    层以 `counts` 提供统一遍历面（供报表 / 日志统一格式化）。

    成员：`DispatchResult`（发件汇总）/ `OwnershipStats`（守卫计数快照）。

    为什么**不**提供派生 `total`：各成员「总数」语义不同——`DispatchResult.backlog` 是待发而 `dead` 是
    终态；强行求和会给出错误语义（09_03 设计 §2 注 5 实证）。因此本层只承接「有哪些**整数计数位**」，
    不替成员定义汇总口径。

    为什么**不含** `ImportResult` / `MigrationSummary`：二者字段是**明细元组**（`rows` / `errors`、
    `succeeded` / `skipped` / `failed` 均为 `tuple[...]`）而非计数，与「计数字段」语义不同 → 保持单类链。
    """

    COUNT_FIELDS: ClassVar[tuple[str, ...]] = ()
    """本类计数位字段名（成员声明；`counts` 按此汇总）。"""

    @property
    def counts(self) -> Mapping[str, int]:
        """计数位 → 计数值的只读映射（按 `COUNT_FIELDS` 汇总）。

        Returns:
            Mapping[str, int]: 计数位映射（键顺序与 `COUNT_FIELDS` 一致）。
        """
        return {name: getattr(self, name) for name in self.COUNT_FIELDS}
