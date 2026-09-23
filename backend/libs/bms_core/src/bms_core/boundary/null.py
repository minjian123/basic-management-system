"""数据所有权守卫缺省实现（Null Object）：恒定无越界、不安装监听。"""

from bms_core.boundary.assess import OwnershipViolation
from bms_core.boundary.base import BaseDataOwnershipGuard, OwnershipStats
from bms_core.core.capability import BaseNullObject

__all__ = ["NullDataOwnershipGuard"]


class NullDataOwnershipGuard(BaseDataOwnershipGuard, BaseNullObject):
    """占位守卫：恒定判定无越界、计数恒零、不安装 SQLAlchemy 监听（未配置真实实现时使用）。"""

    def assess(self, statement: str, *, service: str) -> tuple[OwnershipViolation, ...]:
        """恒定返回无越界。

        Args:
            statement: SQL 语句（占位忽略）。
            service: 当前服务标识（占位忽略）。

        Returns:
            tuple[OwnershipViolation, ...]: 空元组。
        """
        del statement, service
        return ()

    def snapshot(self) -> OwnershipStats:
        """计数恒零。

        Returns:
            OwnershipStats: 全零快照。
        """
        return OwnershipStats()
