"""scope 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 app.scope.base.py 迁入）。"""

from app.core.capability import BaseNullObject
from app.scope.base import DataScope

__all__ = [
    "NullDataScope",
]


class NullDataScope(DataScope, BaseNullObject):
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
