"""值对象体系 · 运维报告链层：运维 / 巡检命令的报告行输出。

**链结构（按公共段成层，本次 1 层）**：

- `BaseOpsReportContract`（**公共段为成对输出方法** `describe()`）——数据库目标 / 库数量统计 /
  连接预算行共用同一「单行报告文本」入口。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from bms_core.core.objects.roots import BaseValueObject

__all__ = ["BaseOpsReportContract"]


@dataclass(frozen=True)
class BaseOpsReportContract(BaseValueObject, ABC):
    """运维报告契约（角色链层）：运维 / 巡检命令的**报告行**输出。

    公共段为**成对输出方法** `describe()`（抽象入口）：成员各自渲染「单行报告文本」，
    运维命令按此统一输出，无需按类型分支拼装。

    说明：`MigrationSummary` **不属本层**（以 `exit_code` 收口、无 `describe()`，见 09_03 设计 §2 注 4）。
    """

    @abstractmethod
    def describe(self) -> str:
        """生成单行报告文本（运维命令统一渲染入口）。

        Returns:
            str: 报告行文本。
        """
