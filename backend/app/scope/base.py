"""数据范围能力域：数据范围注入基座契约（规则由 RBAC 提供，阶段五回补）。"""

from abc import ABC, abstractmethod

from app.core.base import BaseObject


class DataScope(BaseObject, ABC):
    """数据范围契约：读过滤条件 + 写校验（写读双向）。"""

    @abstractmethod
    def read_predicate(self) -> object:
        """读过滤条件（供仓储拼接查询；None 表示不过滤）。"""

    @abstractmethod
    def allow_write(self, values: dict[str, object]) -> bool:
        """写校验：数据是否落在授权范围内。

        Args:
            values: 待写入字段值。

        Returns:
            bool: 允许为 True。
        """


class NullDataScope(DataScope):
    """占位数据范围：无过滤、恒定允许（未接入 RBAC 时使用）。"""

    def read_predicate(self) -> object:
        """无过滤条件。

        Returns:
            object: None（不过滤）。
        """
        return None

    def allow_write(self, values: dict[str, object]) -> bool:
        """恒定允许写入。

        Args:
            values: 待写入字段值（占位不校验）。

        Returns:
            bool: True。
        """
        return True
