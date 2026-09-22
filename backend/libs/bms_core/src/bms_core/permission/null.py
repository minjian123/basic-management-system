"""permission 能力域缺省实现（Null Object）：占位返回、无副作用（02-3 自 bms_core.permission.base.py 迁入）。"""

from bms_core.core.capability import BaseNullObject
from bms_core.permission.base import BasePermissionChecker

__all__ = [
    "NullPermissionChecker",
]


class NullPermissionChecker(BasePermissionChecker, BaseNullObject):
    """占位权限校验：恒定允许（不读权限数据，未接入 RBAC 时使用）。"""

    def check(self, code: str) -> bool:
        """恒定允许。

        Args:
            code: 权限码（占位不校验）。

        Returns:
            bool: True。
        """
        return True
